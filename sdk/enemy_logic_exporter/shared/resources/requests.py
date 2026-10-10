"""Locate explicit action requests using the reviewed native position contract."""

import gzip
import hashlib
import json
from collections import deque
from pathlib import Path
from ..native.evidence import evidence_key, method_rows
from ..native.pe import PE, verify_rows
from ..native.metadata import Il2cppMetadata
from ..config import (
    in_agents,
    EXPORT_COMMAND_POSITION_TYPE,
    OPERATOR_PREV_COMMAND_POSITION,
    OPERATOR_REQUEST_COMMAND,
    OPERATOR_WORK_TYPE,
    REQUEST_ACTION_COMMANDS,
    SELECT_ACTION_ARGUMENT,
    SUPPORTED_PROFILE,
)
from .reader import Resources, typed
from .action_names import ActionNames


def packed_request_stores(native, address, *, block_starts=()):
    """Track straight-line constants and the fourth ABI parameter (operator work).

    A branch clears constants. Calls clear volatile registers. Unknown writes
    discard values. Stores through unrelated objects cannot become requests.
    """
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_REG, CS_OP_MEM, CS_OP_IMM

    disassembler = Cs(CS_ARCH_X86, CS_MODE_64)
    disassembler.detail = True
    values = {}
    stores = []
    volatile = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}

    def register(instruction, identifier):
        name = instruction.reg_name(identifier)
        if name in {"eax", "ecx", "edx", "ebx", "esi", "edi", "ebp", "esp"}:
            return "r" + name[1:]
        if name.startswith("r") and name.endswith("d"):
            return name[:-1]
        return name

    instructions = list(disassembler.disasm(native, address))
    writes, candidates, prologue_aliases = {}, {}, {"r9"}
    in_prologue = True
    starts = set(block_starts)
    for index, instruction in enumerate(instructions):
        _, changed = instruction.regs_access()
        restored_at_return = False
        if instruction.mnemonic == "pop":
            for following in instructions[index + 1 : index + 17]:
                if following.mnemonic.startswith("ret"):
                    restored_at_return = True
                    break
                if (
                    following.mnemonic == "call"
                    or following.mnemonic.startswith("j")
                    or (
                        following.operands
                        and following.operands[0].type == CS_OP_MEM
                        and following.mnemonic.startswith("mov")
                    )
                ):
                    break
        for identifier in changed:
            if not restored_at_return:
                writes.setdefault(register(instruction, identifier), set()).add(
                    instruction.address
                )
        if instruction.mnemonic == "call":
            for name in volatile:
                writes.setdefault(name, set()).add(instruction.address)
        if (
            instruction.mnemonic.startswith("j")
            and instruction.operands
            and instruction.operands[0].type == CS_OP_IMM
        ):
            starts.add(instruction.operands[0].imm)
        if in_prologue:
            operands = instruction.operands
            is_copy = (
                instruction.mnemonic in {"mov", "movabs"}
                and len(operands) == 2
                and operands[0].type == operands[1].type == CS_OP_REG
                and operands[0].size == operands[1].size == 8
            )
            source_operator = (
                is_copy and register(instruction, operands[1].reg) in prologue_aliases
            )
            for identifier in changed:
                prologue_aliases.discard(register(instruction, identifier))
            if source_operator:
                name = register(instruction, operands[0].reg)
                prologue_aliases.add(name)
                candidates[name] = instruction.address
            if instruction.mnemonic == "call" or instruction.mnemonic.startswith("j"):
                in_prologue = False
    operators = {
        name: site for name, site in candidates.items() if writes.get(name) == {site}
    }
    if not writes.get("r9"):
        operators["r9"] = address
    # An alias can be overwritten after the request, for example when the
    # compiler reuses rdi for ReturnStack. Prove its value at each store through
    # the actual direct CFG, rather than rejecting all earlier uses globally.
    # Joins intersect provenance; a back edge carrying a clobber loses it.
    by_address = {instruction.address: instruction for instruction in instructions}
    aliases = {address: frozenset({"r9"})}
    pending = deque([address])
    while pending:
        site = pending.popleft()
        instruction = by_address.get(site)
        if instruction is None:
            continue
        before = aliases[site]
        after = set(before)
        _, changed = instruction.regs_access()
        after.difference_update(
            register(instruction, identifier) for identifier in changed
        )
        operands = instruction.operands
        if (
            instruction.mnemonic in {"mov", "movabs"}
            and len(operands) == 2
            and operands[0].type == operands[1].type == CS_OP_REG
            and operands[0].size == operands[1].size == 8
            and register(instruction, operands[1].reg) in before
        ):
            after.add(register(instruction, operands[0].reg))
        if instruction.mnemonic == "call":
            after.difference_update(volatile)
        following = site + instruction.size
        if instruction.mnemonic.startswith("ret"):
            successors = []
        elif instruction.mnemonic.startswith("j"):
            if operands and operands[0].type == CS_OP_IMM:
                successors = [operands[0].imm]
                if instruction.mnemonic != "jmp":
                    successors.append(following)
            else:
                # An unresolved computed jump may enter any supplied block.
                # It cannot add provenance to those blocks.
                successors, after = list(starts), set()
        else:
            successors = [following]
        for target in successors:
            if target not in by_address:
                continue
            merged = (
                frozenset(after)
                if target not in aliases
                else aliases[target].intersection(after)
            )
            if target not in aliases or merged != aliases[target]:
                aliases[target] = merged
                pending.append(target)
    for instruction in instructions:
        if instruction.address in starts and instruction.address != address:
            values.clear()
        operands = instruction.operands
        if instruction.mnemonic.startswith("j") or instruction.mnemonic.startswith(
            "ret"
        ):
            values.clear()
        if instruction.mnemonic == "call":
            for name in volatile:
                values.pop(name, None)
            continue
        if instruction.mnemonic not in {"mov", "movabs"} or len(operands) != 2:
            _, written = instruction.regs_access()
            for identifier in written:
                name = register(instruction, identifier)
                values.pop(name, None)
            continue
        destination, source = operands
        value = (
            source.imm & ((1 << (source.size * 8)) - 1)
            if source.type == CS_OP_IMM
            else (
                values.get(register(instruction, source.reg))
                if source.type == CS_OP_REG
                else None
            )
        )
        if destination.type == CS_OP_REG:
            name = register(instruction, destination.reg)
            values.pop(name, None)
            if value is not None:
                values[name] = value & ((1 << (destination.size * 8)) - 1)
        elif (
            destination.type == CS_OP_MEM
            and destination.size == 8
            and destination.mem.disp == OPERATOR_REQUEST_COMMAND
            and not destination.mem.index
            and (
                register(instruction, destination.mem.base)
                in aliases.get(instruction.address, ())
                or (
                    register(instruction, destination.mem.base) in operators
                    and instruction.address
                    >= operators[register(instruction, destination.mem.base)]
                )
            )
            and value is not None
        ):
            stores.append(
                dict(
                    address=hex(instruction.address),
                    packedValue=value,
                    commandIndex=value & 0xFFFFFFFF,
                    argumentIndex=value >> 32,
                )
            )
    return stores


