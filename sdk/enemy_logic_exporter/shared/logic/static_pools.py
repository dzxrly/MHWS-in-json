"""Recover version-specific initializer pairs without assigning probabilities."""

import re
import hashlib
from ..native.bindings import _transfer, memory_address, pointer, register, VOLATILE

# Current-version slot for System.ValueTuple<UInt32, Int32>[] pool arrays.
# The allocator receives the array length in r8 and the dimension count in r9.
PACKED_POOL_ARRAY_TYPE_SLOT = 0x1547535A0
ARRAY_ALLOCATOR = 0x14B030670


def initializer_pools(record):
    text = record["code"].replace("\r", "")
    previous = 0
    pools = []
    for match in re.finditer(r"FUN_143801f50\((0x[0-9a-f]+),", text):
        pairs = re.findall(
            r"(?:FUN_143928820|func_0x000143928820|mhws_c49d22bf7e7e9cbe)\s*\(.*?,.*?,\s*(0x[0-9a-f]+|\d+),\s*(0x[0-9a-f]+|\d+)\s*\)\s*;",
            text[previous : match.start()],
            re.S,
        )
        previous = match.end()
        if pairs:
            pools.append(
                dict(
                    address=match[1],
                    entries=[
                        dict(nativeKey=int(a, 0), weight=int(b, 0)) for a, b in pairs
                    ],
                    initializerEvidence={
                        k: record[k]
                        for k in ("type", "method", "address", "end", "nativeSha256")
                    },
                    status="initialization_constants_only",
                    keyMeaningReviewed=False,
                    runtimeCandidateFilteringReviewed=False,
                )
            )
    return pools


