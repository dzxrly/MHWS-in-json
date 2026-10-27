"""One reviewed uint32-mod / signed-interval native formula, with no history defaults."""

from copy import deepcopy

from capstone import CS_OP_IMM, CS_OP_MEM, CS_OP_REG

from ..native.bindings import pointer, register

MOD_PREFIX = bytes.fromhex("89c14869c91f85eb5148c1e9256bc96429c8")
MAX_REMAINDER = bytes.fromhex("89c84869c01f85eb5148c1e8256bc06429c189c8")


def evaluate_interval(expression, context):
    """Return effective <= threshold, or None for absent/noninteger state."""
    values = [context.get(expression[key]) for key in ("drawKey", "maxKey", "minKey")]
    if any(
        type(value) is not int or not -0x80000000 <= value <= 0xFFFFFFFF
        for value in values
    ):
        return None
    draw, maximum, minimum = (value & 0xFFFFFFFF for value in values)
    maximum -= 0x100000000 if maximum & 0x80000000 else 0
    minimum -= 0x100000000 if minimum & 0x80000000 else 0
    remainder = draw % expression["modulus"]
    if minimum < remainder < maximum:
        remainder = (maximum & 0xFFFFFFFF) % expression["modulus"]
    return remainder <= expression["threshold"]


def validate_interval(expression):
    if any(
        not isinstance(expression.get(key), str) or not expression[key]
        for key in ("drawKey", "maxKey", "minKey")
    ):
        raise ValueError("前次随机区间公式缺少状态键")
    modulus, threshold = expression.get("modulus"), expression.get("threshold")
    if (
        type(modulus) is not int
        or not 0 < modulus <= 0xFFFFFFFF
        or type(threshold) is not int
        or not 0 <= threshold < modulus
    ):
        raise ValueError("前次随机区间公式的取余或阈值无效")


def _pattern(machine, history, call):
    """Recognize exact scalar arithmetic; addresses/register Param bases relocate."""
    instructions = machine.ins
    address = call.address + call.size
    native = []

    def take_bytes(expected):
        nonlocal address
        consumed = b""
        while len(consumed) < len(expected):
            ins = instructions.get(address)
            if ins is None:
                return False
            consumed += ins.bytes
            native.append(ins)
            address += ins.size
        return consumed == expected

    if not take_bytes(MOD_PREFIX):
        return None
    ins = instructions.get(address)
    pointer_load = None
    if ins is not None and ins.mnemonic == "mov" and ins.operands[0].size == 8:
        op = ins.operands
        if not (
            op[0].type == CS_OP_REG
            and op[1].type == CS_OP_MEM
            and ins.reg_name(op[1].mem.base) == "rsp"
            and not op[1].mem.index
        ):
            return None
        pointer_load = ins
        native.append(ins)
        address += ins.size
        ins = instructions.get(address)
    if ins is None or ins.mnemonic != "mov":
        return None
    op = ins.operands
    if not (
        len(op) == 2
        and op[0].type == CS_OP_REG
        and ins.reg_name(op[0].reg) == "ecx"
        and op[1].type == CS_OP_MEM
        and op[1].size == 4
        and not op[1].mem.index
    ):
        return None
    maximum = ins
    max_offset, base = op[1].mem.disp, op[1].mem.base
    name = history.fields.get(max_offset, "")
    if not name.startswith("BefoRandomMax_"):
        return None
    suffix = name.rsplit("_", 1)[1]
    minimum_fields = [
        off
        for off, field in history.fields.items()
        if field == "BefoRandomMin_" + suffix
    ]
    if len(minimum_fields) != 1 or set(history.fields) != {
        max_offset,
        minimum_fields[0],
    }:
        return None
    min_offset = minimum_fields[0]
    native.append(ins)
    address += ins.size
    if not take_bytes(bytes.fromhex("39c8")):
        return None
    upper = instructions.get(address)
    if upper is None or upper.mnemonic != "jge" or upper.operands[0].type != CS_OP_IMM:
        return None
    native.append(upper)
    address += upper.size
    minimum = instructions.get(address)
    if minimum is None or minimum.mnemonic != "cmp":
        return None
    op = minimum.operands
    if not (
        len(op) == 2
        and op[0].type == CS_OP_REG
        and minimum.reg_name(op[0].reg) == "eax"
        and op[1].type == CS_OP_MEM
        and op[1].size == 4
        and op[1].mem.base == base
        and not op[1].mem.index
        and op[1].mem.disp == min_offset
    ):
        return None
    native.append(minimum)
    address += minimum.size
    lower = instructions.get(address)
    if (
        lower is None
        or lower.mnemonic != "jle"
        or lower.operands[0].type != CS_OP_IMM
        or lower.operands[0].imm != upper.operands[0].imm
    ):
        return None
    native.append(lower)
    address += lower.size
    if not take_bytes(MAX_REMAINDER) or address != upper.operands[0].imm:
        return None
    threshold = instructions.get(address)
    if threshold is None or threshold.mnemonic != "cmp":
        return None
    op = threshold.operands
    if not (
        len(op) == 2
        and op[0].type == CS_OP_REG
        and threshold.reg_name(op[0].reg) == "eax"
        and op[1].type == CS_OP_IMM
        and 0 <= op[1].imm < 100
    ):
        return None
    native.append(threshold)
    branch = instructions.get(address + threshold.size)
    if (
        branch is None
        or branch.mnemonic != "jbe"
        or branch.operands[0].type != CS_OP_IMM
    ):
        return None
    native.append(branch)
    return dict(
        randomSite=call.address,
        maxOffset=max_offset,
        minOffset=min_offset,
        maxRead=maximum.address,
        minRead=minimum.address,
        prefixEnd=maximum.address,
        threshold=op[1].imm,
        branches={True: branch.operands[0].imm, False: branch.address + branch.size},
        nativeProof=dict(
            kind="uint32_mod_signed_open_interval_remap",
            nativeMethod={
                k: machine.row[k] for k in ("type", "method", "address", "end")
            },
            instructions=[
                dict(address=hex(x.address), nativeBytes=x.bytes.hex())
                for x in [call, *native]
            ],
            modulus=100,
            guard="int32(Min) < uint32(draw)%100 < int32(Max)",
            remap="guard ? uint32(Max)%100 : uint32(draw)%100",
            threshold=op[1].imm,
        ),
    )


