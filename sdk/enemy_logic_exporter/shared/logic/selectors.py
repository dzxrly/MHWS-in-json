"""Recover matched selector operands and native index-to-PC dispatch paths.

Static initializer order is never an execution order.  Candidate program
counters are evaluated from the method's own instructions after its selected
index load, then checked against the actual child call and saved continuation.
Unsupported filtering/dispatch forms retain their native boundary.
"""

import re
from ..resources.reader import typed
from ..config import (
    ARRAY_ELEMENTS,
    ARRAY_LENGTH,
    EXPORT_ARGUMENTS,
    OPERATOR_EXPORT_END,
    OPERATOR_POSITION_ROW,
    OPERATOR_RANDOM_SELECTED,
    POOL_KEY,
    POOL_WEIGHT,
    REFERENCE_ARRAY_STRIDE,
)

# Ghidra pseudo-C spellings of the argument array and pool weight fields.
ARGUMENTS_FIELD = rf"\+ {EXPORT_ARGUMENTS:#x}\)"
ARGUMENT_SLOT = ARGUMENTS_FIELD + rf" \+ {ARRAY_ELEMENTS:#x}"
POOL_WEIGHT_TEXT = f" + {POOL_WEIGHT:#x}"
POOL_WEIGHT_PATTERN = re.escape(POOL_WEIGHT_TEXT)


class SelectorBoundary(ValueError):
    pass


def _outer_blocks(code):
    cases = list(re.finditer(r"^( +)case (0x[0-9a-f]+|\d+):", code, re.M))
    indentation = min((len(match[1]) for match in cases), default=999)
    cases = [match for match in cases if len(match[1]) == indentation]
    return {
        int(match[2], 0): code[
            match.end() : (
                cases[number + 1].start() if number + 1 < len(cases) else len(code)
            )
        ]
        for number, match in enumerate(cases)
    }


def _dispatch_pc(
    machine,
    address,
    *,
    selected_register=None,
    selected_index=None,
    selected_memory=None,
    pc_register="rax",
):
    """Evaluate actual index branches up to the next C6/dispatcher guard.

    Other runtime registers are unknown, so any branch depending on them stops
    this recovery.  Unknown pointer loads/writes do not grant a runtime state.
    ``selected_memory`` names the register that points at the chosen packed
    candidate when the compiler compares its index in memory directly.
    """
    from capstone import CS_OP_MEM, CS_OP_REG

    from .machine import Boundary
    from ..native.bindings import pointer

    state = machine.initial(0)
    state["regs"] = {"rsp": pointer("selector_stack")}
    state["mem"] = {}
    if selected_register is not None:
        state["regs"][selected_register] = selected_index
    if selected_memory is not None:
        state["regs"][selected_memory] = pointer("selected_candidate")
        state["mem"][("selected_candidate", 0, 4)] = selected_index
    for _ in range(192):
        instruction = machine.ins.get(address)
        if instruction is None:
            break
        operands = instruction.operands
        if (
            instruction.mnemonic == "cmp"
            and operands
            and operands[0].type == CS_OP_MEM
            and operands[0].mem.disp == OPERATOR_EXPORT_END
        ):
            value = state["regs"].get(pc_register)
            if type(value) is int:
                return value
            raise SelectorBoundary("选择完成后的原生 PC 寄存器未恢复")
        if instruction.mnemonic == "call" or instruction.mnemonic.startswith("ret"):
            raise SelectorBoundary("候选分派经过未核实调用或返回")
        try:
            address = machine.step(instruction, state)
        except Boundary as error:
            raise SelectorBoundary(str(error)) from error
        if address is None:
            break
    raise SelectorBoundary("候选分派未到达明确的 C6/调度器检查")


