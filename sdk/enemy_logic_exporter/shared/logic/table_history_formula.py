"""One reviewed uint32-mod / signed-interval native formula, with no history defaults."""

from copy import deepcopy

from capstone import CS_OP_IMM, CS_OP_MEM, CS_OP_REG

from ..native.bindings import pointer, register

MOD_PREFIX = bytes.fromhex("89c14869c91f85eb5148c1e9256bc96429c8")
MAX_REMAINDER = bytes.fromhex("89c84869c01f85eb5148c1e8256bc06429c189c8")
MOD_PREFIX_110 = bytes.fromhex("89c1d1e94869c995204f0948c1e9216bc96e29c8")
MOD_PREFIX_90 = bytes.fromhex("89c1d1e9bab7600bb6480fafd148c1ea256bca5a29c8")


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
    """Prove the scalar interval, including flag-preserving compiler scheduling."""
    instructions = machine.ins
    native = {}
    address = call.address + call.size

    def remember(ins):
        native[ins.address] = ins
        return ins.address + ins.size

    def take_bytes(at, expected):
        consumed = b""
        while len(consumed) < len(expected):
            ins = instructions.get(at)
            if ins is None:
                return None
            consumed += ins.bytes
            at = remember(ins)
        return at if consumed == expected else None

    def safe(ins, protected=()):
        if ins is None or ins.mnemonic not in {"mov", "movabs", "lea"}:
            return False
        if ins.operands[0].type != CS_OP_REG:
            return False
        reads, writes = ins.regs_access()
        # An inserted instruction may not consume or overwrite the formula.
        return not set(protected) & {register(ins, r) for r in (*reads, *writes)}

    def seek(at, predicate, protected=()):
        for _ in range(9):
            ins = instructions.get(at)
            if ins is None:
                return None
            if predicate(ins):
                return ins
            if not safe(ins, protected):
                return None
            at = remember(ins)
        return None

    modulus = None
    for divisor, expected in (
        (100, MOD_PREFIX),
        (110, MOD_PREFIX_110),
        (90, MOD_PREFIX_90),
    ):
        matched = take_bytes(address, expected)
        if matched is not None:
            modulus, address = divisor, matched
            break
    if modulus is None:
        return None

    def is_max(ins):
        op = ins.operands
        return (
            ins.mnemonic == "mov"
            and len(op) == 2
            and op[0].type == CS_OP_REG
            and op[0].size == 4
            and register(ins, op[0].reg) not in {"rax", "rsp", "rip"}
            and op[1].type == CS_OP_MEM
            and op[1].size == 4
            and not op[1].mem.index
            and history.fields.get(op[1].mem.disp, "").startswith("BefoRandomMax_")
        )

    maximum = seek(address, is_max, {"rax"})
    if maximum is None:
        return None
    prefix_end = maximum.address
    max_offset = maximum.operands[1].mem.disp
    max_reg = maximum.reg_name(maximum.operands[0].reg)
    max_root = register(maximum, maximum.operands[0].reg)
    suffix = history.fields[max_offset].rsplit("_", 1)[1]
    minimum_fields = [
        o for o, n in history.fields.items() if n == "BefoRandomMin_" + suffix
    ]
    if len(minimum_fields) != 1 or set(history.fields) != {
        max_offset,
        minimum_fields[0],
    }:
        return None
    min_offset = minimum_fields[0]
    address = remember(maximum)
    comparison = seek(
        address,
        lambda x: x.mnemonic == "cmp" and x.op_str == "eax, " + max_reg,
        {"rax", max_root},
    )
    if comparison is None:
        return None
    address = remember(comparison)
    upper = seek(address, lambda x: x.mnemonic == "jge", {"rax", max_root})
    if upper is None or upper.operands[0].type != CS_OP_IMM:
        return None
    address = remember(upper)

    def is_min(ins):
        op = ins.operands
        return (
            ins.mnemonic == "cmp"
            and len(op) == 2
            and op[0].type == CS_OP_REG
            and ins.reg_name(op[0].reg) == "eax"
            and op[1].type == CS_OP_MEM
            and op[1].size == 4
            and not op[1].mem.index
            and op[1].mem.disp == min_offset
        )

    minimum = seek(address, is_min, {"rax", max_root})
    if minimum is None:
        return None
    address = remember(minimum)
    lower = seek(address, lambda x: x.mnemonic == "jle", {"rax", max_root})
    if lower is None or lower.operands[0].type != CS_OP_IMM:
        return None
    address = remember(lower)
    remap_start = address
    # Keep the exact unsigned reciprocal arithmetic; only the proven Max
    # register changes. No signed division or sample-derived modulo is accepted.
    expected = [
        ("mov", "eax, " + max_reg),
        ("imul", "rax, rax, 0x51eb851f"),
        ("shr", "rax, 0x25"),
        ("imul", "eax, eax, 0x64"),
        ("sub", max_reg + ", eax"),
        ("mov", "eax, " + max_reg),
    ]
    if modulus == 110:
        expected = [
            ("mov", "eax, " + max_reg),
            ("shr", "eax, 1"),
            ("imul", "rax, rax, 0x94f2095"),
            ("shr", "rax, 0x21"),
            ("imul", "eax, eax, 0x6e"),
            ("sub", max_reg + ", eax"),
            ("mov", "eax, " + max_reg),
        ]
    elif modulus == 90:
        if max_root == "rdx":
            return None
        expected = [
            ("mov", "eax, " + max_reg),
            ("shr", "eax, 1"),
            ("mov", "edx, 0xb60b60b7"),
            ("imul", "rdx, rax"),
            ("shr", "rdx, 0x25"),
            ("imul", "eax, edx, 0x5a"),
            ("sub", max_reg + ", eax"),
            ("mov", "eax, " + max_reg),
        ]
    for mnemonic, operands in expected:
        ins = instructions.get(address)
        if ins is None or (ins.mnemonic, ins.op_str) != (mnemonic, operands):
            return None
        address = remember(ins)

    def threshold(ins):
        op = ins.operands
        return (
            ins.mnemonic == "cmp"
            and len(op) == 2
            and op[0].type == CS_OP_REG
            and ins.reg_name(op[0].reg) == "eax"
            and op[1].type == CS_OP_IMM
            and 0 <= op[1].imm < modulus
        )

    def join(at):
        seen = set()
        for _ in range(16):
            if at in seen:
                return None
            seen.add(at)
            ins = instructions.get(at)
            if ins is None:
                return None
            if threshold(ins):
                return at
            if ins.mnemonic == "jmp" and ins.operands[0].type == CS_OP_IMM:
                remember(ins)
                at = ins.operands[0].imm
            elif safe(ins, {"rax", max_root}):
                at = remember(ins)
            else:
                return None
        return None

    joins = [join(x) for x in (upper.operands[0].imm, lower.operands[0].imm, address)]
    if None in joins or len(set(joins)) != 1:
        return None
    threshold_start = joins[0]
    splits, leaves = [], []
    address = threshold_start
    for _ in range(16):
        comparison = instructions.get(address)
        if comparison is None or not threshold(comparison):
            return None
        value = comparison.operands[1].imm
        if splits and value <= splits[-1]["threshold"]:
            return None
        address = remember(comparison)
        branch = seek(address, lambda x: x.mnemonic == "jbe", {"rax"})
        if branch is None or branch.operands[0].type != CS_OP_IMM:
            return None
        address = remember(branch)
        splits.append(
            dict(threshold=value, compare=comparison.address, branch=branch.address)
        )
        leaves.append(branch.operands[0].imm)
        following = instructions.get(address)
        if following is None:
            return None
        if not threshold(following):
            leaves.append(address)
            break
    else:
        return None
    return dict(
        randomSite=call.address,
        modulus=modulus,
        maxOffset=max_offset,
        minOffset=min_offset,
        maxRead=maximum.address,
        minRead=minimum.address,
        prefixEnd=prefix_end,
        threshold=splits[0]["threshold"],
        thresholdStart=threshold_start,
        maxRegister=max_root,
        upper=upper.address,
        lower=lower.address,
        remapStart=remap_start,
        splits=splits,
        leaves=leaves,
        branches={True: leaves[0], False: leaves[-1]},
        nativeProof=dict(
            kind="uint32_mod_signed_open_interval_remap",
            nativeMethod={
                k: machine.row[k] for k in ("type", "method", "address", "end")
            },
            instructions=[
                dict(address=hex(x.address), nativeBytes=x.bytes.hex())
                for x in [call, *[native[k] for k in sorted(native)]]
            ],
            modulus=modulus,
            guard=f"int32(Min) < uint32(draw)%{modulus} < int32(Max)",
            remap=f"guard ? uint32(Max)%{modulus} : uint32(draw)%{modulus}",
            thresholds=[s["threshold"] for s in splits],
            threshold=splits[0]["threshold"],
        ),
    )


