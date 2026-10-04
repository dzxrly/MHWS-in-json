"""Bind native calls to BTable resources using conservative x64 dataflow.

High P-code varnode offsets do not carry SSA identities in the existing cache.
Use actual machine registers, stack writes and the Microsoft x64 ABI instead.
"""

from collections import deque

VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}


def register(instruction, identifier):
    name = instruction.reg_name(identifier) or ""
    families = {
        "al": "rax",
        "ah": "rax",
        "ax": "rax",
        "eax": "rax",
        "cl": "rcx",
        "ch": "rcx",
        "cx": "rcx",
        "ecx": "rcx",
        "dl": "rdx",
        "dh": "rdx",
        "dx": "rdx",
        "edx": "rdx",
        "bl": "rbx",
        "bh": "rbx",
        "bx": "rbx",
        "ebx": "rbx",
        "sil": "rsi",
        "si": "rsi",
        "esi": "rsi",
        "dil": "rdi",
        "di": "rdi",
        "edi": "rdi",
        "bpl": "rbp",
        "bp": "rbp",
        "ebp": "rbp",
        "spl": "rsp",
        "sp": "rsp",
        "esp": "rsp",
    }
    if name in families:
        return families[name]
    if name.startswith("r") and name[-1:] in {"d", "w", "b"}:
        return name[:-1]
    return name


def pointer(owner, offset=0):
    return "pointer", owner, offset


def add(base, offset):
    if isinstance(base, int):
        return base + offset
    if isinstance(base, tuple) and base[0] == "pointer":
        return pointer(base[1], base[2] + offset)
    return None