def _native_routes(machine, pool_address):
    """Find the real pool/key store and its selected-index/fallback paths."""
    from capstone import CS_OP_IMM, CS_OP_MEM, CS_OP_REG

    from ..native.bindings import register

    instructions = list(machine.ins.values())
    selections, fallbacks, guards, filter_ends = [], [], [], []
    for number, instruction in enumerate(instructions):
        operands = instruction.operands
        if not (
            instruction.mnemonic == "mov"
            and len(operands) == 2
            and operands[0].type == CS_OP_REG
            and operands[1].type == CS_OP_MEM
            and instruction.reg_name(operands[1].mem.base) == "rip"
            and instruction.address + instruction.size + operands[1].mem.disp
            == pool_address
        ):
            continue
        following = instructions[number + 1 : number + 9]
        if (
            len(following) >= 2
            and following[0].mnemonic == "cmp"
            and following[0].operands[0].type == CS_OP_MEM
            and following[0].operands[0].mem.disp == ARRAY_LENGTH
            and following[1].mnemonic == "jle"
            and following[1].operands[0].type == CS_OP_IMM
        ):
            guards.append(following[1].address)
            filter_ends.append(following[1].operands[0].imm)
            # Empty static/filter candidate sets skip the total-weight draw.
            # Follow the actual following signed-positive total guard rather
            # than inventing candidate zero as a fallback.
            total_address = following[1].operands[0].imm
            comparison = None
            for _ in range(5):
                total = machine.ins.get(total_address)
                if not total:
                    break
                if (
                    comparison
                    and total.mnemonic == "jle"
                    and total.operands[0].type == CS_OP_IMM
                ):
                    fallbacks.append(total.operands[0].imm)
                    break
                # mov and lea leave the flags of the total-weight compare intact.
                if total.mnemonic not in {"mov", "lea", "cmp", "test"}:
                    break
                if total.mnemonic in {"cmp", "test"}:
                    comparison = total
                total_address = total.address + total.size
        stores = [
            item
            for item in following
            if item.mnemonic == "mov"
            and item.operands[0].type == CS_OP_MEM
            and item.operands[0].mem.disp == OPERATOR_RANDOM_SELECTED
        ]
        keys = [
            item
            for item in following
            if item.mnemonic == "mov"
            and item.operands[1].type == CS_OP_MEM
            and item.operands[1].mem.disp == ARRAY_ELEMENTS
            and item.operands[1].mem.scale == REFERENCE_ARRAY_STRIDE
            and item.operands[1].mem.index
        ]
        if len(stores) != 1 or len(keys) != 1:
            continue
        # With few candidates the compiler compares the chosen packed entry's
        # index in memory (cmp dword ptr [reg], imm) instead of loading it.
        direct = [
            item
            for item in following
            if item.mnemonic == "cmp"
            and len(item.operands) == 2
            and item.operands[0].type == CS_OP_MEM
            and item.operands[0].size == 4
            and item.operands[0].mem.disp == 0
            and not item.operands[0].mem.index
            and item.reg_name(item.operands[0].mem.base) not in {"rip", "rsp"}
            and item.operands[1].type == CS_OP_IMM
        ]
        if len(direct) == 1:
            base = register(direct[0], direct[0].operands[0].mem.base)
            between = instructions[number : instructions.index(direct[0])]
            if not any(
                item.operands
                and item.operands[0].type == CS_OP_REG
                and register(item, item.operands[0].reg) == base
                for item in between
            ):
                selections.append(
                    dict(
                        start=direct[0].address,
                        selectedMemory=base,
                        selectedIndexCompare=hex(direct[0].address),
                        previousKeyStore=hex(stores[0].address),
                    )
                )
                continue
        index_loads = [
            item
            for item in instructions[max(0, number - 8) : number]
            if item.mnemonic == "mov"
            and len(item.operands) == 2
            and item.operands[0].type == CS_OP_REG
            and item.operands[1].type == CS_OP_MEM
            and item.operands[1].mem.disp == 0
            and not item.operands[1].mem.index
            and item.reg_name(item.operands[1].mem.base) not in {"rip", "rsp"}
        ]
        if not index_loads:
            continue
        selected_register = register(index_loads[-1], index_loads[-1].operands[0].reg)
        # The key lookup/store must preserve the chosen candidate's register.
        between = instructions[number : instructions.index(stores[0]) + 1]
        if any(
            item.operands
            and item.operands[0].type == CS_OP_REG
            and register(item, item.operands[0].reg) == selected_register
            for item in between
        ):
            continue
        selections.append(
            dict(
                # Begin after the actual selected-index load.  The following
                # instructions may copy/sign-extend that index into a second
                # register used by some candidate comparisons.
                start=index_loads[-1].address + index_loads[-1].size,
                selectedRegister=selected_register,
                selectedIndexLoad=hex(index_loads[-1].address),
                previousKeyStore=hex(stores[0].address),
            )
        )
    if len(selections) != 1 or len(set(fallbacks)) != 1:
        raise SelectorBoundary(
            f"静态池的候选分派({len(selections)})或空池回退({len(set(fallbacks))})没有唯一原生路径"
        )
    pc_registers = {
        register(item, item.operands[0].reg)
        for item in instructions
        if item.mnemonic == "mov"
        and item.operands[0].type == CS_OP_REG
        and item.operands[1].type == CS_OP_MEM
        and item.operands[1].mem.disp == OPERATOR_POSITION_ROW
        and not item.operands[1].mem.index
        and item.operands[0].size == 4
    }
    if len(pc_registers) != 1:
        raise SelectorBoundary("外层 PC 的实际寄存器未能唯一恢复")
    selections[0]["programCounterRegister"] = next(iter(pc_registers))
    if len(set(guards)) != 1 or len(set(filter_ends)) != 1:
        raise SelectorBoundary("静态池的筛选循环没有唯一长度守卫")
    selections[0]["poolSizeGuard"] = hex(guards[0])
    selections[0]["filterLoopEnd"] = hex(filter_ends[0])
    return selections[0], next(iter(set(fallbacks)))