def prepare_history_formula(machine, history, *, enabled=None):
    """Opt-in only after every discovered private read belongs to a matched block."""
    if enabled is None:
        from .monster_rules import hooks

        policies = [
            p
            for hook in hooks("table_history_policy")
            if (p := hook(machine.row)) is not None
        ]
        if len(policies) > 1:
            raise ValueError("私有随机公式策略不唯一")
        enabled = bool(policies and policies[0].get("formula"))
    if not enabled:
        return False
    if history is None or history.local_pairs or not history.complete_discovery:
        raise ValueError("已审核随机公式缺少完整单区间读取证据")
    specs = {
        ins.address: spec
        for ins in machine.ins.values()
        if ins.mnemonic == "call"
        and (spec := _pattern(machine, history, ins)) is not None
    }
    covered = {}
    for spec in specs.values():
        covered[spec["maxRead"]] = {spec["maxOffset"]}
        covered[spec["minRead"]] = {spec["minOffset"]}
    if not specs or not history.read_sites or covered != history.read_sites:
        raise ValueError("已审核随机公式的原生形状或全部Param读取位置变化")
    history.formula_specs = specs
    history.formula_enabled = True
    return True


def recover_history_formula(machine, ins, event, state):
    """Return two proven fixed-write continuations at their first actual call."""
    from .machine import Boundary, Machine

    history = machine.table_history
    if history is None or not history.formula_enabled:
        return None
    spec = history.formula_specs.get(ins.address)
    if spec is None or event["target"] != ("random_generator",):
        return None
    working = machine.complete_call(state, event, None)
    address = ins.address + ins.size
    while address != spec["prefixEnd"]:
        operation = machine.ins[address]
        address = machine.step(operation, working)
    maximum = machine.ins[spec["maxRead"]]
    minimum = machine.ins[spec["minRead"]]
    if machine.address(maximum, maximum.operands[1], working) != pointer(
        history.owner, spec["maxOffset"]
    ) or machine.address(minimum, minimum.operands[1], working) != pointer(
        history.owner, spec["minOffset"]
    ):
        raise ValueError("已审核随机公式的Param对象绑定变化")
    working["regs"]["rax"] = working["regs"]["rcx"] = None
    working["flags"] = None
    if working.get("history_updates"):
        raise ValueError("进入随机公式前还有未输出的历史写入")

    class Probe(Machine):
        def load(self, location, size, selected):
            if isinstance(location, tuple) and location[:2] == (
                "pointer",
                history.owner,
            ):
                fields = history.private_field(location, size)
                if (
                    not fields
                    or len(fields) * 4 != size
                    or any(off not in self.written for off, _ in fields)
                ):
                    raise Boundary("branch rereads an old private value")
            return Machine.load(self, location, size, selected)

        def write(self, operation, operand, value, selected):
            if operand.type == CS_OP_MEM:
                location = self.address(operation, operand, selected)
                fields = history.private_field(location, operand.size)
                if fields:
                    if type(value) is not int or sum(4 for _ in fields) != operand.size:
                        raise Boundary(
                            "private write is not a complete fixed Int32 store"
                        )
                    self.written.update(off for off, _ in fields)
                elif not (
                    isinstance(location, tuple) and location[:2] == ("pointer", "stack")
                ):
                    raise Boundary("branch has an unreviewed external write")
            return Machine.write(self, operation, operand, value, selected)

    buckets = []
    for truth, start in spec["branches"].items():
        probe = object.__new__(Probe)
        probe.__dict__ = dict(machine.__dict__)
        probe.written = set()
        selected = deepcopy(working)
        address, dirty, writes, path, seen = start, {"rax", "rcx"}, [], [], set()
        try:
            for _ in range(96):
                if address in seen or address not in probe.ins:
                    raise Boundary("branch loops or leaves the method")
                seen.add(address)
                operation = probe.ins[address]
                if operation.mnemonic == "call":
                    call = probe.event(operation, selected)
                    if (
                        set(history.fields) != probe.written
                        or call["target"] is None
                        or any(arg is None for arg in call["arguments"])
                    ):
                        raise Boundary(
                            "fixed writes or actual call arguments are incomplete"
                        )
                    buckets.append(
                        dict(
                            truth=truth,
                            address=address,
                            state=selected,
                            writes=writes,
                            nativePath=path,
                        )
                    )
                    break
                if operation.mnemonic not in {
                    "mov",
                    "movabs",
                    "lea",
                    "xor",
                    "add",
                    "sub",
                    "jmp",
                }:
                    raise Boundary("branch is not a reviewed fixed-write prefix")
                reads, _ = operation.regs_access()
                clearing = (
                    operation.mnemonic == "xor"
                    and operation.operands[0].type
                    == operation.operands[1].type
                    == CS_OP_REG
                    and operation.operands[0].reg == operation.operands[1].reg
                    and operation.operands[0].size >= 4
                )
                if dirty & {register(operation, reg) for reg in reads} and not clearing:
                    raise Boundary("effective remainder/old maximum is still live")
                path.append(
                    dict(address=hex(address), nativeBytes=operation.bytes.hex())
                )
                address = probe.step(operation, selected)
                if (
                    operation.operands[0].type == CS_OP_REG
                    and operation.operands[0].size >= 4
                ):
                    dirty.discard(register(operation, operation.operands[0].reg))
                updates = selected.pop("history_updates", {})
                if updates:
                    writes.append(
                        dict(site=hex(operation.address), stateUpdates=updates)
                    )
            else:
                raise Boundary("branch exceeded fixed-write prefix bound")
        except Boundary as error:
            raise ValueError(
                "已审核随机公式后继未能证明独立于输入历史：" + str(error)
            ) from error
    return dict(
        expression=dict(
            kind="table_history_interval",
            drawKey=f"random_uint32_mod_100:{hex(ins.address)}",
            maxKey=history.key(spec["maxOffset"]),
            minKey=history.key(spec["minOffset"]),
            modulus=100,
            threshold=spec["threshold"],
        ),
        inputDefinitions=history.input_definitions(),
        nativeProof=deepcopy(spec["nativeProof"]),
        buckets=buckets,
    )