def dereference(value):
    if not isinstance(value, tuple) or value[0] != "pointer":
        return None
    _, owner, offset = value
    if owner == "export":
        if offset == 0x10:
            return pointer("commands")
        if offset == 0x18:
            return pointer("arguments")
        return ("export_field", offset)
    if (
        owner in {"commands", "arguments"}
        and offset >= 0x20
        and (offset - 0x20) % 8 == 0
    ):
        return pointer(
            ("command" if owner == "commands" else "argument", (offset - 0x20) // 8)
        )
    if isinstance(owner, tuple) and owner[0] == "command" and offset == 0:
        return pointer(("command_vtable", owner[1]))
    if isinstance(owner, tuple) and owner[0] == "command_vtable":
        return ("command_method", owner[1], offset)
    if owner == "operator":
        return ("operator_field", offset)
    return None


def memory_address(instruction, operand, values):
    mem = operand.mem
    base_name = instruction.reg_name(mem.base)
    base = (
        instruction.address + instruction.size
        if base_name == "rip"
        else (values.get(register(instruction, mem.base)) if mem.base else 0)
    )
    if mem.index:
        index = values.get(register(instruction, mem.index))
        if not isinstance(index, int):
            return None
        return add(base, mem.disp + index * mem.scale)
    return add(base, mem.disp)


def _transfer(instructions, incoming, *, collect=False):
    from capstone import CS_OP_IMM, CS_OP_REG, CS_OP_MEM

    values = dict(incoming)
    events = []

    def read(ins, operand):
        if operand.type == CS_OP_IMM:
            return operand.imm & ((1 << (operand.size * 8)) - 1)
        if operand.type == CS_OP_REG:
            value = values.get(register(ins, operand.reg))
            if ins.reg_name(operand.reg) in {"ah", "bh", "ch", "dh"}:
                return (value >> 8) & 0xFF if isinstance(value, int) else None
            if operand.size < 8:
                if isinstance(value, tuple) and value[0] == "call_result":
                    return value
                return (
                    value & ((1 << (operand.size * 8)) - 1)
                    if isinstance(value, int)
                    else None
                )
            return value
        if operand.type == CS_OP_MEM:
            location = memory_address(ins, operand, values)
            if isinstance(location, tuple) and location[:2] == ("pointer", "stack"):
                return values.get(("stack", location[2], operand.size))
            if (
                isinstance(location, tuple)
                and location[0] == "pointer"
                and location[1] == "operator"
            ):
                return ("operator_field", location[2])
            return dereference(location) if operand.size == 8 else None
        return None

    for ins in instructions:
        operands = ins.operands
        mnemonic = ins.mnemonic
        if mnemonic == "call":
            target = read(ins, operands[0])
            args = [values.get(k) for k in ("rcx", "rdx", "r8", "r9")]
            rsp = values.get("rsp")
            fifth = (
                values.get(("stack", rsp[2] + 0x20, 8))
                if isinstance(rsp, tuple) and rsp[:2] == ("pointer", "stack")
                else None
            )
            if collect:
                positions = {}
                for index, arg in enumerate(args + [fifth]):
                    if isinstance(arg, tuple) and arg[:2] == ("pointer", "stack"):
                        packed = values.get(("stack", arg[2] + 4, 8))
                        if isinstance(packed, int):
                            positions[index] = dict(
                                tableIndex=packed & 0xFFFFFFFF,
                                programCounter=packed >> 32,
                            )
                events.append(
                    dict(
                        kind="call",
                        site=hex(ins.address),
                        target=target,
                        direct=operands[0].type == CS_OP_IMM,
                        arguments=args + [fifth],
                        positionArguments=positions,
                    )
                )
            for key in VOLATILE:
                values.pop(key, None)
            values.pop("condition_flags", None)
            # Calls can overwrite any stack object passed by address. Keep only
            # pointers and constants in unescaped locals.
            escaped = [
                a[2]
                for a in args + [fifth]
                if isinstance(a, tuple) and a[:2] == ("pointer", "stack")
            ]
            if escaped:
                for key in list(values):
                    if (
                        isinstance(key, tuple)
                        and key[0] == "stack"
                        and any(key[1] >= p for p in escaped)
                    ):
                        values.pop(key, None)
            values["rax"] = ("call_result", hex(ins.address))
            continue
        result, destination = None, None
        if (
            mnemonic in {"mov", "movabs", "movzx", "movsxd", "movsx"}
            and len(operands) == 2
        ):
            destination = operands[0]
            result = read(ins, operands[1])
            if mnemonic in {"movsx", "movsxd"}:
                if isinstance(result, int):
                    bits = operands[1].size * 8
                    result = (
                        result - (1 << bits) if result & (1 << (bits - 1)) else result
                    )
                else:
                    result = None
        elif mnemonic == "lea":
            destination = operands[0]
            result = memory_address(ins, operands[1], values)
        elif mnemonic in {"add", "sub"} and len(operands) == 2:
            destination = operands[0]
            a, b = read(ins, destination), read(ins, operands[1])
            if operands[1].type == CS_OP_IMM:
                b = operands[1].imm
            if isinstance(b, int):
                result = add(a, b if mnemonic == "add" else -b)
        elif (
            mnemonic == "xor"
            and len(operands) == 2
            and operands[0].type == operands[1].type == CS_OP_REG
            and operands[0].reg == operands[1].reg
        ):
            destination = operands[0]
            result = 0
        elif mnemonic == "push":
            rsp = add(values.get("rsp"), -8)
            values["rsp"] = rsp
            if rsp is not None:
                values[("stack", rsp[2], 8)] = read(ins, operands[0])
            continue
        elif mnemonic == "pop":
            destination = operands[0]
            rsp = values.get("rsp")
            if rsp is not None:
                result = values.get(("stack", rsp[2], 8))
            values["rsp"] = add(rsp, 8)
        elif mnemonic == "ret":
            if collect:
                events.append(
                    dict(kind="return", site=hex(ins.address), value=values.get("rax"))
                )
            continue
        elif mnemonic in {"cmp", "test"}:
            compared = tuple(read(ins, o) for o in operands)
            values["condition_flags"] = (
                hex(ins.address),
                mnemonic,
                compared,
                ins.op_str,
            )
            if collect:
                events.append(
                    dict(
                        kind="comparison",
                        site=hex(ins.address),
                        operation=mnemonic,
                        values=list(compared),
                        assembly=ins.op_str,
                    )
                )
            continue
        elif mnemonic.startswith("j"):
            if collect:
                events.append(
                    dict(
                        kind="branch",
                        site=hex(ins.address),
                        operation=mnemonic,
                        target=(
                            hex(operands[0].imm)
                            if operands and operands[0].type == CS_OP_IMM
                            else None
                        ),
                        comparison=(
                            values.get("condition_flags") if mnemonic != "jmp" else None
                        ),
                        fallthrough=(
                            hex(ins.address + ins.size) if mnemonic != "jmp" else None
                        ),
                    )
                )
            continue
        # Invalidate all explicit/implicit written registers before applying a
        # recognized result. Partial writes cannot preserve a pointer.
        _, written = ins.regs_access()
        for identifier in written:
            name = register(ins, identifier)
            if name in {"eflags", "rflags"}:
                values.pop("condition_flags", None)
            if name != "rsp" or mnemonic not in {"pop"}:
                values.pop(name, None)
        if destination is None:
            # An unsupported memory write invalidates overlapping stack cells.
            if operands and operands[0].type == CS_OP_MEM and operands[0].access & 2:
                destination = operands[0]
            else:
                continue
        if destination.type == CS_OP_REG:
            if (
                result is not None
                and destination.size in {4, 8}
                and (
                    destination.size == 8
                    or isinstance(result, int)
                    or isinstance(result, tuple)
                    and result[0] == "call_result"
                )
            ):
                values[register(ins, destination.reg)] = (
                    result & ((1 << (destination.size * 8)) - 1)
                    if isinstance(result, int)
                    else result
                )
        elif destination.type == CS_OP_MEM:
            location = memory_address(ins, destination, values)
            if isinstance(location, tuple) and location[:2] == ("pointer", "stack"):
                for key in list(values):
                    if (
                        isinstance(key, tuple)
                        and key[0] == "stack"
                        and key[1] < location[2] + destination.size
                        and location[2] < key[1] + key[2]
                    ):
                        values.pop(key, None)
                if result is not None:
                    values[("stack", location[2], destination.size)] = result
            if collect and location is not None:
                events.append(
                    dict(
                        kind="store",
                        site=hex(ins.address),
                        destination=location,
                        value=result,
                        size=destination.size,
                    )
                )
    return {k: v for k, v in values.items() if v is not None}, events


def bind_native(native, address, control_flow, *, dispatcher=False):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM

    disassembler = Cs(CS_ARCH_X86, CS_MODE_64)
    disassembler.detail = True
    instructions = list(disassembler.disasm(native, address))
    blocks = {b["id"]: b for b in control_flow["blocks"]}
    # Analyze only actual bytes in the verified PE range. Callee tails in the
    # decompiler cannot extend this range or suppress valid in-range evidence.
    range_warnings = [
        b["id"]
        for b in blocks.values()
        if not address
        <= int(b["start"], 16)
        <= int(b["end"], 16)
        < address + len(native)
    ]
    by_address = {i.address: i for i in instructions}
    if address not in by_address:
        return dict(
            status="instruction_decode_requires_review", blocks={}, iterations=0
        )
    # Build direct branch edges from machine code, not the optimized high CFG.
    starts = {address}
    external_branches = []
    for ins in instructions:
        if ins.mnemonic.startswith("j"):
            if ins.operands[0].type == CS_OP_IMM and ins.operands[0].imm in by_address:
                starts.add(ins.operands[0].imm)
            elif ins.operands[0].type == CS_OP_IMM:
                target = ins.operands[0].imm
                if address <= target < address + len(native):
                    return dict(
                        status="branch_target_requires_review", blocks={}, iterations=0
                    )
                external_branches.append(
                    dict(
                        site=hex(ins.address),
                        target=hex(target),
                        operation=ins.mnemonic,
                    )
                )
            elif ins.operands[0].type != CS_OP_IMM:
                high = [b for b in blocks.values() if int(b["end"], 16) == ins.address]
                if len(high) != 1 or not high[0]["successors"]:
                    return dict(
                        status="indirect_jump_requires_review", blocks={}, iterations=0
                    )
                targets = [int(blocks[s]["start"], 16) for s in high[0]["successors"]]
                if any(target not in by_address for target in targets):
                    return dict(
                        status="indirect_jump_targets_unmatched",
                        blocks={},
                        iterations=0,
                    )
                starts.update(targets)
            if ins.address + ins.size in by_address:
                starts.add(ins.address + ins.size)
        if ins.mnemonic.startswith("ret") and ins.address + ins.size in by_address:
            starts.add(ins.address + ins.size)
    instruction_blocks = {}
    key = None
    for ins in instructions:
        if ins.address in starts:
            key = hex(ins.address)
            instruction_blocks[key] = []
        if key is not None:
            instruction_blocks[key].append(ins)
    native_blocks = {}
    indirect_boundary = []
    for key, seq in instruction_blocks.items():
        last = seq[-1]
        successors = []
        if last.mnemonic.startswith("j"):
            if last.operands[0].type == CS_OP_IMM:
                if last.operands[0].imm in starts:
                    successors.append(hex(last.operands[0].imm))
            else:
                high = [b for b in blocks.values() if int(b["end"], 16) == last.address]
                if len(high) == 1:
                    successors.extend(
                        hex(int(blocks[s]["start"], 16))
                        for s in high[0]["successors"]
                        if int(blocks[s]["start"], 16) in starts
                    )
                indirect_boundary.append(hex(last.address))
            if last.mnemonic != "jmp" and last.address + last.size in starts:
                successors.append(hex(last.address + last.size))
        elif not last.mnemonic.startswith("ret") and last.address + last.size in starts:
            successors.append(hex(last.address + last.size))
        native_blocks[key] = dict(successors=sorted(set(successors)))
    blocks = native_blocks
    entry = hex(address)
    initial = {
        "rdx": pointer("export"),
        "r8": pointer("position" if dispatcher else "command_work"),
        "r9": pointer("command_work" if dispatcher else "operator"),
        "rsp": pointer("stack"),
    }
    if dispatcher:
        initial[("stack", 0x28, 8)] = pointer("operator")
    predecessors = {k: set() for k in blocks}
    for k, b in blocks.items():
        for target in b["successors"]:
            predecessors[target].add(k)
    outgoing, incoming, pending, queued = {}, {}, deque([entry]), {entry}
    iterations, limit = 0, max(100, len(blocks) * 30)
    while pending and iterations < limit:
        key = pending.popleft()
        queued.discard(key)
        sources = [outgoing[p] for p in predecessors[key] if p in outgoing]
        if key == entry:
            sources.append(initial)
        if not sources:
            continue
        merged = {
            k: v
            for k, v in sources[0].items()
            if all(s.get(k) == v for s in sources[1:])
        }
        incoming[key] = merged
        result, _ = _transfer(instruction_blocks[key], merged)
        iterations += 1
        if key in outgoing:
            result = {
                k: v
                for k, v in result.items()
                if k in outgoing[key] and outgoing[key][k] == v
            }
        if outgoing.get(key) != result:
            outgoing[key] = result
            for target in blocks[key]["successors"]:
                if target not in queued:
                    pending.append(target)
                    queued.add(target)
    if pending:
        return dict(status="dataflow_not_converged", blocks={}, iterations=iterations)
    references = []
    from capstone import CS_OP_MEM

    for key in incoming:
        for ins in instruction_blocks[key]:
            for operand in ins.operands:
                if (
                    operand.type == CS_OP_MEM
                    and ins.reg_name(operand.mem.base) == "rip"
                    and not operand.mem.index
                ):
                    references.append(
                        dict(
                            site=hex(ins.address),
                            address=hex(ins.address + ins.size + operand.mem.disp),
                            size=operand.size,
                        )
                    )
    events_by_block = {
        k: _transfer(instruction_blocks[k], s, collect=True)[1]
        for k, s in incoming.items()
    }
    native_flow = []
    for key, events in events_by_block.items():
        operations = []
        for event in events:
            if event["kind"] == "call":
                operations.append(
                    dict(
                        address=event["site"],
                        opcode="CALL" if event["direct"] else "CALLIND",
                        inputs=[
                            dict(
                                offset=(
                                    hex(event["target"])
                                    if isinstance(event["target"], int)
                                    else ""
                                )
                            )
                        ],
                    )
                )
            if event["kind"] == "return":
                operations.append(
                    dict(address=event["site"], opcode="RETURN", inputs=[])
                )
            if event["kind"] == "branch":
                operations.append(
                    dict(
                        address=event["site"],
                        opcode="BRANCH" if event["operation"] == "jmp" else "CBRANCH",
                        inputs=[],
                    )
                )
        native_flow.append(
            dict(
                id=key,
                start=key,
                end=hex(instruction_blocks[key][-1].address),
                successors=[s for s in blocks[key]["successors"] if s in incoming],
                operations=operations,
            )
        )
    return dict(
        status=(
            "converged_partial_range_boundary"
            if range_warnings or external_branches
            else "converged"
        ),
        blocks=events_by_block,
        iterations=iterations,
        indirectJumpSites=indirect_boundary,
        memoryReferences=references,
        rangeBoundaryWarnings=range_warnings,
        externalBranches=external_branches,
        nativeControlFlow=dict(blocks=native_flow),
    )