def _filter_arguments(machine, block, pool, route, body):
    """Bind either one shared list or the proved per-candidate index loop."""
    from capstone import CS_OP_IMM, CS_OP_MEM, CS_OP_REG

    from ..native.bindings import register

    dynamic = set(re.findall(ARGUMENT_SLOT + r" \+ (\w+) \* 8", block))
    if dynamic:
        if len(dynamic) != 1:
            raise SelectorBoundary("候选跳过参数存在多个动态索引")
        variable = next(iter(dynamic))
        prefix = block[: block.index(POOL_WEIGHT_TEXT)]
        bases = set(
            int(value, 0)
            for value in re.findall(
                rf"\b{re.escape(variable)} = (0x[0-9a-f]+|\d+);", prefix
            )
        )
        if len(bases) != 1 or not re.search(
            rf"\b{re.escape(variable)} = {re.escape(variable)} \+ 1;",
            prefix + block[block.index(POOL_WEIGHT_TEXT) : block.index(" % ")],
        ):
            raise SelectorBoundary("逐候选参数的常量基址及递增循环尚未核实")
        base = next(iter(bases))
        guard, end = int(route["poolSizeGuard"], 16), int(route["filterLoopEnd"], 16)
        window = [
            item for address, item in machine.ins.items() if guard < address < end
        ]
        matches = []
        for number, instruction in enumerate(window):
            for operand in instruction.operands:
                if not (
                    operand.type == CS_OP_MEM
                    and operand.mem.disp == ARRAY_ELEMENTS
                    and operand.mem.scale == REFERENCE_ARRAY_STRIDE
                    and operand.mem.index
                ):
                    continue
                index = register(instruction, operand.mem.index)
                initializers = [
                    item
                    for item in window[:number]
                    if item.mnemonic == "mov"
                    and item.operands[0].type == CS_OP_REG
                    and register(item, item.operands[0].reg) == index
                    and item.operands[1].type == CS_OP_IMM
                    and item.operands[1].imm == base
                ]
                increments = [
                    item
                    for item in window[number + 1 :]
                    if item.operands
                    and item.operands[0].type == CS_OP_REG
                    and register(item, item.operands[0].reg) == index
                    and (
                        item.mnemonic == "inc"
                        or (
                            item.mnemonic == "add"
                            and item.operands[1].type == CS_OP_IMM
                            and item.operands[1].imm == 1
                        )
                    )
                ]
                if len(initializers) == len(increments) == 1:
                    matches.append(
                        dict(
                            argumentBase=base,
                            indexRegister=index,
                            initializationSite=hex(initializers[0].address),
                            argumentLoadSite=hex(instruction.address),
                            incrementSite=hex(increments[0].address),
                        )
                    )
        if len(matches) != 1:
            raise SelectorBoundary("逐候选参数的实际基址写入、数组读取及递增指令不唯一")
        indices = [base + number for number in range(len(pool["entries"]))]
        mode = "per_candidate"
        filter_evidence = matches[0]
    else:
        offsets = set(
            int(value, 0)
            for value in re.findall(ARGUMENTS_FIELD + r" \+ (0x[0-9a-f]+|\d+)", block)
        )
        if len(offsets) != 1:
            raise SelectorBoundary("动态参数或筛选索引需要专项核查")
        offset = next(iter(offsets))
        if offset < ARRAY_ELEMENTS or (offset - ARRAY_ELEMENTS) % REFERENCE_ARRAY_STRIDE:
            raise SelectorBoundary("跳过参数的原生偏移不匹配参数数组布局")
        indices = [(offset - ARRAY_ELEMENTS) // REFERENCE_ARRAY_STRIDE]
        mode = "shared"
        filter_evidence = dict(argumentOffset=hex(offset))
    arguments = []
    for index in indices:
        if not 0 <= index < len(body["_CommandArgArray"]):
            raise SelectorBoundary("跳过参数原生索引超出本资源范围")
        argument_type, _ = typed(body["_CommandArgArray"][index])
        if not argument_type.endswith("cSetSkipActionTblArg"):
            raise SelectorBoundary("原生跳过参数对应的资源类型发生变化")
        arguments.append(dict(index=index, type=argument_type))
    return mode, arguments, filter_evidence


def _selection_form(block, address, code):
    """Require the observed uint32/modulo/strict-weight selection form."""
    pool = f"lRam0000000{address:x}"
    required = (
        rf"{pool} \+ {ARRAY_LENGTH:#x}",
        rf"{pool} \+ {POOL_WEIGHT:#x}",
        rf"{pool} \+ {POOL_KEY:#x}",
        r"& 0xffffffff\) % \(ulonglong\)",
    )
    if any(re.search(pattern, block) is None for pattern in required):
        raise SelectorBoundary("原生筛选、uint32 取模或严格权重比较样式需要专项核查")
    comparison = r"if \(\(int\)\w+ < \*\(int \*\)\(\w+ \+ 4\)\)"
    subtract = r"\(int\)\w+ - \*\(int \*\)\(\w+ \+ 4\)"
    if re.search(comparison, block) and re.search(subtract, block):
        return
    inverse = re.search(
        r"if \(\*\(int \*\)\(\w+ \+ 4\) <= \(int\)\w+\) goto (\w+);",
        block,
    )
    if inverse:
        tail = re.search(
            rf"^{re.escape(inverse[1])}:\n(.*?)(?=^\w+:|\Z)", code, re.M | re.S
        )
        if (
            tail
            and re.search(subtract, tail[1])
            and any(
                re.search(rf"^{re.escape(target)}:", block, re.M)
                for target in re.findall(r"goto (\w+);", tail[1])
            )
        ):
            return
    raise SelectorBoundary("严格权重比较与相减循环未能绑定到本 PC 的实际分支")


def recover_selectors(machine, code, pools, body):
    """Return recovered graph, accepted selections and explicit boundaries."""
    start = int(machine.row["address"], 16)
    code = code.replace("\r", "")
    blocks = _outer_blocks(code)
    evidence, boundaries = [], []
    for pc, block in blocks.items():
        references = set(re.findall(r"lRam0000000(1[0-9a-f]+)" + POOL_WEIGHT_PATTERN, block))
        if not references:
            continue
        boundary = machine.walk(start, machine.initial(pc))
        record = dict(programCounter=pc, nativeBoundary=boundary)
        try:
            if len(references) != 1:
                raise SelectorBoundary("同一外层 PC 引用了多个静态池")
            address = int(next(iter(references)), 16)
            record["staticArray"] = hex(address)
            pool = pools.get(hex(address))
            if pool is None:
                raise SelectorBoundary("缺少此静态池的匹配原生初始化证据")
            if (
                not pool["entries"]
                or any(
                    type(entry["weight"]) is not int or entry["weight"] < 0
                    for entry in pool["entries"]
                )
                or sum(entry["weight"] for entry in pool["entries"]) > 0x7FFFFFFF
            ):
                raise SelectorBoundary("空池、负权重或原生有符号总权重溢出需要专项核查")
            _selection_form(block, address, code)
            route, fallback_address = _native_routes(machine, address)
            filtering, arguments, filter_evidence = _filter_arguments(
                machine, block, pool, route, body
            )
            fallback_pc = _dispatch_pc(
                machine, fallback_address, pc_register=route["programCounterRegister"]
            )
            candidate_pcs = [
                _dispatch_pc(
                    machine,
                    route["start"],
                    selected_register=route.get("selectedRegister"),
                    selected_memory=route.get("selectedMemory"),
                    selected_index=number,
                    pc_register=route["programCounterRegister"],
                )
                for number in range(len(pool["entries"]))
            ]
            if fallback_pc not in blocks or any(
                value not in blocks for value in candidate_pcs
            ):
                raise SelectorBoundary("真实候选或空池回退 PC 不在当前方法外层分派中")
            if machine.nodes[boundary]["kind"] != "unknown":
                raise SelectorBoundary("选择器前缀已产生其他语义，不能覆盖为随机节点")
            if machine.nodes[boundary].get("nativeSite") != route["poolSizeGuard"]:
                raise SelectorBoundary(
                    "选择器前仍有其他未知逻辑，不能覆盖它的条件或副作用"
                )
            candidates, candidate_routes = [], []
            for number, candidate_pc in enumerate(candidate_pcs):
                entry = machine.walk(start, machine.initial(candidate_pc))
                selected = machine.nodes[entry]
                if selected["kind"] != "call" or not selected.get("nativeContinuation"):
                    record["candidateNode"] = dict(
                        nativeCandidateIndex=number,
                        nativeProgramCounter=candidate_pc,
                        kind=selected["kind"],
                        reason=selected.get("reason"),
                        nativeSite=selected.get("nativeSite"),
                    )
                    raise SelectorBoundary("候选没有唯一子表调用及准确保存恢复位置")
                candidates.append(
                    dict(
                        id=f"slot:{number}",
                        nodeId=machine.state(candidate_pc),
                        targetTable=selected["targetTable"],
                        weight=pool["entries"][number]["weight"],
                        nativeKey=pool["entries"][number]["nativeKey"],
                        nativeCandidateIndex=number,
                        nativeProgramCounter=candidate_pc,
                    )
                )
                if filtering == "per_candidate":
                    candidates[-1].update(
                        skipArgumentIndex=arguments[number]["index"],
                        expectedSkipArgumentType=arguments[number]["type"],
                    )
                candidate_routes.append(
                    {**candidates[-1], "nodeId": entry, "targetNativeNode": entry}
                )
            collision_groups = {}
            for candidate in candidate_routes:
                collision_groups.setdefault(candidate["targetNativeNode"], []).append(
                    candidate
                )
            convergences = {
                key: values
                for key, values in collision_groups.items()
                if len(values) > 1
            }
            if convergences:
                # Slot identities remain independent even when their verified
                # native PCs converge on one real call instruction. Keep the
                # raw native node identity in evidence; do not clone the call,
                # merge weights/filters or invent another program counter.
                record["candidateDispatchConvergences"] = convergences
            machine.nodes[boundary] = dict(
                id=boundary,
                kind="weighted_random",
                filteringMode=filtering,
                candidates=candidates,
                fallback=machine.state(fallback_pc),
                staticArray=hex(address),
                initializerEvidence=pool["initializerEvidence"],
                execution="filter_candidates_then_uint32_mod_total_weight_then_first_strict_less_weight",
                selectionEffects={
                    "previousTableHash": "按当前原生索引写入；不能假定过滤后仍使用原候选索引",
                    "contextFlag14": "各候选分派的真实写入保留在原生证据中",
                },
            )
            if filtering == "shared":
                machine.nodes[boundary].update(
                    argumentIndex=arguments[0]["index"],
                    expectedArgumentType=arguments[0]["type"],
                )
            evidence.append(
                dict(
                    **record,
                    entries=pool["entries"],
                    candidateStates=candidate_pcs,
                    fallbackState=fallback_pc,
                    nativeDispatch=route,
                    candidateFiltering=dict(mode=filtering, **filter_evidence),
                    status="matched_native_dispatch_and_child_resume",
                )
            )
        except SelectorBoundary as error:
            boundaries.append(
                dict(**record, reason=str(error), status="unreviewed_selector_boundary")
            )
    result = machine.build()

    def resolve(key):
        seen = set()
        while key in machine.states and key not in seen:
            seen.add(key)
            key = machine.states[key]
        return key

    for node in result["nodes"]:
        if node["kind"] == "weighted_random":
            for candidate in node["candidates"]:
                candidate["nodeId"] = resolve(candidate["nodeId"])
            node["fallback"] = resolve(node["fallback"])
    return result, evidence, boundaries
