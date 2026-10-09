"""Bounded symbolic x64 walk for reviewed BTable command and continuation sites.

This emits player semantic nodes, never native blocks. Unknown branch inputs stop
the walk. Command implementations and random selectors still require review.
"""

import copy
import hashlib
import json
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM, CS_OP_REG
from ..native.bindings import register, pointer, add, dereference
from ..workflow.semantic_recovery import command_binding
from .predicates import RuleRegistry
from .values import enum_number
from .common_conditions import receipt
from ..config import (
    ARRAY_LENGTH,
    BOOLEAN_TYPE,
    CALLBACK_COUNT,
    CALLBACK_METHOD,
    CALLBACK_TARGET,
    COMMAND_WORK_RANDOM,
    EXPORT_RUNTIME_ROOT,
    FN_POSITION_STACK_PUSH,
    GLOBAL_TABLE_ENTRY_ZERO,
    INLINE_PUSH_CALLS,
    MACHINE_TRANSPARENT_CALLS,
    NO_ARGUMENT_TYPES,
    OBJECT_VTABLE_FROM_INTERFACE,
    OPERATOR_CLASS,
    OPERATOR_EXPORT_END,
    OPERATOR_EXPORT_JUMP,
    OPERATOR_POSITION,
    OPERATOR_POSITION_CALLBACK,
    OPERATOR_POSITION_ROW,
    OPERATOR_POSITION_STACK,
    OPERATOR_RANDOM_STATE,
    OPERATOR_REQUEST_COMMAND,
    POSITION_ROW,
    POSITION_SIZE,
    POSITION_TABLE,
    RANDOM_DRAW_SOURCE,
    RANDOM_TYPE_COMMAND,
    RANDOM_TYPE_COMMAND_EVIDENCE,
    RUNTIME_DATA_START,
    STACK_ARRAY,
    STACK_REFERENCE_TAG,
    STACK_SIZE,
    STACK_VERSION,
    UNFAIR_ACTIVE_FIELD,
    UNFAIR_ACTIVE_OFFSET,
    UNFAIR_ROUTINE_COMMAND,
    VOID_TYPE,
    ARRAY_ELEMENTS,
)

VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}


class Boundary(Exception):
    pass