def discover_requests(native_index, inventory, exe, metadata, natives, output):
    """Report bindings and boundaries; do not infer branch order or complete AI."""
    native_index, output = Path(native_index), Path(output)
    if not in_agents(output):
        raise ValueError("原生请求研究结果只允许写入 .agents")
    index = json.loads(native_index.read_text(encoding="utf8"))
    inventory = json.loads(Path(inventory).read_text(encoding="utf8"))
    if (
        index["profile"] != SUPPORTED_PROFILE
        or inventory["profile"] != index["profile"]
    ):
        raise ValueError("请求位置契约只支持已核实的 1.42.0.2 来源")
    with Il2cppMetadata(Path(metadata)) as metadata_data:
        if metadata_data.sha256 != index["profile"]["metadataSha256"]:
            raise ValueError("元数据来源版本不匹配")
        operator = metadata_data.fields(OPERATOR_WORK_TYPE)
        position = metadata_data.fields(EXPORT_COMMAND_POSITION_TYPE)
        if int(operator["PrevCommandPosition"]["offset_from_base"], 16) != OPERATOR_PREV_COMMAND_POSITION:
            raise ValueError("原生请求位置字段偏移已改变")
        if (
            int(position["CommandNum"]["offset_from_fieldptr"], 16) != 4
            or int(position["CommmandArgNum"]["offset_from_fieldptr"], 16) != 8
        ):
            raise ValueError("请求位置中的命令和参数索引布局已改变")
        contract = dict(
            operatorField=operator["PrevCommandPosition"], positionFields=position
        )
    rows = method_rows(index)
    verify_rows(exe, rows)
    resources = Resources(natives)
    by_type = {r["exportType"]: r for r in inventory["resources"]}
    events, boundaries, action_catalog = [], [], {}
    name_sources = {}
    body_cache = {}
    with PE(exe) as pe:
        for row in rows:
            if not row["method"].startswith("table_"):
                continue
            key = evidence_key(row)
            artifact = index["nativeBodyArtifacts"][key]
            cache_path = native_index.parent / artifact["path"]
            if key not in body_cache:
                raw = cache_path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                    raise ValueError("原生压缩证据摘要不匹配")
                with gzip.open(cache_path, "rt", encoding="utf8") as stream:
                    data = json.load(stream)
                # Keep just the position constants found in the decompiled C.
                code = data.get("code", "").replace("\r", "")
                data = dict(
                    completed=data["completed"],
                    hasPositionStore=f"+ {OPERATOR_REQUEST_COMMAND:#x})" in code,
                    blockStarts=[
                        int(b["start"], 16)
                        for b in data.get("controlFlow", {}).get("blocks", [])
                    ],
                )
                body_cache[key] = data
            data = body_cache[key]
            if not data["completed"]:
                boundaries.append(
                    dict(
                        type=row["type"],
                        method=row["method"],
                        reason="native_extraction_failed",
                    )
                )
                continue
            if not data["hasPositionStore"]:
                continue
            source = by_type[row["type"]]["resource"]
            body = resources.read(source)
            factories = resources.factories(body)
            native = pe.read(
                int(row["address"], 16), int(row["end"], 16) - int(row["address"], 16)
            )
            stores = packed_request_stores(
                native, int(row["address"], 16), block_starts=data["blockStarts"]
            )
            if not stores:
                boundaries.append(
                    dict(
                        type=row["type"],
                        method=row["method"],
                        reason="position_store_requires_nonlocal_register_or_stack_dataflow",
                    )
                )
            for store in stores:
                command, argument = store["commandIndex"], store["argumentIndex"]
                if command >= len(factories) or argument >= len(
                    body["_CommandArgArray"]
                ):
                    boundaries.append(
                        dict(
                            type=row["type"],
                            method=row["method"],
                            **store,
                            reason="position_outside_resource_slots"
                        )
                    )
                    continue
                factory = factories[command]
                arg_type, arg = typed(body["_CommandArgArray"][argument])
                if (
                    arg_type != SELECT_ACTION_ARGUMENT
                    or factory["_ArgumentType"] != arg_type
                    or factory["_OrderType"]
                    not in set(REQUEST_ACTION_COMMANDS)
                ):
                    boundaries.append(
                        dict(
                            type=row["type"],
                            method=row["method"],
                            **store,
                            reason="request_is_not_an_explicit_select_action",
                            commandType=factory["_OrderType"],
                            argumentType=arg_type
                        )
                    )
                    continue
                try:
                    action = resources.action(body, arg)
                except (ValueError, FileNotFoundError) as error:
                    boundaries.append(
                        dict(
                            type=row["type"],
                            method=row["method"],
                            resource=source,
                            resourceSha256=resources.hashes[source],
                            nativeCodeRef=key,
                            **store,
                            reason="action_identity_binding_unresolved",
                            error=str(error),
                            argument=arg
                        )
                    )
                    continue
                owner_id = (
                    "EM"
                    + source.split("/Enemy/Em", 1)[1]
                    .split("/BTable/", 1)[0]
                    .replace("/", "_")
                    + "_0"
                )
                if owner_id not in name_sources:
                    name_sources[owner_id] = ActionNames(resources, owner_id)
                name_sources[owner_id].bind(action)
                identity = [
                    action[k] for k in ("source", "actionGuid", "parameterVariantGuid")
                ]
                identity_key = hashlib.sha256(
                    json.dumps(identity).encode()
                ).hexdigest()[:24]
                action_catalog.setdefault(
                    identity_key,
                    {
                        k: action[k]
                        for k in (
                            "source",
                            "actionGuid",
                            "instanceActionGuid",
                            "actionGuidBinding",
                            "parameterVariantGuid",
                            "actionClass",
                            "parameterAsset",
                            "declaredParameterAsset",
                            "parameterResolutionChain",
                            "parameterBodyPointer",
                            "parameterOverridesResolved",
                            "displayName",
                            "nameBinding",
                        )
                    },
                )
                events.append(
                    dict(
                        type=row["type"],
                        method=row["method"],
                        tableGuid=row["method"][6:42].replace("_", "-"),
                        resource=source,
                        resourceSha256=resources.hashes[source],
                        nativeCodeRef=key,
                        **store,
                        actionRef=identity_key,
                        status="native_position_and_resource_binding_verified",
                        controlFlowReviewed=False
                    )
                )
    counts = {}
    for monster in inventory["monsters"]:
        relevant = set(monster["tableImportClosure"])
        found = [e for e in events if e["resource"] in relevant]
        counts[monster["enemyId"]] = dict(
            explicitActionRequestStores=len(found),
            distinctActionVariants=len({e["actionRef"] for e in found}),
            entireBattleRecovered=False,
        )
    result = dict(
        profile=index["profile"],
        nativePositionContract=contract,
        actionRequestBindings=events,
        actionCatalog=action_catalog,
        boundaries=boundaries,
        monsters=counts,
        shellNameCatalogs={
            k: v.catalog()["shellCatalog"] for k, v in name_sources.items()
        },
        sourceHashes=resources.hashes,
        scope="核实原生位置写入与资源动作身份；分支、调用/返回、运行时选中动作和具体 Shell 触发另行恢复",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf8"
    )
    receipt = dict(
        monsters=len(counts),
        explicitActionRequestStores=len(events),
        distinctActionVariants=len(action_catalog),
        unresolvedPositionStores=len(boundaries),
        semanticControlFlowComplete=False,
    )
    print("REQUEST DISCOVERY", json.dumps(receipt), flush=True)
    return receipt