def prepare_history_formula(machine, history, *, enabled=None):
    """Opt in only when every discovered private read has a proven interval."""
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
    if history is None or not history.complete_discovery or history.escaped_sites:
        raise ValueError("已审核随机公式缺少完整区间读取证据")
    specs, covered = {}, {}
    pairs = history.local_pairs or [history]
    for pair in pairs:
        if pair.escaped_sites:
            raise ValueError("私有Param逃逸，不能投影其历史字段")
        pair_specs = {
            ins.address: spec
            for ins in machine.ins.values()
            if ins.mnemonic == "call"
            and (spec := _pattern(machine, pair, ins)) is not None
        }
        pair_covered = {}
        for spec in pair_specs.values():
            pair_covered[spec["maxRead"]] = {spec["maxOffset"]}
            pair_covered[spec["minRead"]] = {spec["minOffset"]}
            spec["history"] = pair
        if not pair_specs or not pair.read_sites or pair_covered != pair.read_sites:
            raise ValueError("已审核随机公式的原生形状或全部Param读取位置变化")
        if specs.keys() & pair_specs.keys():
            raise ValueError("同一随机调用对应多组私有区间")
        specs.update(pair_specs)
        covered.update(pair_covered)
    if covered != history.read_sites:
        raise ValueError("已审核随机公式的全部Param读取位置变化")
    for pair in pairs:
        pair.formula_enabled = True
    history.formula_specs = specs
    history.formula_enabled = True
    return True