class Machine:
    def __init__(self, row, native, pe, body, factories, target_rows, imports):
        self.row, self.pe, self.body, self.factories = row, pe, body, factories
        assert hashlib.sha256(native).hexdigest() == row["nativeSha256"]
        decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        decoder.detail = True
        self.ins = {
            i.address: i for i in decoder.disasm(native, int(row["address"], 16))
        }
        self.targets, self.imports = target_rows, imports
        self.registry = RuleRegistry.load()
        self.nodes, self.states, self.log = {}, {}, []
        self.pending = []
        self.required_tables = set()
        self.random_states = {}
        self.random_modulus = None
        self.last_request = None
        self.last_resume_trace = None
        self.metadata = None
        self.command_evidence = {}
        self.action_entries = {}
        self.event_contexts = {}
        self.proofs = {}
        self.proof_depth = 0

    def event_key(self, event, state, bound=None):
        """Return the semantic node key of one call context, or None.

        The compiler can share one call instruction between several PCs with
        different argument slots; each target/argument identity keeps its own
        node. A later machine state reuses a node only when replaying both
        states from the call yields the same semantic subgraph, which proves
        that every differing register, stack slot or field is dead there.
        """
        site = event["site"]
        identity = (event["target"], event["arguments"], bound)
        variants = self.event_contexts.setdefault(site, [])
        for index, (known, known_state) in enumerate(variants):
            if known == identity:
                key = site if index == 0 else f"{site}-variant-{index}"
                if known_state == state or self.equivalent(
                    int(site, 16), (site, index), known_state, state
                ):
                    return key
                return None
        variants.append((copy.deepcopy(identity), copy.deepcopy(state)))
        index = len(variants) - 1
        return site if index == 0 else f"{site}-variant-{index}"

    def equivalent(self, address, variant, known, state):
        if self.proof_depth >= 2:
            return False
        key = variant, repr(state)
        if key not in self.proofs:
            if variant not in self.proofs:
                self.proofs[variant] = self.replay(address, known)
            self.proofs[key] = self.proofs[variant] == self.replay(address, state)
        return self.proofs[key]

    def replay(self, address, state):
        """Walk one state in an isolated copy; pending PCs stay unresolved keys."""
        probe = copy.copy(self)
        probe.nodes, probe.states, probe.pending = {}, {}, []
        probe.required_tables, probe.event_contexts = set(), {}
        probe.action_entries, probe.proofs = {}, {}
        probe.proof_depth = self.proof_depth + 1
        probe.last_request = probe.last_resume_trace = None
        entry = probe.walk(address, copy.deepcopy(state))
        return entry, probe.nodes, probe.required_tables

    def command_return(self, bound):
        """Use the matched actual onExecute identity, including inherited bodies."""
        row = self.command_evidence.get(bound["commandType"])
        if row is None or self.metadata is None:
            return None
        record = self.metadata.get(row["type"])
        method = (record or {}).get("methods", {}).get(row["method"])
        if not method or int(method.get("function", "0"), 16) != int(
            row["address"], 16
        ):
            raise ValueError("命令返回类型的原生方法身份不匹配")
        return method.get("returns", {}).get("type")

    def initial(self, pc):
        return dict(
            regs={
                "rcx": pointer("thread"),
                "rdx": pointer("export"),
                "r8": pointer("command_work"),
                "r9": pointer("operator"),
                "rsp": pointer("stack"),
            },
            mem={
                ("operator", OPERATOR_POSITION_ROW, 4): pc,
                ("operator", OPERATOR_EXPORT_JUMP, 1): 0,
                ("operator", OPERATOR_EXPORT_END, 1): 0,
                ("operator", OPERATOR_RANDOM_STATE, 4): 0,
            },
            flags=None,
            saved=None,
        )

    def address(self, ins, op, s):
        m = op.mem
        base = (
            ins.address + ins.size
            if ins.reg_name(m.base) == "rip"
            else (s["regs"].get(register(ins, m.base)) if m.base else 0)
        )
        index = s["regs"].get(register(ins, m.index), 0) if m.index else 0
        if not isinstance(index, int):
            return None
        return add(base, m.disp + index * m.scale)

    def load(self, address, size, s):
        if isinstance(address, int):
            if address == GLOBAL_TABLE_ENTRY_ZERO:
                return 0
            if address >= RUNTIME_DATA_START:
                return None
            # PE bytes are used only for switch offsets and compile-time data.
            try:
                return int.from_bytes(self.pe.read(address, size), "little")
            except (ValueError, KeyError, IndexError):
                return None
        if not isinstance(address, tuple) or address[0] != "pointer":
            return None
        owner, offset = address[1:]
        key = owner, offset, size
        if key in s["mem"]:
            return s["mem"][key]
        for (other, start, width), value in s["mem"].items():
            if other == owner and start <= offset and offset + size <= start + width:
                if isinstance(value, int):
                    return (value >> ((offset - start) * 8)) & ((1 << (size * 8)) - 1)
                if offset == start and size == width:
                    return value
        if owner == "export":
            if offset == EXPORT_RUNTIME_ROOT:
                return 0xABCDEF
            if offset in self.imports:
                return pointer(("import", self.imports[offset]))
            return dereference(address) if size == 8 else None
        if owner == "operator":
            if offset == OPERATOR_CLASS:
                return pointer("operator_class")
            if offset == OPERATOR_POSITION_STACK:
                return pointer("return_stack")
            if offset == OPERATOR_POSITION:
                return 0xABCDEF
            return None
        if owner == "operator_class" and offset == 0:
            # The native method is evaluated under its declared valid
            # cEmOperatorWork precondition; no game runtime memory is read.
            return 0
        if owner == "command_work" and offset == COMMAND_WORK_RANDOM:
            return pointer("random_holder")
        if owner == "random_holder" and offset == 0:
            return pointer("random_instance")
        if owner == "random_instance" and offset == OBJECT_VTABLE_FROM_INTERFACE:
            return pointer("random_vtable")
        if owner == "random_vtable" and offset == 0:
            return ("random_generator",)
        return dereference(address) if size == 8 else None

    def read(self, ins, op, s):
        if op.type == CS_OP_IMM:
            return op.imm
        if op.type == CS_OP_REG:
            value = s["regs"].get(register(ins, op.reg))
            if isinstance(value, int):
                shift = 8 if ins.reg_name(op.reg) in {"ah", "bh", "ch", "dh"} else 0
                return (value >> shift) & ((1 << (8 * op.size)) - 1)
            return value if op.size == 8 else None
        if op.type == CS_OP_MEM:
            return self.load(self.address(ins, op, s), op.size, s)
        return None

    def write(self, ins, op, value, s):
        if op.type == CS_OP_REG:
            name = register(ins, op.reg)
            if isinstance(value, int):
                mask = (1 << (op.size * 8)) - 1
                if op.size < 4:
                    old = s["regs"].get(name, 0)
                    shift = 8 if ins.reg_name(op.reg) in {"ah", "bh", "ch", "dh"} else 0
                    value = (
                        (old if isinstance(old, int) else 0) & ~(mask << shift)
                    ) | ((value & mask) << shift)
                else:
                    value &= mask
            s["regs"][name] = value
        elif op.type == CS_OP_MEM:
            address = self.address(ins, op, s)
            if not isinstance(address, tuple) or address[0] != "pointer":
                return
            owner, offset = address[1:]
            for key in list(s["mem"]):
                if (
                    key[0] == owner
                    and key[1] < offset + op.size
                    and offset < key[1] + key[2]
                ):
                    del s["mem"][key]
            s["mem"][(owner, offset, op.size)] = value

    def truth(self, mnemonic, s):
        f = s["flags"]
        if not f:
            return None
        if mnemonic in {"a", "ae", "b", "be"} and f["c"] is None:
            return None
        return {
            "e": f["z"],
            "z": f["z"],
            "ne": not f["z"],
            "nz": not f["z"],
            "a": not f["c"] and not f["z"],
            "ae": not f["c"],
            "b": f["c"],
            "be": f["c"] or f["z"],
            "g": not f["z"] and f["s"] == f["o"],
            "ge": f["s"] == f["o"],
            "l": f["s"] != f["o"],
            "le": f["z"] or f["s"] != f["o"],
            "s": f["s"],
            "ns": not f["s"],
        }.get(mnemonic)

    def flags(self, a, b, result, width, operation):
        if not all(isinstance(x, int) for x in (a, b, result)):
            return None
        mask, sign = (1 << width) - 1, 1 << (width - 1)
        x = result & mask
        subtraction = operation == "sub"
        addition = operation == "add"
        return dict(
            z=x == 0,
            s=bool(x & sign),
            c=(
                (a & mask) < (b & mask)
                if subtraction
                else (a & mask) + (b & mask) > mask if addition else False
            ),
            o=(
                bool(((a ^ b) & (a ^ x) & sign))
                if subtraction
                else bool((~(a ^ b) & (a ^ x) & sign)) if addition else False
            ),
        )

    def event(self, ins, s):
        args = [s["regs"].get(k) for k in ("rcx", "rdx", "r8", "r9")]
        args.append(self.load(add(s["regs"].get("rsp"), 0x20), 8, s))
        target = self.read(ins, ins.operands[0], s)
        if args[0] is None or not (
            isinstance(args[0], tuple) and args[0][:2] == ("pointer", "stack")
        ):
            args = args[:4]
        return dict(
            kind="call",
            site=hex(ins.address),
            target=target,
            direct=ins.operands[0].type == CS_OP_IMM,
            arguments=args,
            positionArguments={},
        )

    def bind(self, event):
        try:
            bound = command_binding(event, self.body, self.factories, self.registry)
        except ValueError as error:
            bound = dict(
                kind="boundary",
                site=event["site"],
                reason="command_argument_rule_conflict",
                detail=str(error),
            )
        target = event["target"]
        if isinstance(target, tuple) and target[0] == "command_method":
            factory = self.factories[target[1]]
            if factory.get("_ArgumentType") in NO_ARGUMENT_TYPES:
                try:
                    predicate = self.registry.bind(factory["_OrderType"], "", {})
                except ValueError as error:
                    predicate = dict(status="unknown", reason=str(error))
                return dict(
                    commandIndex=target[1],
                    argumentIndex=None,
                    commandType=factory["_OrderType"],
                    argumentType="",
                    argument={},
                    predicate=predicate,
                    argumentBindingStatus=(
                        "conflict" if predicate.get("reason") else "no_argument"
                    ),
                )
        return bound

    def complete_call(self, s, e, boolean=0):
        s = copy.deepcopy(s)
        for k in VOLATILE:
            s["regs"].pop(k, None)
        s["flags"] = None
        out = e["arguments"][0]
        if isinstance(out, tuple) and out[:2] == ("pointer", "stack"):
            s["mem"][("stack", out[2], 4)] = 0
            s["mem"][("stack", out[2] + 4, 8)] = (
                None if boolean is None else int(boolean)
            )
            s["regs"]["rax"] = out
        else:
            s["regs"]["rax"] = None if boolean is None else int(boolean)
        return s

    def position(self, p, s):
        if not isinstance(p, tuple) or p[0] != "pointer":
            return None
        table = self.load(add(p, POSITION_TABLE), 4, s)
        pc = self.load(add(p, POSITION_ROW), 4, s)
        return (table, pc) if isinstance(table, int) and isinstance(pc, int) else None

    def add_unknown(self, site, reason):
        key = "boundary-" + hex(site)
        self.nodes.setdefault(
            key, dict(id=key, kind="unknown", reason=reason, nativeSite=hex(site))
        )
        return key

    def state(self, pc):
        key = "pc-" + str(pc)
        if key not in self.states:
            self.states[key] = None
            self.pending.append((key, int(self.row["address"], 16), self.initial(pc)))
        return key

    def branch_node(self, event, bound, s, after):
        site = event["site"]
        key = self.event_key(event, s, bound)
        if key is None:
            return self.add_unknown(
                int(site, 16),
                "同一原生判断位置的参数或机器上下文不同；尚不能证明复用已有后继等价",
            )
        if key in self.nodes:
            return key
        node = dict(
            id=key,
            kind="condition",
            nativeSite=site,
            argumentIndex=bound.get("argumentIndex"),
            commandIndex=bound["commandIndex"],
            expectedCommandType=bound["commandType"],
            expectedArgumentType=bound.get("argumentType", ""),
        )
        if bound.get("argumentIndex") is None:
            node.pop("argumentIndex")
            node.pop("commandIndex")
            node["expression"] = dict(
                kind="unknown",
                reason="此无参数命令的布尔判断尚未恢复：" + bound["commandType"],
            )
            node["summary"] = {
                "cCheckUnfairRoutineActive": "当前是否满足启动不公平行为流程的条件",
                "cCheckOccludedToDest": "目标是否被遮挡",
            }.get(
                bound["commandType"].split(".")[-1], bound["commandType"].split(".")[-1]
            )
        self.nodes[key] = node
        node["true"] = self.walk(after, self.complete_call(s, event, 1))
        node["false"] = self.walk(after, self.complete_call(s, event, 0))
        if (
            bound["commandType"]
            == UNFAIR_ROUTINE_COMMAND
        ):
            node["expression"] = dict(
                kind="unknown",
                reason="目标有效性及 checkTargetCharaUnfair 的完整资格条件尚未核实；不能把该命令当作读取已激活标志",
            )
            node["semanticEvidence"] = copy.deepcopy(
                receipt()["evidence"]["unfair_active"]
            )
            effect = key + "-activate"
            self.nodes[effect] = dict(
                id=effect,
                kind="mutation",
                effect="write_context_field",
                summary="启动不公平行为流程",
                nativeField=UNFAIR_ACTIVE_FIELD,
                nativeOffset=UNFAIR_ACTIVE_OFFSET,
                nativeValue=True,
                nativeSite=site,
                evidence=copy.deepcopy(receipt()["evidence"]["unfair_active"][0]),
                next=node["true"],
            )
            node["true"] = effect
        if bound.get("argumentIndex") is None:
            from .navigation_conditions import recover_navigation_condition

            recovered = recover_navigation_condition(
                node, self.registry.data["profile"]
            )
            if recovered is not None:
                node.update(recovered)
        return key

    def find_resume(self, address, s):
        self.last_request = None
        self.last_resume_trace = None
        original = copy.deepcopy(s)
        result = self._find_resume_once(address, s)
        if result is not None:
            return result
        # The native compiler sometimes inlines Stack<POSITION>.Push and
        # setCurrentPosition. Check both capacity branches and the optional
        # position-change callback path. These are symbolic storage fixtures,
        # never values asserted for the running game. All normal return paths
        # must write the same continuation before this pattern is accepted.
        candidates = []
        for used, capacity, reference in (
            (0, 0, 0),
            (0, 1, 0),
            (1, 1, 0),
            (1, 2, 0),
            (0, 0, 0xFFFFFFFF),
            (0, 1, 0xFFFFFFFF),
            (1, 1, 0xFFFFFFFF),
            (1, 2, 0xFFFFFFFF),
        ):
            for callbacks in (0, 1):
                state = copy.deepcopy(original)
                state["mem"].update(
                    {
                        ("return_stack", STACK_ARRAY, 8): pointer("return_stack_array"),
                        ("return_stack", STACK_REFERENCE_TAG, 4): reference,
                        ("return_stack", STACK_SIZE, 4): used,
                        ("return_stack", STACK_VERSION, 4): 0,
                        ("return_stack_array", ARRAY_LENGTH, 4): capacity,
                        ("operator", OPERATOR_POSITION_CALLBACK, 8): pointer(
                            "position_callbacks"
                        ),
                        ("position_callbacks", CALLBACK_COUNT, 4): callbacks,
                        ("position_callbacks", CALLBACK_TARGET, 8): 0,
                        ("position_callbacks", CALLBACK_METHOD, 8): (
                            "position_callback",
                        ),
                    }
                )
                self.last_request = None
                resume = self._find_resume_once(address, state, inline_stack=True)
                if resume is None:
                    return None
                candidates.append((resume, copy.deepcopy(self.last_request)))
        if any(item != candidates[0] for item in candidates[1:]):
            return None
        self.last_request = candidates[0][1]
        self.last_resume_trace = dict(
            kind="native_inline_position_save",
            checkedStackStorageCases=4,
            checkedCallbackCases=2,
            checkedReferenceTagCases=2,
            callbackSideEffects="unreviewed",
            scope="调用方正常返回后的真实12字节POSITION写入；不模拟回调内部副作用或游戏栈容量",
        )
        return candidates[0][0]

    def _find_resume_once(self, address, s, *, inline_stack=False):
        candidate = None
        for _ in range(480):
            ins = self.ins.get(address)
            if ins is None:
                break
            if ins.mnemonic == "call":
                e = self.event(ins, s)
                if e["target"] == FN_POSITION_STACK_PUSH:
                    return self.position(e["arguments"][2], s)
                if self.bind(e):
                    break
                if (
                    inline_stack
                    and e["target"] not in INLINE_PUSH_CALLS
                    and e["target"] != ("position_callback",)
                ):
                    break
                s = self.complete_call(s, e, None)
                address += ins.size
            else:
                try:
                    if (
                        ins.mnemonic.startswith("mov")
                        and len(ins.operands) == 2
                        and ins.operands[0].type == CS_OP_MEM
                    ):
                        destination = self.address(ins, ins.operands[0], s)
                        if destination == pointer("operator", OPERATOR_REQUEST_COMMAND):
                            value = self.read(ins, ins.operands[1], s)
                            self.last_request = dict(
                                site=hex(ins.address), packedValue=value
                            )
                    address = self.step(ins, s)
                    if inline_stack and ins.mnemonic.startswith("mov"):
                        op = ins.operands[0]
                        if op.type == CS_OP_MEM:
                            destination = self.address(ins, op, s)
                            if (
                                isinstance(destination, tuple)
                                and destination[:2] == ("pointer", "return_stack_array")
                                and op.size == 8
                                and (destination[2] - ARRAY_ELEMENTS - POSITION_TABLE)
                                % POSITION_SIZE
                                == 0
                            ):
                                start = add(destination, -POSITION_TABLE)
                                position = self.position(start, s)
                                root = self.load(start, 4, s)
                                if position is not None and isinstance(root, int):
                                    candidate = position
                            if candidate is not None and destination == pointer(
                                "return_stack", STACK_SIZE
                            ):
                                return candidate
                except Boundary:
                    break
        return None

    def step(self, ins, s):
        op, m = ins.operands, ins.mnemonic
        nxt = ins.address + ins.size
        if m.startswith("ret"):
            return None
        if m.startswith("j"):
            target = self.read(ins, op[0], s)
            take = True if m == "jmp" else self.truth(m[1:], s)
            if take is None:
                raise Boundary("该分支的输入未恢复：" + ins.mnemonic + " " + ins.op_str)
            if take and not isinstance(target, int):
                raise Boundary("间接分支目标未恢复")
            return target if take else nxt
        if m in {"nop", "endbr64"}:
            return nxt
        if m == "lea":
            self.write(ins, op[0], self.address(ins, op[1], s), s)
            return nxt
        if m == "push":
            s["regs"]["rsp"] = add(s["regs"].get("rsp"), -8)
            s["mem"][("stack", s["regs"]["rsp"][2], 8)] = self.read(ins, op[0], s)
            return nxt
        if m == "pop":
            self.write(ins, op[0], self.load(s["regs"].get("rsp"), 8, s), s)
            s["regs"]["rsp"] = add(s["regs"].get("rsp"), 8)
            return nxt
        if m.startswith("set"):
            self.write(ins, op[0], self.truth(m[3:], s), s)
            return nxt
        if m == "btr" and len(op) == 2 and op[1].type == CS_OP_IMM and op[1].imm == 63:
            value = self.read(ins, op[0], s)
            if isinstance(value, tuple) and value[:2] == ("pointer", "stack"):
                return nxt
            if isinstance(value, int):
                self.write(ins, op[0], value & ~(1 << 63), s)
                return nxt
        if m.startswith("cmov"):
            t = self.truth(m[4:], s)
            if t is None:
                raise Boundary("条件赋值输入未恢复")
            if t:
                self.write(ins, op[0], self.read(ins, op[1], s), s)
            return nxt
        if m.startswith("mov") and len(op) == 2:
            value = self.read(ins, op[1], s)
            if m in {"movsx", "movsxd"} and isinstance(value, int):
                bits = op[1].size * 8
                if value & (1 << (bits - 1)):
                    value -= 1 << bits
            self.write(ins, op[0], value, s)
            return nxt
        if (
            m
            in {
                "cmp",
                "test",
                "and",
                "or",
                "xor",
                "add",
                "sub",
                "shr",
                "shl",
                "sar",
                "imul",
                "adc",
                "sbb",
            }
            and len(op) >= 2
        ):
            a, b = self.read(ins, op[0], s), self.read(ins, op[1], s)
            if m == "imul" and len(op) == 3:
                a, b = self.read(ins, op[1], s), self.read(ins, op[2], s)
            if (
                m == "xor"
                and op[0].type == op[1].type == CS_OP_REG
                and op[0].reg == op[1].reg
            ):
                a = b = 0
            value = None
            if m in {"add", "sub"} and isinstance(b, int):
                value = add(a, b if m == "add" else -b)
            elif (
                m in {"adc", "sbb"}
                and isinstance(a, int)
                and isinstance(b, int)
                and s["flags"] is not None
            ):
                carry = int(s["flags"]["c"])
                value = a + b + carry if m == "adc" else a - b - carry
            elif (
                m == "and"
                and b == 0x7FFFFFFFFFFFFFFF
                and isinstance(a, tuple)
                and a[0] == "pointer"
            ):
                value = a
            elif (
                m == "and"
                and a == 0x7FFFFFFFFFFFFFFF
                and isinstance(b, tuple)
                and b[0] == "pointer"
            ):
                value = b
            elif (
                m == "or"
                and b == 0x8000000000000000
                and isinstance(a, tuple)
                and a[0] == "pointer"
            ):
                value = a
            elif (
                m == "or"
                and a == 0x8000000000000000
                and isinstance(b, tuple)
                and b[0] == "pointer"
            ):
                value = b
            elif isinstance(a, int) and isinstance(b, int):
                value = {
                    "cmp": lambda: a - b,
                    "test": lambda: a & b,
                    "and": lambda: a & b,
                    "or": lambda: a | b,
                    "xor": lambda: a ^ b,
                    "shr": lambda: a >> b,
                    "shl": lambda: a << b,
                    "sar": lambda: (
                        a - (1 << (op[0].size * 8))
                        if a & (1 << (op[0].size * 8 - 1))
                        else a
                    )
                    >> b,
                    "imul": lambda: a * b,
                }.get(m, lambda: None)()
            if m == "test" and a == b and isinstance(a, tuple) and a[0] == "pointer":
                value, a, b = 1, 1, 1
            s["flags"] = self.flags(
                a, b, value, op[0].size * 8, "sub" if m in {"cmp", "sub"} else m
            )
            if m not in {"cmp", "test"}:
                self.write(ins, op[0], value, s)
            return nxt
        if m == "mul" and len(op) == 1:
            width = op[0].size * 8
            a, b = s["regs"].get("rax"), self.read(ins, op[0], s)
            if isinstance(a, int) and isinstance(b, int):
                product = (a & ((1 << width) - 1)) * b
                s["regs"]["rax"] = product & ((1 << width) - 1)
                s["regs"]["rdx"] = product >> width
            else:
                s["regs"]["rax"] = s["regs"]["rdx"] = None
            s["flags"] = None
            return nxt
        if m in {"inc", "dec", "neg"}:
            a = self.read(ins, op[0], s)
            previous_flags = s["flags"]
            value = (
                (-a if m == "neg" else a + (1 if m == "inc" else -1))
                if isinstance(a, int)
                else None
            )
            self.write(ins, op[0], value, s)
            s["flags"] = self.flags(
                0 if m == "neg" else a,
                a if m == "neg" else 1,
                value,
                op[0].size * 8,
                "add" if m == "inc" else "sub",
            )
            if m != "neg" and s["flags"] is not None:
                s["flags"]["c"] = (
                    previous_flags["c"] if previous_flags is not None else None
                )
            return nxt
        _, writes = ins.regs_access()
        for reg in writes:
            s["regs"].pop(register(ins, reg), None)
        return nxt

    def position_callback_branch(self, branch, s):
        """Prove that the OnChangedCurrnetPosition null check converges.

        The caller tests the operator's position-change delegate list before
        pushing a return position. A null list, an empty list and one static
        callback must all reach the same semantic node; the callback bodies
        are notifications whose side effects stay unreviewed.
        """
        if branch.mnemonic not in ("je", "jne") or branch.operands[0].type != CS_OP_IMM:
            return None
        if not hasattr(self, "order"):
            self.order = list(self.ins)
            self.index = {address: n for n, address in enumerate(self.order)}
        number = self.index[branch.address]
        test = self.ins[self.order[number - 1]]
        if (
            test.mnemonic != "test"
            or len(test.operands) != 2
            or test.operands[0].type != CS_OP_REG
            or test.operands[0].reg != test.operands[1].reg
            or test.operands[0].size != 8
        ):
            return None
        name = register(test, test.operands[0].reg)
        source = None
        for address in reversed(self.order[max(0, number - 14) : number - 1]):
            ins = self.ins[address]
            if ins.mnemonic.startswith(("j", "call", "ret")):
                return None
            _, writes = ins.regs_access()
            if name not in {register(ins, reg) for reg in writes}:
                continue
            op = ins.operands
            if (
                ins.mnemonic == "mov"
                and op[1].type == CS_OP_MEM
                and op[1].mem.disp == OPERATOR_POSITION_CALLBACK
                and not op[1].mem.index
                and s["regs"].get(register(ins, op[1].mem.base)) == pointer("operator")
            ):
                source = ins
            break
        if source is None:
            return None
        taken = branch.operands[0].imm
        following = branch.address + branch.size
        empty, listed = (
            (taken, following) if branch.mnemonic == "je" else (following, taken)
        )
        keys = []
        for count in (None, 0, 1):
            state = copy.deepcopy(s)
            state["flags"] = None
            if count is None:
                state["regs"][name] = 0
                keys.append(self.walk(empty, state))
                continue
            state["regs"][name] = pointer("position_callbacks")
            state["mem"].update(
                {
                    ("position_callbacks", CALLBACK_COUNT, 4): count,
                    ("position_callbacks", CALLBACK_TARGET, 8): 0,
                    ("position_callbacks", CALLBACK_METHOD, 8): ("position_callback",),
                }
            )
            keys.append(self.walk(listed, state))
        if any(key != keys[0] for key in keys[1:]) or keys[0].startswith("boundary-"):
            return None
        self.nodes[keys[0]].setdefault(
            "nativePositionCallbackRecovery",
            dict(
                kind="position_change_callback_convergence",
                nullCheck=hex(branch.address),
                listLoad=hex(source.address),
                checkedCases=["null", "empty", "one_static_callback"],
                callbackSideEffects="unreviewed",
            ),
        )
        return keys[0]

    def walk(self, address, s):
        seen = set()
        for _ in range(4000):
            if address is None:
                value = s["regs"].get("rax")
                if not isinstance(value, int):
                    return self.add_unknown(
                        int(self.row["address"], 16), "返回值未能从当前原生指令唯一恢复"
                    )
                value = value & 0xFF
                ended = self.load(pointer("operator", OPERATOR_EXPORT_END), 1, s)
                key = "return-" + str(bool(value)).lower() + "-end-" + str(ended)
                self.nodes.setdefault(
                    key,
                    dict(
                        id=key, kind="return", value=bool(value), tableEnded=ended == 1
                    ),
                )
                return key
            ins = self.ins.get(address)
            if ins is None:
                return self.add_unknown(
                    address, "执行到当前已校验方法范围外；需核实该实际目标"
                )
            signature = (address, repr(s["regs"]), repr(s["mem"]))
            if signature in seen:
                return self.add_unknown(address, "循环的更新或退出条件尚未恢复")
            seen.add(signature)
            if ins.mnemonic == "call":
                e = self.event(ins, s)
                if e["target"] == ("random_generator",):
                    key = self.event_key(e, s)
                    if key is None:
                        return self.add_unknown(
                            address,
                            "同一随机调用位置的机器上下文不同；尚不能证明复用已有后继等价",
                        )
                    if self.random_modulus is None:
                        if key in self.nodes:
                            return key
                        self.nodes[key] = dict(
                            id=key,
                            kind="mutation",
                            effect="draw_random_integer",
                            summary="更新随机数状态",
                            nativeSite=e["site"],
                        )
                        self.nodes[key]["next"] = self.walk(
                            address + ins.size, self.complete_call(s, e, None)
                        )
                        return key
                    if key in self.nodes:
                        return key
                    self.nodes[key] = dict(
                        id=key,
                        kind="unknown",
                        reason="正在核实随机余数分支",
                        nativeSite=e["site"],
                    )
                    choices = [
                        self.walk(address + ins.size, self.complete_call(s, e, value))
                        for value in range(self.random_modulus)
                    ]
                    groups = []
                    for value, target in enumerate(choices):
                        if groups and groups[-1][2] == target:
                            groups[-1] = (groups[-1][0], value, target)
                        else:
                            groups.append((value, value, target))
                    for i, (low, high, target) in enumerate(groups):
                        nid = key if i == 0 else key + "-range-" + str(i)
                        if i == len(groups) - 1:
                            self.nodes[nid] = dict(
                                id=nid,
                                kind="mutation",
                                effect="random_result_selection",
                                summary=f"本次随机余数落在 {low}–{high}",
                                next=target,
                                nativeSite=e["site"],
                            )
                        else:
                            self.nodes[nid] = dict(
                                id=nid,
                                kind="condition",
                                summary=f"本次随机整数 % {self.random_modulus} ≤ {high}",
                                detail="按已核实的原生余数分支继续；随机源分布尚未模拟",
                                expression=dict(
                                    kind="compare",
                                    operator="le",
                                    left=dict(
                                        kind="runtime",
                                        key=f"random_uint32_mod_{self.random_modulus}:"
                                        + key,
                                        source=RANDOM_DRAW_SOURCE,
                                    ),
                                    right=dict(kind="constant", value=high),
                                ),
                                true=target,
                                false=key + "-range-" + str(i + 1),
                                nativeSite=e["site"],
                            )
                    return key
                bound = self.bind(e)
                if bound and bound.get("kind") == "boundary":
                    unknown = self.add_unknown(
                        address,
                        "命令参数绑定存在边界："
                        + bound.get("reason", "unknown_binding"),
                    )
                    self.nodes[unknown]["nativeBinding"] = copy.deepcopy(bound)
                    return unknown
                if bound and (
                    not bound.get("commandType")
                    or not isinstance(bound.get("commandIndex"), int)
                ):
                    unknown = self.add_unknown(address, "命令调用身份未完整恢复")
                    self.nodes[unknown]["nativeBinding"] = copy.deepcopy(bound)
                    return unknown
                if bound and (
                    bound.get("argumentIndex") is not None
                    or self.factories[bound["commandIndex"]].get("_ArgumentType")
                    in NO_ARGUMENT_TYPES
                ):
                    command = bound["commandType"].split(".")[-1]
                    key = self.event_key(e, s, bound)
                    if key is None:
                        return self.add_unknown(
                            address,
                            "同一原生命令位置的参数、保存位置或机器上下文不同；尚不能证明复用已有后继等价",
                        )
                    if key in self.nodes:
                        return self.action_entries.get(key, key)
                    if bound.get("argumentBindingStatus") == "conflict" or (
                        bound.get("argumentIndex") is None
                        and bound.get("predicate", {}).get("argumentType")
                    ):
                        return self.add_unknown(
                            address,
                            "工厂声明无参数，但命令规则需要参数；不能伪造参数绑定："
                            + command,
                        )
                    if bound.get("argumentIndex") is not None and not bound.get(
                        "argumentType"
                    ):
                        return self.add_unknown(
                            address,
                            "命令参数类型尚未唯一恢复，不能据此建立判断分支："
                            + command,
                        )
                    binding = dict(
                        argumentIndex=bound.get("argumentIndex"),
                        commandIndex=bound["commandIndex"],
                        expectedCommandType=bound["commandType"],
                        expectedArgumentType=bound.get("argumentType", ""),
                        nativeSite=e["site"],
                    )
                    if command in {"cRequestAction", "cRequestActionSync"}:
                        if (
                            command == "cRequestActionSync"
                            and self.command_return(bound) != VOID_TYPE
                        ):
                            return self.add_unknown(
                                address, "同步动作请求必须先由匹配元数据核实 void 返回"
                            )
                        resume = self.find_resume(
                            address + ins.size, self.complete_call(s, e, None)
                        )
                        if not resume:
                            return self.add_unknown(
                                address, "动作请求已绑定，准确恢复位置仍须追踪"
                            )
                        self.nodes[key] = dict(
                            id=key,
                            kind="action",
                            **binding,
                            resume=self.state(resume[1]),
                            nativeContinuation=dict(
                                tableIndex=resume[0], programCounter=resume[1]
                            ),
                            execution="request_then_yield",
                            requestSite=(
                                self.last_request["site"] if self.last_request else e["site"]
                            ),
                            callSite=e["site"],
                            nativeRequestPosition=self.last_request,
                            nativeResumeRecovery=copy.deepcopy(self.last_resume_trace),
                        )
                        from .action_commands import request_details

                        detail = request_details(
                            bound["commandType"],
                            self.registry.data["profile"],
                            self.command_evidence.get(bound["commandType"]),
                            self.metadata,
                        )
                        if detail is not None:
                            self.nodes[key].update(detail)
                            guard_key, suppressed = key + "-guard", key + "-suppressed"
                            self.nodes[guard_key] = dict(
                                id=guard_key,
                                kind="condition",
                                summary="有效命令工作且未屏蔽行为表动作请求？",
                                expression=copy.deepcopy(detail["requestGuard"]),
                                true=key,
                                false=suppressed,
                                nativeSite=e["site"],
                                semanticEvidence=copy.deepcopy(
                                    detail["semanticEvidence"]
                                ),
                            )
                            self.nodes[suppressed] = dict(
                                id=suppressed,
                                kind="mutation",
                                effect="yield_without_action_request",
                                summary="本次未发出动作请求；行为表仍保存继续位置并让出",
                                reason="原生命令返回 void；调用方无条件写请求位置并保存继续位置，不能按假造的成功布尔选择路径",
                                next=self.state(resume[1]),
                                nativeSite=e["site"],
                                execution="request_suppressed_then_yield",
                                nativeContinuation=dict(
                                    tableIndex=resume[0], programCounter=resume[1]
                                ),
                            )
                            if "actorRequestGuard" in detail:
                                actor_guard, actor_skip = (
                                    key + "-actor-guard",
                                    key + "-actor-skip",
                                )
                                self.nodes[guard_key]["true"] = actor_guard
                                self.nodes[actor_guard] = dict(
                                    id=actor_guard,
                                    kind="condition",
                                    summary="当前 actor 没有网络信息，或其主机索引为无效值/本机索引？",
                                    expression=copy.deepcopy(
                                        detail["actorRequestGuard"]
                                    ),
                                    true=key,
                                    false=actor_skip,
                                    nativeSite=e["site"],
                                    semanticEvidence=copy.deepcopy(
                                        detail["semanticEvidence"]
                                    ),
                                )
                                self.nodes[actor_skip] = dict(
                                    id=actor_skip,
                                    kind="mutation",
                                    effect="record_request_without_actor_helper",
                                    summary="已登记请求并清除请求标志；当前网络归属跳过 actor 请求 helper，行为表保存继续位置并让出",
                                    next=self.state(resume[1]),
                                    nativeSite=e["site"],
                                    execution="request_actor_helper_skipped_then_yield",
                                    requestEffects=copy.deepcopy(
                                        detail["requestEffects"]
                                    ),
                                    implementationBoundary=detail[
                                        "implementationBoundary"
                                    ],
                                    nativeContinuation=dict(
                                        tableIndex=resume[0], programCounter=resume[1]
                                    ),
                                )
                            self.action_entries[key] = guard_key
                            return guard_key
                        return key
                    if command in {"cSetTimerValue", "cSetValueFloat"}:
                        self.nodes[key] = dict(
                            id=key,
                            kind="mutation",
                            **binding,
                            effect=(
                                "set_timer_state"
                                if command == "cSetTimerValue"
                                else "set_float_value"
                            ),
                        )
                        self.nodes[key]["next"] = self.walk(
                            address + ins.size, self.complete_call(s, e)
                        )
                        return key
                    if command == "cSetDest":
                        self.nodes[key] = dict(
                            id=key,
                            kind="mutation",
                            **binding,
                            effect="set_destination",
                            summary="设置移动目的地",
                            reason="按本节点的资源参数调用导航命令；目的地计算使用实际运行时场景",
                            implementationBoundary="destination_query_inputs_required",
                        )
                        yes = self.walk(address + ins.size, self.complete_call(s, e, 1))
                        no = self.walk(address + ins.size, self.complete_call(s, e, 0))
                        if yes == no:
                            self.nodes[key]["next"] = yes
                        else:
                            result_key = key + "-result"
                            self.nodes[result_key] = dict(
                                id=result_key,
                                kind="condition",
                                summary="移动目的地命令的返回结果为真？",
                                detail="按调用方真实分支继续；导航内部查询依赖当前场景",
                                expression=dict(
                                    kind="runtime",
                                    key="command_result:" + key,
                                    source=bound["commandType"]
                                    + " 在此原生调用位置返回的布尔结果",
                                ),
                                true=yes,
                                false=no,
                                nativeSite=e["site"],
                            )
                            self.nodes[key]["next"] = result_key
                        return key
                    if bound["commandType"] == RANDOM_TYPE_COMMAND:
                        value = enum_number(bound["argument"]["_EditType"])
                        self.nodes[key] = dict(
                            id=key,
                            kind="mutation",
                            **binding,
                            effect="read_random_selection_mode",
                            value=value,
                            summary="读取资源中指定的随机选择方式",
                            semanticEvidence=dict(RANDOM_TYPE_COMMAND_EVIDENCE),
                            next=self.walk(
                                address + ins.size, self.complete_call(s, e, value)
                            ),
                        )
                        return key
                    if (
                        command.startswith("cCheck")
                        or command.startswith("cCompare")
                        or (
                            command.startswith("cIs")
                            and self.command_return(bound) == BOOLEAN_TYPE
                        )
                    ):
                        return self.branch_node(e, bound, s, address + ins.size)
                    if self.command_return(bound) == VOID_TYPE:
                        evidence = copy.deepcopy(
                            self.command_evidence[bound["commandType"]]
                        )
                        node = dict(
                            id=key,
                            kind="unknown",
                            reason="已绑定 void 命令，内部副作用尚未核实：" + command,
                            nativeSite=e["site"],
                            commandType=bound["commandType"],
                            expectedCommandType=bound["commandType"],
                            semanticEvidence=evidence,
                            implementationBoundary="unknown_void_command_effects",
                            returnType=VOID_TYPE,
                            continuationStatus="native_caller_continuation",
                        )
                        if bound.get("argumentIndex") is not None:
                            node.update(binding)
                        self.nodes[key] = node
                        node["next"] = self.walk(
                            address + ins.size, self.complete_call(s, e, None)
                        )
                        return key
                    return self.add_unknown(
                        address, "已绑定命令需逐项核实其作用：" + command
                    )
                if e["target"] == FN_POSITION_STACK_PUSH:
                    s["saved"] = self.position(e["arguments"][2], s)
                if isinstance(e["target"], int) and e["target"] in self.targets:
                    candidates = self.targets[e["target"]]
                    if isinstance(candidates, dict):
                        candidates = [candidates]
                    owner = e["arguments"][1]
                    owner_type = None
                    if owner == pointer("export"):
                        owner_type = self.row["type"]
                    elif (
                        isinstance(owner, tuple)
                        and len(owner) == 3
                        and owner[0] == "pointer"
                        and isinstance(owner[1], tuple)
                        and owner[1][0] == "import"
                    ):
                        owner_type = owner[1][1]
                    candidates = [
                        target
                        for target in candidates
                        if target["row"]["type"] == owner_type
                    ]
                    if len(candidates) != 1:
                        return self.add_unknown(
                            address, "原生调用的对象归属或同地址表别名未能唯一恢复"
                        )
                    target = candidates[0]
                    if s["saved"] is None:
                        return self.add_unknown(
                            address, "子表调用已定位，准确返回位置尚未恢复"
                        )
                    key = (
                        e["site"]
                        + "-target-"
                        + target["tableGuid"]
                        + "-resume-"
                        + str(s["saved"][0])
                        + "-"
                        + str(s["saved"][1])
                    )
                    self.required_tables.add(target["tableGuid"])
                    self.nodes.setdefault(
                        key,
                        dict(
                            id=key,
                            kind="call",
                            targetTable=target["tableGuid"],
                            resume=self.state(s["saved"][1]),
                            nativeContinuation=dict(
                                tableIndex=s["saved"][0], programCounter=s["saved"][1]
                            ),
                            execution="push_return_position_then_call",
                            nativeSite=e["site"],
                        ),
                    )
                    return key
                # Shared position/security helpers are transparent here. Other
                # direct calls stop: no guessed side effect can advance the tree.
                # A position-change notification exists only in the fixture of
                # position_callback_branch, which proves path convergence.
                if e["target"] not in MACHINE_TRANSPARENT_CALLS and e["target"] != (
                    "position_callback",
                ):
                    return self.add_unknown(
                        address, "辅助调用的作用尚未核实：" + str(e["target"])
                    )
                s = self.complete_call(s, e)
                address += ins.size
                continue
            try:
                address = self.step(ins, s)
            except Boundary as error:
                from .combat_position import recover_entry_push

                recovered = recover_entry_push(self, ins, s)
                if recovered is not None:
                    call_address, state, proof = recovered
                    key = self.walk(call_address, state)
                    self.nodes[key]["nativeContinuationRecovery"] = proof
                    return key
                key = self.position_callback_branch(ins, s)
                if key is not None:
                    return key
                return self.add_unknown(ins.address, str(error))
        return self.add_unknown(address, "本条路径超过有界追踪长度；需展开循环语义")

    def build(self):
        self.state(0)
        while self.pending:
            key, address, state = self.pending.pop(0)
            self.states[key] = self.walk(address, state)

        def resolve(key):
            seen = set()
            while key in self.states:
                if key in seen:
                    raise ValueError("empty state cycle")
                seen.add(key)
                key = self.states[key]
            return key

        for n in self.nodes.values():
            for role in ("true", "false", "next", "resume"):
                if role in n:
                    n[role] = resolve(n[role])
        return dict(
            entry=resolve("pc-0"),
            nodes=list(self.nodes.values()),
            requiredTables=sorted(self.required_tables),
        )