def native_initializer_pools(native, address, record, *, read_memory=None):
    """Read constant constructor/copy arguments even when C has bad callee tails."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    chunks = []
    current = []
    instructions = list(decoder.disasm(native, address))
    for instruction in instructions:
        current.append(instruction)
        if instruction.mnemonic.startswith(("j", "ret")):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    pools = []
    pairs = []
    for chunk in chunks:
        _, events = _transfer(chunk, {"rsp": pointer("stack")}, collect=True)
        for event in events:
            if event["kind"] != "call" or not event["direct"]:
                continue
            if event["target"] == 0x143928820:
                key, weight = event["arguments"][2:4]
                if (
                    isinstance(key, int)
                    and isinstance(weight, int)
                    and 0 <= key <= 0xFFFFFFFF
                    and 0 <= weight <= 0x7FFFFFFF
                ):
                    pairs.append(
                        dict(
                            nativeKey=key, weight=weight, constructorSite=event["site"]
                        )
                    )
                else:
                    pairs = []
            elif event["target"] == 0x143801F50:
                destination = event["arguments"][0]
                if isinstance(destination, int) and pairs:
                    pools.append(
                        dict(
                            address=hex(destination),
                            entries=pairs,
                            copySite=event["site"],
                            initializerEvidence={
                                k: record[k]
                                for k in (
                                    "type",
                                    "method",
                                    "address",
                                    "end",
                                    "nativeSha256",
                                )
                            },
                            status="native_initialization_constants_only",
                            keyMeaningReviewed=False,
                            runtimeCandidateFilteringReviewed=False,
                        )
                    )
                pairs = []
        # Do not group constructor calls across an unresolved branch. A pool
        # association requires one straight-line instruction segment.
        if chunk[-1].mnemonic.startswith(("j", "ret")):
            pairs = []
    pools.extend(_packed_initializer_pools(instructions, record, read_memory))
    return pools


def _initializer_evidence(record):
    return {
        key: record[key] for key in ("type", "method", "address", "end", "nativeSha256")
    }


def _reference_assignment(instructions, start, values):
    """Recognize the checked AddRef/atomic replace/Release pattern exactly.

    The equality fast path leaves the same completed allocation at this static
    slot. The retry loop only repeats cmpxchg. Other conditional branches do
    not authorize carrying array identities or constructor constants forward.
    """
    from capstone import CS_OP_IMM, CS_OP_MEM, CS_OP_REG

    first = instructions[start]
    if first.mnemonic != "cmp" or len(first.operands) != 2:
        return None
    memory, source = first.operands
    if memory.type != CS_OP_MEM or source.type != CS_OP_REG or memory.size != 8:
        return None
    destination = memory_address(first, memory, values)
    array = values.get(register(first, source.reg))
    if not isinstance(destination, int) or not _is_array(array):
        return None
    sequence = instructions[start + 1 : start + 32]
    if not sequence or sequence[0].mnemonic not in ("je", "jz"):
        return None
    end_address = sequence[0].operands[0].imm
    block = []
    for index in range(start + 1, min(start + 33, len(instructions))):
        ins = instructions[index]
        if ins.address == end_address:
            break
        block.append(ins)
    else:
        return None
    if not block or block[-1].mnemonic not in ("call", "jmp"):
        return None
    semantic_block = [ins for ins in block if ins.mnemonic != "vzeroupper"]
    operations = [ins.mnemonic for ins in semantic_block]
    expected = [
        "je",
        "mov",
        "mov",
        "call",
        "mov",
        "mov",
        "lock cmpxchg",
        "jne",
        "test",
        "je",
        "call",
    ]
    # An allocation already held in a nonvolatile register needs no extra move.
    expected_short = [
        "je",
        "mov",
        "call",
        "mov",
        "mov",
        "lock cmpxchg",
        "jne",
        "test",
        "je",
        "call",
    ]
    tail_release = operations[-1] == "jmp"
    if tail_release:
        prefix = (
            expected[:-1]
            if operations[: len(expected) - 1] == expected[:-1]
            else expected_short[:-1]
        )
        if operations[: len(prefix)] != prefix:
            return None
        epilogue = semantic_block[len(prefix) : -1]
        if (
            not epilogue
            or epilogue[0].mnemonic != "add"
            or any(ins.mnemonic != "pop" for ins in epilogue[1:])
        ):
            return None
        adjustment = epilogue[0].operands
        if (
            adjustment[0].type != CS_OP_REG
            or register(epilogue[0], adjustment[0].reg) != "rsp"
            or adjustment[1].type != CS_OP_IMM
        ):
            return None
        if (
            block[-1].operands[0].type != CS_OP_IMM
            or block[-1].operands[0].imm != 0x14B0099E0
        ):
            return None
        branch_to_end = semantic_block[len(prefix) - 1]
    else:
        if operations not in (expected, expected_short):
            return None
        branch_to_end = semantic_block[-2]
    calls = [ins for ins in block if ins.mnemonic == "call"]
    if any(ins.operands[0].type != CS_OP_IMM for ins in calls):
        return None
    if [ins.operands[0].imm for ins in calls] != (
        [0x14B007BD0] if tail_release else [0x14B007BD0, 0x14B0099E0]
    ):
        return None
    atomic = next(ins for ins in block if ins.mnemonic == "lock cmpxchg")
    if memory_address(atomic, atomic.operands[0], values) != destination:
        return None
    loop_load = semantic_block[semantic_block.index(calls[0]) + 1]
    if (
        loop_load.operands[0].type != CS_OP_REG
        or register(loop_load, loop_load.operands[0].reg) != "rcx"
        or loop_load.operands[1].type != CS_OP_MEM
        or memory_address(loop_load, loop_load.operands[1], values) != destination
    ):
        return None
    compare_old = semantic_block[semantic_block.index(loop_load) + 1]
    if [register(compare_old, operand.reg) for operand in compare_old.operands] != [
        "rax",
        "rcx",
    ]:
        return None
    local = dict(values)
    for ins in block[: block.index(calls[0])]:
        local, _ = _transfer([ins], local, collect=True)
    if (
        local.get("rcx") != array
        or local.get(register(atomic, atomic.operands[1].reg)) != array
    ):
        return None
    retry = semantic_block[semantic_block.index(atomic) + 1]
    if retry.operands[0].imm != loop_load.address:
        return None
    if branch_to_end.operands[0].imm != end_address:
        return None
    written = set()
    for ins in block:
        _, ids = ins.regs_access()
        written.update(register(ins, identifier) for identifier in ids)
    return dict(
        nextIndex=index,
        destination=destination,
        array=array,
        assignmentSite=hex(atomic.address),
        written=written,
    )


def _is_array(value):
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and value[0] == "pointer"
        and isinstance(value[1], tuple)
        and value[1][0] == "packed_pool_array"
    )


def _packed_initializer_pools(instructions, record, read_memory):
    """Follow complete packed arrays and prove their individual static slots."""
    from capstone import CS_OP_IMM, CS_OP_MEM, CS_OP_REG

    values = {"rsp": pointer("stack")}
    arrays, pools = {}, []
    vectors = {}
    index = 0

    def publish(array, destination, site):
        definition = arrays.get(array[1])
        if definition is None or not definition["valid"] or array[2] != 0:
            return
        length, cells = definition["length"], definition["cells"]
        if set(cells) != set(range(length * 8)) or any(
            value is None for value in cells.values()
        ):
            return
        entries = []
        for offset in range(0, length * 8, 8):
            packed = int.from_bytes(
                bytes(cells[offset + byte] for byte in range(8)), "little"
            )
            weight = packed >> 32
            if weight > 0x7FFFFFFF:
                return
            entries.append(
                dict(
                    nativeKey=packed & 0xFFFFFFFF,
                    weight=weight,
                    storeSites=sorted(definition["sites"][offset // 8]),
                )
            )
        pools.append(
            dict(
                address=hex(destination),
                entries=entries,
                allocationSite=definition["allocationSite"],
                assignmentSite=site,
                arrayLength=length,
                elementStride=8,
                elementType="System.ValueTuple<System.UInt32,System.Int32>",
                arrayTypeSlot=hex(PACKED_POOL_ARRAY_TYPE_SLOT),
                pairLayout="little-endian uint32 nativeKey followed by int32 nonnegative weight",
                initializerEvidence=_initializer_evidence(record),
                constantEvidence=list(definition["constantEvidence"].values()),
                status="native_initialization_constants_only",
                keyMeaningReviewed=False,
                runtimeCandidateFilteringReviewed=False,
            )
        )

    def write(array, offset, raw, size, site, constant=None):
        definition = arrays.get(array[1])
        if definition is None:
            return
        position = array[2] + offset - 0x20
        if position < 0 or position + size > definition["length"] * 8:
            definition["valid"] = False
            return
        for byte in range(size):
            definition["cells"][position + byte] = (
                raw[byte] if raw is not None else None
            )
            definition["sites"][(position + byte) // 8].add(site)
        if constant is not None:
            definition["constantEvidence"][constant["address"]] = constant

    while index < len(instructions):
        ins = instructions[index]
        assignment = _reference_assignment(instructions, index, values)
        if assignment is not None:
            publish(
                assignment["array"],
                assignment["destination"],
                assignment["assignmentSite"],
            )
            for key in assignment["written"] | VOLATILE:
                values.pop(key, None)
            vectors.clear()
            index = assignment["nextIndex"]
            continue
        before = dict(values)
        values, events = _transfer([ins], values, collect=True)
        operands = ins.operands
        vector_store_handled = False
        _, written_registers = ins.regs_access()
        for identifier in written_registers:
            name = ins.reg_name(identifier)
            if name.startswith(("xmm", "ymm", "zmm")):
                vectors.pop(name[3:], None)
        if ins.mnemonic == "vzeroupper":
            vectors.clear()
        vector_store_handled = False
        # Preserve identity of a type-pointer load without inventing its value.
        if (
            ins.mnemonic == "mov"
            and len(operands) == 2
            and operands[0].type == CS_OP_REG
            and operands[0].size == 8
            and operands[1].type == CS_OP_MEM
        ):
            source = memory_address(ins, operands[1], before)
            if isinstance(source, int):
                values[register(ins, operands[0].reg)] = ("native_static_value", source)
        if (
            ins.mnemonic
            in (
                "vmovaps",
                "vmovups",
                "vmovdqa",
                "vmovdqu",
                "movaps",
                "movups",
                "movdqa",
                "movdqu",
            )
            and len(operands) == 2
        ):
            destination, source = operands
            if destination.type == CS_OP_REG:
                name = ins.reg_name(destination.reg)[3:]
                vectors.pop(name, None)
                location = (
                    memory_address(ins, source, before)
                    if source.type == CS_OP_MEM
                    else None
                )
                if isinstance(location, int) and read_memory is not None:
                    raw = read_memory(location, source.size)
                    if len(raw) == source.size:
                        vectors[name] = (
                            raw,
                            dict(
                                type="native.constant",
                                method="packed_weighted_indices",
                                address=hex(location),
                                end=hex(location + len(raw)),
                                nativeSha256=hashlib.sha256(raw).hexdigest(),
                            ),
                        )
            elif destination.type == CS_OP_MEM and source.type == CS_OP_REG:
                location = memory_address(ins, destination, before)
                if _is_array(location):
                    data = vectors.get(ins.reg_name(source.reg)[3:])
                    write(
                        pointer(location[1]),
                        location[2],
                        data[0] if data else None,
                        destination.size,
                        hex(ins.address),
                        data[1] if data else None,
                    )
                    vector_store_handled = True
                    vector_store_handled = True
        for event in events:
            if event["kind"] == "call":
                if event["direct"] and event["target"] == ARRAY_ALLOCATOR:
                    _, type_pointer, length, dimension, _ = event["arguments"]
                    if (
                        type_pointer
                        == ("native_static_value", PACKED_POOL_ARRAY_TYPE_SLOT)
                        and type(length) is int
                        and 0 < length <= 2048
                        and dimension == 1
                    ):
                        owner = ("packed_pool_array", event["site"])
                        arrays[owner] = dict(
                            length=length,
                            cells={},
                            sites=[set() for _ in range(length)],
                            valid=True,
                            allocationSite=event["site"],
                            constantEvidence={},
                        )
                        values["rax"] = pointer(owner)
                else:
                    for arg in event["arguments"]:
                        if _is_array(arg) and arg[1] in arrays:
                            arrays[arg[1]]["valid"] = False
                vectors.clear()
            elif event["kind"] == "store":
                if vector_store_handled:
                    continue
                if vector_store_handled:
                    continue
                destination, value = event["destination"], event["value"]
                if _is_array(destination):
                    raw = (
                        (value & ((1 << (8 * event["size"])) - 1)).to_bytes(
                            event["size"], "little"
                        )
                        if type(value) is int
                        else None
                    )
                    write(
                        pointer(destination[1]),
                        destination[2],
                        raw,
                        event["size"],
                        event["site"],
                    )
                elif (
                    isinstance(destination, int)
                    and _is_array(value)
                    and event["size"] == 8
                ):
                    publish(value, destination, event["site"])
        if ins.mnemonic.startswith("j") or ins.mnemonic == "ret":
            values = {"rsp": values.get("rsp", pointer("stack"))}
            vectors.clear()
            for array in arrays.values():
                array["valid"] = False
        index += 1
    return pools