def recover_history_formula(machine, ins, event, state):
    """Keep one draw and prove each real continuation without skipping checks."""
    from .machine import Boundary, Machine

    manager = machine.table_history
    if manager is None or not manager.formula_enabled:
        return None
    spec = manager.formula_specs.get(ins.address)
    if spec is None or event["target"] != ("random_generator",):
        return None
    history = spec["history"]

    def project(selected):
        # Every discovered read is covered by an explicit formula input. Keep
        # its real value in JSON persistent state, rather than accumulating a
        # Cartesian product of unrelated local pairs in native machine memory.
        selected = deepcopy(selected)
        for key in list(selected["mem"]):
            owner, offset, size = key
            if owner == manager.owner and any(
                offset < off + 4 and off < offset + size for off in manager.fields
            ):
                del selected["mem"][key]
        return selected

    entry_state = project(state)
    initial = machine.complete_call(entry_state, event, None)
    initial["regs"]["rax"] = None
    if initial.get("history_updates"):
        raise ValueError("进入随机公式前还有未输出的历史写入")

    # Execute all three guard paths using unknown Int32 fields, retaining actual
    # flag-preserving instructions. Exact state equality proves their common
    # continuation; no sampled history stands in for an unbounded domain.
    prefix_states, prefix_paths = [], []
    for upper_taken, lower_taken in ((True, False), (False, True), (False, False)):
        selected = deepcopy(initial)
        address, seen, path = ins.address + ins.size, set(), []
        try:
            for _ in range(128):
                if address == spec["thresholdStart"]:
                    break
                if address in seen or address not in machine.ins:
                    raise Boundary("formula prefix loops or leaves method")
                seen.add(address)
                operation = machine.ins[address]
                path.append(
                    dict(address=hex(address), nativeBytes=operation.bytes.hex())
                )
                if address == spec["maxRead"]:
                    if machine.address(
                        operation, operation.operands[1], selected
                    ) != pointer(history.owner, spec["maxOffset"]):
                        raise Boundary("maximum is not this typed Param")
                if address == spec["minRead"]:
                    if machine.address(
                        operation, operation.operands[1], selected
                    ) != pointer(history.owner, spec["minOffset"]):
                        raise Boundary("minimum is not this typed Param")
                if address in (spec["upper"], spec["lower"]):
                    taken = upper_taken if address == spec["upper"] else lower_taken
                    address = (
                        operation.operands[0].imm if taken else address + operation.size
                    )
                else:
                    address = machine.step(operation, selected)
            else:
                raise Boundary("formula prefix exceeds bound")
        except Boundary as error:
            raise ValueError("已审核随机公式前缀绑定未闭合：" + str(error)) from error
        selected["regs"]["rax"] = selected["regs"][spec["maxRegister"]] = None
        selected["flags"] = None
        prefix_states.append(selected)
        prefix_paths.append(path)

    class Probe(Machine):
        def load(self, location, size, selected):
            if isinstance(location, tuple) and location[:2] == (
                "pointer",
                history.owner,
            ):
                fields = manager.private_field(location, size)
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
                fields = manager.private_field(location, operand.size)
                if fields:
                    if (
                        type(value) is not int
                        or sum(4 for _ in fields) != operand.size
                        or not {off for off, _ in fields} <= set(history.fields)
                    ):
                        raise Boundary(
                            "private write is not a complete fixed pair store"
                        )
                    self.written.update(off for off, _ in fields)
                elif not (
                    isinstance(location, tuple) and location[:2] == ("pointer", "stack")
                ):
                    raise Boundary("branch has an unreviewed external write")
            return Machine.write(self, operation, operand, value, selected)

    def recover_bucket(index, start, working):
        probe = object.__new__(Probe)
        probe.__dict__ = dict(machine.__dict__)
        probe.written = set()
        selected = deepcopy(working)
        dirty = {"rax", spec["maxRegister"]}
        # Compiler-scheduled MOV/LEA between a threshold CMP and JBE is part
        # of every path through that decision, including the final high bucket.
        for split in spec["splits"][: min(index + 1, len(spec["splits"]))]:
            scheduled = split["compare"]
            while scheduled != split["branch"]:
                operation = probe.ins[scheduled]
                scheduled = probe.step(operation, selected)
                if (
                    operation.mnemonic in {"mov", "movabs", "lea"}
                    and operation.operands[0].size >= 4
                ):
                    dirty.discard(register(operation, operation.operands[0].reg))
        selected["flags"] = None
        address, writes, path, seen = start, [], [], set()
        try:
            for _ in range(96):
                if address in seen or address not in probe.ins:
                    raise Boundary("branch loops or leaves the method")
                seen.add(address)
                operation = probe.ins[address]
                complete = set(history.fields) == probe.written
                if operation.mnemonic == "call":
                    call = probe.event(operation, selected)
                    if (
                        not complete
                        or call["target"] is None
                        or any(arg is None for arg in call["arguments"])
                    ):
                        raise Boundary(
                            "fixed writes or actual call arguments are incomplete"
                        )
                    if any(
                        isinstance(arg, tuple) and arg[:2] == ("pointer", history.owner)
                        for arg in call["arguments"]
                    ):
                        raise Boundary("private Param escapes to a call")
                    stop_kind = "nativeCall"
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
                    if not complete:
                        raise Boundary("branch checks before fixed history writes")
                    # Resume exactly here. In particular the operator's +0xc6
                    # guard remains a real Machine.walk branch with its state.
                    stop_kind = "nativeContinuation"
                    break
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
                    operation.operands
                    and operation.operands[0].type == CS_OP_REG
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
            truth=index == 0,
            address=address,
            state=project(selected),
            writes=writes,
            nativePath=path,
            continuationKind=stop_kind,
        )

    buckets = []
    for index, start in enumerate(spec["leaves"]):
        candidates = [
            recover_bucket(index, start, working) for working in prefix_states
        ]
        # Inserted pointer reloads may differ at the threshold. They may be
        # forgotten only when all guard paths reach this exact actual call or
        # continuation with the same complete state and ordered writes.
        if any(candidate != candidates[0] for candidate in candidates[1:]):
            raise ValueError("随机区间各guard路径的真实后继状态或写入不相同")
        buckets.append(candidates[0])

    def expression(threshold):
        return dict(
            kind="table_history_interval",
            drawKey=f"random_uint32_mod_{spec['modulus']}:{hex(ins.address)}",
            maxKey=history.key(spec["maxOffset"]),
            minKey=history.key(spec["minOffset"]),
            modulus=spec["modulus"],
            threshold=threshold,
        )

    decisions = [
        dict(
            expression=expression(split["threshold"]),
            true=dict(bucket=index),
            false=(
                dict(decision=index + 1)
                if index + 1 < len(spec["splits"])
                else dict(bucket=index + 1)
            ),
        )
        for index, split in enumerate(spec["splits"])
    ]
    proof = deepcopy(spec["nativeProof"])
    proof["guardPaths"] = prefix_paths
    return dict(
        expression=decisions[0]["expression"],
        decisions=decisions,
        entryState=entry_state,
        inputDefinitions=history.input_definitions(),
        nativeProof=proof,
        buckets=buckets,
    )
