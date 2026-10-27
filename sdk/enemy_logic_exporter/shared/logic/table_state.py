"""Track an export's private previous-random interval without inventing history.

The dictionary lookup is a typed address model, not a game-memory read. Candidate
histories come from paired constant stores in this native method and its matched
constructor. They are not exhaustive: callers must retain an unknown fallback.
"""

from collections import deque
from copy import deepcopy
import json
import re
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM, CS_OP_REG

from ..native.bindings import pointer, register
from ..config import EVIDENCE_DIR

OPERATOR_TYPE = "ace.btable.cOperatorWork"
EXPORT_TYPE = "ace.btable.cExportBTableBase"
PARAM_TYPE = EXPORT_TYPE + ".cExportBTableParam"
DICT_TYPE = "System.Collections.Generic.Dictionary`2<System.Int32," + PARAM_TYPE + ">"
MAX_DISCOVERY_STEPS = 12000
RUNTIME_FIXTURE_ID = 0xABCDEF


def _decoder():
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    return decoder


def _signed(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & (1 << 31) else value


def _method(metadata, owner, stem):
    rows = [
        (name, info)
        for name, info in (metadata.get(owner) or {}).get("methods", {}).items()
        if re.sub(r"\d+$", "", name) == stem
    ]
    return rows[0] if len(rows) == 1 else None


def _native_evidence(pe, owner, method, address, body):
    return dict(
        type=owner,
        method=method,
        address=hex(address),
        end=hex(address + len(body)),
        nativeBytes=body.hex(),
    )


def prove_history_free_pc(machine, pc):
    """Prove one entry reaches ret without touching or escaping private Param.

    This uses the existing typed-object/valid-work entry preconditions, including
    the export's already-created dictionary item. It supplies no field values.
    Only the exact typed lookup and stack-cookie check may be crossed; a command,
    an uncertain branch, or an unsupported instruction keeps the history gate.
    """
    from .machine import Boundary, Machine
    from ..config import (
        FN_STACK_COOKIE_CHECK,
        OPERATOR_EXPORT_END,
        OPERATOR_EXPORT_JUMP,
    )

    history = machine.table_history
    if history is None or type(pc) is not int:
        return None

    def private_reference(value):
        return (
            isinstance(value, tuple)
            and len(value) == 3
            and value[0] == "pointer"
            and value[1]
            in (
                history.owner,
                ("table_history_value_slot", history.export_type),
                ("table_history_dictionary", history.export_type),
            )
        )

    class Probe(Machine):
        def load(self, address, size, state):
            if address is None or (
                isinstance(address, tuple) and address[:2] == ("pointer", history.owner)
            ):
                raise Boundary("private or unresolved memory read")
            return Machine.load(self, address, size, state)

        def write(self, ins, operand, value, state):
            if operand.type == CS_OP_MEM:
                address = self.address(ins, operand, state)
                if not (
                    isinstance(address, tuple)
                    and address[0] == "pointer"
                    and (
                        address[1] == "stack"
                        or address[1] == "operator"
                        and address[2] in (OPERATOR_EXPORT_END, OPERATOR_EXPORT_JUMP)
                        and operand.size == 1
                        and not private_reference(value)
                    )
                ):
                    raise Boundary("private, escaping, or unreviewed memory write")
            return Machine.write(self, ins, operand, value, state)

    probe = object.__new__(Probe)
    probe.__dict__ = dict(machine.__dict__)
    state = deepcopy(machine.initial(pc))
    # Reject an entry override that already assumes private field contents.
    if any(owner == history.owner for owner, _, _ in state["mem"]):
        return None
    address = int(machine.row["address"], 16)
    path, lookups, seen = [], [], set()
    scalar = {
        "nop",
        "endbr64",
        "lea",
        "push",
        "pop",
        "mov",
        "movabs",
        "movsx",
        "movsxd",
        "movzx",
        "add",
        "sub",
        "xor",
        "and",
        "or",
        "cmp",
        "test",
        "shr",
        "shl",
        "sar",
        "imul",
        "inc",
        "dec",
        "neg",
    }
    try:
        for _ in range(512):
            stack = state["regs"].get("rsp")
            if (
                address in seen
                or address not in probe.ins
                or not isinstance(stack, tuple)
                or stack[:2] != ("pointer", "stack")
            ):
                return None
            seen.add(address)
            ins = probe.ins[address]
            path.append(dict(address=hex(address), nativeBytes=ins.bytes.hex()))
            if ins.mnemonic == "ret":
                value = state["regs"].get("rax")
                ended = probe.load(pointer("operator", OPERATOR_EXPORT_END), 1, state)
                if (
                    ins.operands
                    or state["regs"].get("rsp") != pointer("stack")
                    or not isinstance(value, int)
                    or ended not in (0, 1)
                ):
                    return None
                return dict(
                    kind="native_pc_history_independence",
                    programCounter=pc,
                    nativeMethod={
                        k: machine.row[k] for k in ("type", "method", "address", "end")
                    },
                    returnAddress=hex(address),
                    returnValue=bool(value & 0xFF),
                    tableEnded=bool(ended),
                    nativePath=path,
                    lookupSites=lookups,
                    preconditions=[
                        "existing_typed_object_and_valid_work_entry_model",
                        "export_runtime_id_dictionary_item_already_created",
                        "original_stack_cookie_check_preserved",
                    ],
                )
            if ins.mnemonic == "call":
                event = probe.event(ins, state)
                handled, value = history.call(event, state)
                if handled:
                    lookups.append(event["site"])
                elif not (
                    event.get("direct")
                    and event["target"] == FN_STACK_COOKIE_CHECK
                    and not private_reference(event["arguments"][0])
                ):
                    return None
                state = probe.complete_call(state, event, None)
                if handled:
                    state["regs"]["rax"] = value
                address += ins.size
                continue
            if ins.mnemonic == "btr":
                op = ins.operands
                if not (
                    len(op) == 2
                    and op[0].type == CS_OP_REG
                    and op[1].type == CS_OP_IMM
                    and op[1].imm == 63
                    and (
                        isinstance(value := probe.read(ins, op[0], state), int)
                        or isinstance(value, tuple)
                        and value[:2] == ("pointer", "stack")
                        or history.tagged_reference(value)
                    )
                ):
                    return None
            elif ins.mnemonic not in scalar and not ins.mnemonic.startswith("j"):
                return None
            address = probe.step(ins, state)
    except (Boundary, KeyError, TypeError, ValueError):
        return None
    return None


class TableHistory:
    """One export object's dictionary identity and one native history pair."""

    def __init__(self, export_type, dictionary_offset, runtime_offset, lookup, fields):
        self.export_type = export_type
        self.owner = ("table_history", export_type)
        self.dictionary_offset = dictionary_offset
        self.runtime_offset = runtime_offset
        self.lookup = lookup
        self.fields = fields
        self.read_offsets = set()
        self.read_sites = {}
        self.escaped_sites = set()
        self.candidates = {}
        self.evidence = []
        self.identity_evidence = []
        self.complete_discovery = False
        self.local_pairs = []
        self.formula_enabled = False
        self.formula_specs = {}

    def key(self, offset):
        return "table_history:" + self.export_type + ":" + self.fields[offset]

    def private_field(self, address, size):
        if not (
            isinstance(address, tuple)
            and len(address) == 3
            and address[:2] == ("pointer", self.owner)
        ):
            return []
        start = address[2]
        return [
            (offset, name)
            for offset, name in self.fields.items()
            if start < offset + 4 and offset < start + size
        ]

    def load(self, address, size, state):
        if address == pointer("operator", self.dictionary_offset) and size == 8:
            return True, pointer(("table_history_dictionary", self.export_type))
        if address == pointer("export", self.runtime_offset) and size == 4:
            # A symbolic fixture identity, not an assertion about a running ID.
            return True, RUNTIME_FIXTURE_ID
        if (
            address == pointer(("table_history_value_slot", self.export_type))
            and size == 8
        ):
            return True, pointer(self.owner)
        return False, None

    def call(self, event, state):
        args = event["arguments"]
        if (
            event.get("direct")
            and event["target"] == self.lookup
            and len(args) >= 3
            and args[1] == pointer(("table_history_dictionary", self.export_type))
            and args[2] == RUNTIME_FIXTURE_ID
        ):
            # The export's setup creates this entry. A missing key is the native
            # exception path, not a normal history whose field value is zero.
            return True, pointer(("table_history_value_slot", self.export_type))
        return False, None

    def tagged_reference(self, value):
        return value == pointer(("table_history_value_slot", self.export_type))

    def updates(self, address, size, value):
        fields = self.private_field(address, size)
        return {
            self.key(offset): (
                _signed(value >> (8 * (offset - address[2])))
                if isinstance(value, int)
                and address[2] <= offset
                and offset + 4 <= address[2] + size
                else None
            )
            for offset, _ in fields
        }

    def history_cases(self):
        """Explicit predicates; an unmatched or absent history remains unknown."""
        if self.local_pairs or self.formula_enabled:
            return []
        result = []
        for values, sites in sorted(self.candidates.items()):
            mapping = {offset: value for offset, value in values}
            if set(mapping) != self.read_offsets:
                continue
            result.append(
                dict(
                    values={
                        (self.owner, off, 4): val & 0xFFFFFFFF for off, val in values
                    },
                    expression=dict(
                        kind="all",
                        items=[
                            dict(
                                kind="compare",
                                operator="eq",
                                left=dict(
                                    kind="runtime",
                                    key=self.key(off),
                                    source="行为表保存的前次随机区间",
                                ),
                                right=dict(kind="constant", value=val),
                            )
                            for off, val in values
                        ],
                    ),
                    label="前次随机区间 "
                    + ", ".join(f"{self.fields[o]}={v}" for o, v in values),
                    evidence=dict(
                        nativeStoreSites=sorted(sites), methods=deepcopy(self.evidence)
                    ),
                )
            )
        return result

    def pair_for(self, address, size):
        """Return the pair actually read here; unrelated pairs stay untouched."""
        return next(
            (pair for pair in self.local_pairs if pair.private_field(address, size)),
            None,
        )

    def input_definitions(self):
        return {
            self.key(offset): dict(
                label="前次随机区间" + ("上界" if "Max_" in name else "下界"),
                number=True,
                min=-0x80000000 if self.formula_enabled else -1,
                max=0x7FFFFFFF,
                hint=f"{self.export_type}.{name}；仅在此处读取该历史，其他记录不设默认值",
            )
            for offset, name in self.fields.items()
        }


def _switch_targets(probe, ins, state):
    """Only the compiler's bounded signed-offset table dispatch form."""
    order = sorted(probe.ins)
    index = order.index(ins.address)
    recent = [probe.ins[a] for a in order[max(0, index - 12) : index]]
    if len(recent) < 3 or ins.operands[0].type != CS_OP_REG:
        return []
    target = register(ins, ins.operands[0].reg)
    addition, load = recent[-1], recent[-2]
    if not (
        addition.mnemonic == "add"
        and all(o.type == CS_OP_REG for o in addition.operands)
        and register(addition, addition.operands[0].reg) == target
        and load.mnemonic == "movsxd"
        and load.operands[1].type == CS_OP_MEM
        and register(load, load.operands[0].reg) == target
        and load.operands[1].mem.scale == 4
    ):
        return []
    base = state["regs"].get(register(addition, addition.operands[1].reg))
    if not isinstance(base, int) or load.operands[1].mem.disp:
        return []
    if register(load, load.operands[1].mem.base) != register(
        addition, addition.operands[1].reg
    ):
        return []
    guards = [
        x.operands[1].imm
        for x in recent
        if x.mnemonic == "cmp"
        and len(x.operands) == 2
        and x.operands[1].type == CS_OP_IMM
        and 0 <= x.operands[1].imm <= 256
    ]
    if len(guards) != 1:
        return []
    raw = probe.pe.read(base, 4 * (guards[0] + 1))
    if len(raw) != 4 * (guards[0] + 1):
        return []
    targets = {base + offset for (offset,) in struct.iter_unpack("<i", raw)}
    return sorted(targets) if targets <= probe.ins.keys() else []


def _discover(machine, history, *, reviewed_calls=False):
    """Reuse the native evaluator, without treating candidate paths as semantics."""
    from .machine import Machine, Boundary

    class Probe(Machine):
        def event(self, ins, state):
            event = Machine.event(self, ins, state)
            if event["target"] not in {history.lookup, ("random_generator",)} and any(
                isinstance(arg, tuple) and arg[:2] == ("pointer", history.owner)
                for arg in event["arguments"]
            ):
                history.escaped_sites.add(ins.address)
            return event

        def read(self, ins, operand, state):
            if operand.type == CS_OP_MEM:
                fields = history.private_field(
                    self.address(ins, operand, state), operand.size
                )
                if fields:
                    history.read_sites.setdefault(ins.address, set()).update(
                        off for off, _ in fields
                    )
            return Machine.read(self, ins, operand, state)

        def step(self, ins, state):
            if (
                ins.mnemonic == "btr"
                and len(ins.operands) == 2
                and ins.operands[1].type == CS_OP_IMM
                and ins.operands[1].imm == 63
                and history.tagged_reference(self.read(ins, ins.operands[0], state))
            ):
                return ins.address + ins.size
            return Machine.step(self, ins, state)

        def load(self, address, size, state):
            handled, value = history.load(address, size, state)
            if handled:
                return value
            for offset, _ in history.private_field(address, size):
                history.read_offsets.add(offset)
            return Machine.load(self, address, size, state)

        def write(self, ins, operand, value, state):
            fields = []
            if operand.type == CS_OP_MEM:
                location = self.address(ins, operand, state)
                fields = history.private_field(location, operand.size)
                if (
                    isinstance(value, tuple)
                    and value[:2] == ("pointer", history.owner)
                    and not (
                        isinstance(location, tuple)
                        and location[:2] == ("pointer", "stack")
                    )
                ):
                    history.escaped_sites.add(ins.address)
            Machine.write(self, ins, operand, value, state)
            if fields:
                state.setdefault("history_written", set()).update(
                    off for off, _ in fields
                )
                state.setdefault("history_sites", set()).add(hex(ins.address))
                if set(history.fields) <= state["history_written"]:
                    values = (
                        tuple(
                            (
                                off,
                                _signed(
                                    Machine.load(
                                        self, pointer(history.owner, off), 4, state
                                    )
                                ),
                            )
                            for off in sorted(history.fields)
                        )
                        if all(
                            isinstance(
                                Machine.load(
                                    self, pointer(history.owner, off), 4, state
                                ),
                                int,
                            )
                            for off in history.fields
                        )
                        else ()
                    )
                    if values:
                        history.candidates.setdefault(values, set()).update(
                            state["history_sites"]
                        )

    probe = object.__new__(Probe)
    probe.__dict__ = dict(machine.__dict__)
    # Parent integration can call the same public load hook; discovery uses its
    # own hook above and must not recursively initialize another history model.
    probe.table_history = None
    pcs = {0}
    order = sorted(probe.ins)
    for index, address in enumerate(order):
        ins = probe.ins[address]
        if ins.mnemonic == "jmp" and ins.operands[0].type == CS_OP_REG:
            recent = [probe.ins[a] for a in order[max(0, index - 12) : index]]
            guards = [
                x.operands[1].imm
                for x in recent
                if x.mnemonic == "cmp"
                and len(x.operands) == 2
                and x.operands[1].type == CS_OP_IMM
                and 0 <= x.operands[1].imm <= 256
            ]
            if len(guards) == 1:
                pcs.update(range(guards[0] + 1))
            break
    pending = deque(
        (int(machine.row["address"], 16), probe.initial(pc)) for pc in sorted(pcs)
    )
    seen = set()
    count = 0
    while pending and count < MAX_DISCOVERY_STEPS:
        address, state = pending.popleft()
        if address not in probe.ins:
            continue
        signature = (
            address,
            repr(state["regs"]),
            repr(state["mem"]),
            repr(state.get("history_written")),
        )
        if signature in seen:
            continue
        seen.add(signature)
        ins = probe.ins[address]
        count += 1
        following = address + ins.size
        if ins.mnemonic == "call":
            event = probe.event(ins, state)
            handled, value = history.call(event, state)
            variable_write = False
            if (
                reviewed_calls
                and not handled
                and event["target"] != ("random_generator",)
            ):
                from .command_effects import reviewed_command_effect

                bound = probe.bind(event)
                if bound and bound.get("commandType"):
                    effect = reviewed_command_effect(
                        bound,
                        probe.command_evidence.get(bound["commandType"]),
                        probe.variable_catalog,
                    )
                    variable_write = effect is not None and effect.get("effect") in {
                        "set_float_value",
                        "set_bool_value",
                        "set_timer_state",
                    }
            if (
                not handled
                and not variable_write
                and event["target"] != ("random_generator",)
            ):
                # Discovery needs only the interval read/constant write region.
                # It does not execute, or assume effects for, game commands.
                continue
            state = probe.complete_call(state, event, None)
            if handled:
                state["regs"]["rax"] = value
            state["history_written"], state["history_sites"] = set(), set()
            pending.append((following, state))
        elif ins.mnemonic.startswith("j"):
            try:
                pending.append((probe.step(ins, state), state))
            except Boundary:
                targets = (
                    [ins.operands[0].imm, following]
                    if ins.operands[0].type == CS_OP_IMM and ins.mnemonic != "jmp"
                    else _switch_targets(probe, ins, state)
                )
                for target in targets:
                    pending.append((target, deepcopy(state)))
        else:
            try:
                pending.append((probe.step(ins, state), state))
            except Boundary:
                continue
    history.complete_discovery = not pending


def _import_name(pe, address):
    """Resolve an import thunk by the PE's original lookup/name table."""
    native = list(_decoder().disasm(pe.read(address, 6), address))
    if len(native) != 1 or native[0].mnemonic != "jmp":
        return None
    ins = native[0]
    operand = ins.operands[0]
    if operand.type != CS_OP_MEM or ins.reg_name(operand.mem.base) != "rip":
        return None
    slot = ins.address + ins.size + operand.mem.disp
    header = struct.unpack_from("<I", pe.data, 0x3C)[0]
    rva, size = struct.unpack_from("<II", pe.data, header + 24 + 120)
    for offset in range(0, size, 20):
        raw = pe.read(pe.base + rva + offset, 20)
        if len(raw) != 20:
            return None
        original, _, _, _, first = struct.unpack("<IIIII", raw)
        if not any(raw):
            break
        if not original:
            continue
        for index in range(4096):
            entry = int.from_bytes(pe.read(pe.base + original + 8 * index, 8), "little")
            if not entry:
                break
            if pe.base + first + 8 * index == slot:
                if entry & (1 << 63):
                    return None
                return (
                    pe.read(pe.base + entry + 2, 128).split(b"\0", 1)[0].decode("ascii")
                )
    return None


def _constructor_case(machine, history, *, allow_avx_fill=False):
    found = _method(machine.metadata, history.export_type + ".Param", ".ctor")
    if found is None:
        return
    method, info = found
    address = int(info["function"], 16)
    instructions = []
    for ins in _decoder().disasm(machine.pe.read(address, 512), address):
        instructions.append(ins)
        if ins.mnemonic in {"ret", "jmp"}:
            break
    if not instructions or instructions[-1].mnemonic not in {"ret", "jmp"}:
        return
    values = {}
    # A tiny constructor can directly initialize adjacent Int32 fields.
    for ins in instructions:
        op = ins.operands
        if ins.mnemonic == "ret":
            break
        if not (
            ins.mnemonic == "mov"
            and len(op) == 2
            and op[0].type == CS_OP_MEM
            and op[1].type == CS_OP_IMM
            and ins.reg_name(op[0].mem.base) == "rdx"
            and not op[0].mem.index
        ):
            values = {}
            break
        for off in history.fields:
            if op[0].mem.disp <= off and off + 4 <= op[0].mem.disp + op[0].size:
                values[off] = _signed(op[1].imm >> (8 * (off - op[0].mem.disp)))
    if len(instructions) == 4:
        a, b, c, d = instructions
        if (
            a.mnemonic == "lea"
            and len(a.operands) == 2
            and a.operands[0].type == CS_OP_REG
            and a.reg_name(a.operands[0].reg) == "rcx"
            and a.operands[1].type == CS_OP_MEM
            and a.reg_name(a.operands[1].mem.base) == "rdx"
            and not a.operands[1].mem.index
            and b.mnemonic == "mov"
            and len(b.operands) == 2
            and b.operands[0].type == CS_OP_REG
            and b.reg_name(b.operands[0].reg) == "r8d"
            and b.operands[1].type == CS_OP_IMM
            and c.mnemonic == "mov"
            and c.op_str == "dl, 0xff"
            and d.mnemonic == "jmp"
            and d.operands[0].type == CS_OP_IMM
            and _import_name(machine.pe, d.operands[0].imm) == "memset"
        ):
            start, length = a.operands[1].mem.disp, b.operands[1].imm
            values = {
                off: -1
                for off in history.fields
                if start <= off and off + 4 <= start + length
            }
    if (
        allow_avx_fill
        and len(instructions) >= 4
        and instructions[-2].mnemonic == "vzeroupper"
        and instructions[-1].mnemonic == "ret"
    ):
        zero, ones = instructions[:2]
        if (
            zero.mnemonic == "vxorps"
            and ones.mnemonic == "vcmptrueps"
            and len(zero.operands) == len(ones.operands) == 3
            and all(op.type == CS_OP_REG for op in (*zero.operands, *ones.operands))
            and len(
                {zero.reg_name(op.reg)[3:] for op in zero.operands}
                | {ones.reg_name(op.reg)[3:] for op in ones.operands}
            )
            == 1
        ):
            fills = []
            for ins in instructions[2:-2]:
                op = ins.operands
                if not (
                    ins.mnemonic == "vmovups"
                    and len(op) == 2
                    and op[0].type == CS_OP_MEM
                    and op[1].type == CS_OP_REG
                    and ins.reg_name(op[0].mem.base) == "rdx"
                    and not op[0].mem.index
                    and ins.reg_name(op[1].reg) == ones.reg_name(ones.operands[0].reg)
                ):
                    break
                fills.append((op[0].mem.disp, op[0].size))
            else:
                values = {
                    off: -1
                    for off in history.fields
                    if any(
                        start <= off and off + 4 <= start + size
                        for start, size in fills
                    )
                }
    if set(values) == set(history.fields):
        body = b"".join(ins.bytes for ins in instructions)
        history.evidence.append(
            _native_evidence(
                machine.pe, history.export_type + ".Param", method, address, body
            )
        )
        history.candidates.setdefault(tuple(sorted(values.items())), set()).add(
            hex(address)
        )


def _param_setup_identity(machine, dictionary_offset, runtime_offset, lookup):
    """Prove the export's exact setup creates this Param under its RuntimeID.

    The compiler's checked-present path must skip creation, while the absent
    path allocates the metadata class, calls its constructor, and inserts the
    same object/key. This supplies object identity only, never field values.
    All call targets and field offsets are resolved from current identities.
    """
    from ..config import symbol

    metadata, pe = machine.metadata, machine.pe
    owner = machine.row["type"]
    setup = _method(metadata, owner, "setupOperatorWork")
    constructor = _method(metadata, owner + ".Param", ".ctor")
    insert = _method(metadata, DICT_TYPE, "TryInsert")
    param = metadata.get(owner + ".Param") or {}
    behavior = (metadata.get("System.Collections.Generic.InsertionBehavior") or {}).get(
        "fields", {}
    )
    if not setup or not constructor or not insert or not param.get("address"):
        return None
    setup_name, setup_info = setup
    constructor_name, constructor_info = constructor
    insert_name, insert_info = insert
    if (
        [p.get("type") for p in setup_info.get("params", [])] != [OPERATOR_TYPE]
        or setup_info.get("returns", {}).get("type") != "System.Void"
        or constructor_info.get("params", [])
        or constructor_info.get("returns", {}).get("type") != "System.Void"
        or [p.get("type") for p in insert_info.get("params", [])]
        != ["System.Int32", PARAM_TYPE, "System.Collections.Generic.InsertionBehavior"]
        or insert_info.get("returns", {}).get("type") != "System.Boolean"
        or behavior.get("ThrowOnExisting", {}).get("default") != 2
    ):
        return None
    start = int(setup_info["function"], 16)
    constructor_address = int(constructor_info["function"], 16)
    insert_address = int(insert_info["function"], 16)
    if insert_address != symbol("btable_param_try_insert"):
        return None
    allocate = symbol("managed_object_allocate")
    end = pe.end(start)
    if not 0 < end - start <= 512:
        return None
    body = pe.read(start, end - start)
    native = list(_decoder().disasm(body, start))
    if len(native) not in (31, 36) or sum(ins.size for ins in native) != len(body):
        return None
    inline = len(native) == 31
    expected = [
        ("push", "r14"),
        ("push", "rsi"),
        ("push", "rdi"),
        ("push", "rbx"),
        ("sub", "rsp,0x28"),
        ("mov", "rbx,r8"),
        ("mov", "rdi,rdx"),
        ("mov", "rsi,rcx"),
        ("mov", f"rdx,qwordptr[r8+{dictionary_offset:#x}]"),
        ("mov", f"r8d,dwordptr[rdi+{runtime_offset:#x}]"),
        ("call", hex(lookup)),
        ("test", "rax,rax"),
        ("jne", hex(native[29].address)),
        ("mov", f"rbx,qwordptr[rbx+{dictionary_offset:#x}]"),
        ("mov", f"edi,dwordptr[rdi+{runtime_offset:#x}]"),
        None,
        ("mov", "rcx,rsi"),
        ("xor", "r8d,r8d"),
        ("call", hex(allocate)),
        ("mov", "r14,rax"),
        ("mov", "rcx,rsi"),
        ("mov", "rdx,rax"),
        ("call", hex(constructor_address)),
        ("mov", "byteptr[rsp+0x20],2"),
        ("mov", "rcx,rsi"),
        ("mov", "rdx,rbx"),
        ("mov", "r8d,edi"),
        ("mov", "r9,r14"),
        ("call", hex(insert_address)),
        ("nop", ""),
        ("add", "rsp,0x28"),
        ("pop", "rbx"),
        ("pop", "rdi"),
        ("pop", "rsi"),
        ("pop", "r14"),
        ("ret", ""),
    ]
    constructor_proof = None
    if inline:
        private = {
            name: field
            for name, field in param.get("fields", {}).items()
            if "default" not in field
        }
        pairs = {
            name.rsplit("_", 1)[-1]
            for name in private
            if re.fullmatch(r"BefoRandom(?:Max|Min)_\d+", name)
        }
        if (
            len(private) != 2
            or len(pairs) != 1
            or {
                (
                    re.sub(r"_\d+$", "", name),
                    field.get("type"),
                    field.get("offset_from_base"),
                )
                for name, field in private.items()
            }
            != {
                ("BefoRandomMax", "System.Int32", "0x10"),
                ("BefoRandomMin", "System.Int32", "0x14"),
            }
        ):
            return None
        constructor_body = bytes.fromhex("48c74210ffffffffc3")
        if pe.read(constructor_address, len(constructor_body)) != constructor_body:
            return None
        constructor_proof = _native_evidence(
            pe,
            owner + ".Param",
            constructor_name,
            constructor_address,
            constructor_body,
        )
        expected = [
            ("push", "rsi"),
            ("push", "rdi"),
            ("push", "rbx"),
            ("sub", "rsp,0x30"),
            ("mov", "rbx,r8"),
            ("mov", "rdi,rdx"),
            ("mov", "rsi,rcx"),
            ("mov", f"rdx,qwordptr[r8+{dictionary_offset:#x}]"),
            ("mov", f"r8d,dwordptr[rdi+{runtime_offset:#x}]"),
            ("call", hex(lookup)),
            ("test", "rax,rax"),
            ("jne", hex(native[25].address)),
            ("mov", f"rbx,qwordptr[rbx+{dictionary_offset:#x}]"),
            ("mov", f"edi,dwordptr[rdi+{runtime_offset:#x}]"),
            None,
            ("mov", "rcx,rsi"),
            ("xor", "r8d,r8d"),
            ("call", hex(allocate)),
            ("mov", "qwordptr[rax+0x10],0xffffffffffffffff"),
            ("mov", "byteptr[rsp+0x20],2"),
            ("mov", "rcx,rsi"),
            ("mov", "rdx,rbx"),
            ("mov", "r8d,edi"),
            ("mov", "r9,rax"),
            ("call", hex(insert_address)),
            ("nop", ""),
            ("add", "rsp,0x30"),
            ("pop", "rbx"),
            ("pop", "rdi"),
            ("pop", "rsi"),
            ("ret", ""),
        ]
    if any(
        value is not None and (ins.mnemonic, ins.op_str.replace(" ", "")) != value
        for ins, value in zip(native, expected)
    ):
        return None
    load = native[14 if inline else 15]
    op = load.operands
    if not (
        load.mnemonic == "mov"
        and len(op) == 2
        and op[0].type == CS_OP_REG
        and load.reg_name(op[0].reg) == "rdx"
        and op[1].type == CS_OP_MEM
        and op[1].size == 8
        and load.reg_name(op[1].mem.base) == "rip"
        and not op[1].mem.index
    ):
        return None
    slot = load.address + load.size + op[1].mem.disp
    if int.from_bytes(pe.read(slot, 8), "little") != int(param["address"], 16):
        return None
    proof = dict(
        _native_evidence(pe, owner, setup_name, start, body),
        kind="typed_param_dictionary_setup",
        paramType=owner + ".Param",
        dictionaryField=dict(
            type=OPERATOR_TYPE, field="ExportTableParam", offset=hex(dictionary_offset)
        ),
        keyField=dict(
            type=EXPORT_TYPE,
            field="<RuntimeID>k__BackingField",
            offset=hex(runtime_offset),
        ),
        classSymbol=dict(type=owner + ".Param", slot=hex(slot)),
        allocationSymbol="managed_object_allocate",
        constructor=dict(type=owner + ".Param", method=constructor_name),
        insertion=dict(
            type=DICT_TYPE,
            method=insert_name,
            symbol="btable_param_try_insert",
            behavior="ThrowOnExisting",
        ),
        existingItem="preserved",
        fieldValues="not_assumed",
    )
    if constructor_proof is not None:
        proof["constructor"]["inlined"] = True
        proof["constructorEvidence"] = constructor_proof
    return proof


def recover_table_history(machine, *, local=False):
    """Recover an interval, or explicitly enabled pairs at their actual reads."""
    metadata = machine.metadata
    if metadata is None or machine.pe is None:
        return None
    owner = machine.row["type"]
    param = metadata.get(owner + ".Param")
    if not param or param.get("parent") != PARAM_TYPE:
        return None
    operator = metadata.fields(OPERATOR_TYPE).get("ExportTableParam", {})
    runtime = metadata.fields(EXPORT_TYPE).get("<RuntimeID>k__BackingField", {})
    method = _method(metadata, DICT_TYPE, "FindValue")
    if (
        operator.get("type") != DICT_TYPE
        or runtime.get("type") != "System.Int32"
        or method is None
    ):
        return None
    name, info = method
    if (
        [p.get("type") for p in info.get("params", [])] != ["System.Int32"]
        or info.get("returns", {}).get("type") != PARAM_TYPE
        or info.get("returns", {}).get("modifier") != "ByRef"
    ):
        return None
    lookup = int(info["function"], 16)
    if not any(
        ins.mnemonic == "call"
        and ins.operands[0].type == CS_OP_IMM
        and ins.operands[0].imm == lookup
        for ins in machine.ins.values()
    ):
        return None
    proof = json.loads(
        (EVIDENCE_DIR / "table_state.v1.json").read_text(encoding="utf-8")
    )["lookup"]
    if (
        proof["type"] != DICT_TYPE
        or proof["method"] != name
        or int(proof["address"], 16) != lookup
    ):
        raise ValueError("行为表私有参数的字典查找方法身份变化")
    expected = bytes.fromhex(proof["nativeBytes"])
    if machine.pe.read(lookup, len(expected)) != expected:
        raise ValueError("行为表私有参数的字典查找原生字节变化")
    source_evidence = dict(
        type=owner,
        method=machine.row.get("method"),
        address=machine.row["address"],
        end=machine.row.get("end"),
    )
    identity = _param_setup_identity(
        machine,
        int(operator["offset_from_base"], 16),
        int(runtime["offset_from_base"], 16),
        lookup,
    )

    def identity_only():
        if identity is None:
            return None
        result = TableHistory(
            owner,
            int(operator["offset_from_base"], 16),
            int(runtime["offset_from_base"], 16),
            lookup,
            {},
        )
        result.identity_evidence = [identity]
        result.evidence = [source_evidence, proof, identity]
        return result

    fields = {}
    for field, description in param.get("fields", {}).items():
        if "default" in description:
            continue
        if (
            re.fullmatch(r"BefoRandom(?:Max|Min)_\d+", field)
            and description.get("type") == "System.Int32"
        ):
            fields[int(description["offset_from_base"], 16)] = field
        else:
            # A new private layout needs its own field lifetime/escape review.
            identity = None
    if not fields:
        return identity_only()
    history = TableHistory(
        owner,
        int(operator["offset_from_base"], 16),
        int(runtime["offset_from_base"], 16),
        lookup,
        fields,
    )
    history.identity_evidence = [identity] if identity is not None else []
    # First discover accesses with all metadata fields, then keep only one pair.
    _discover(machine, history, reviewed_calls=local)
    used = {off: fields[off] for off in history.read_offsets}
    suffixes = {name.rsplit("_", 1)[1] for name in used.values()}
    if local and len(suffixes) > 1:
        if not history.complete_discovery:
            return identity_only()
        history.fields = used
        history.evidence = [source_evidence, proof, *history.identity_evidence]
        for suffix in sorted(suffixes):
            pair_fields = {
                off: name
                for off, name in used.items()
                if name.rsplit("_", 1)[1] == suffix
            }
            if (
                len(pair_fields) != 2
                or not any("Max_" in n for n in pair_fields.values())
                or not any("Min_" in n for n in pair_fields.values())
            ):
                return identity_only()
            pair = TableHistory(
                owner,
                history.dictionary_offset,
                history.runtime_offset,
                lookup,
                pair_fields,
            )
            _discover(machine, pair, reviewed_calls=True)
            if (
                not pair.complete_discovery
                or not pair.candidates
                or set(pair_fields) != pair.read_offsets
            ):
                return identity_only()
            pair.identity_evidence = list(history.identity_evidence)
            pair.evidence = [source_evidence, proof, *pair.identity_evidence]
            _constructor_case(machine, pair, allow_avx_fill=True)
            history.local_pairs.append(pair)
        return history
    if (
        len(used) != 2
        or len(suffixes) != 1
        or not any("Max_" in n for n in used.values())
        or not any("Min_" in n for n in used.values())
    ):
        return identity_only()
    history.fields = used
    history.candidates = {}
    _discover(machine, history, reviewed_calls=local)
    if not history.complete_discovery or not history.candidates:
        return identity_only()
    history.evidence.append(source_evidence)
    history.evidence.append(proof)
    history.evidence.extend(history.identity_evidence)
    _constructor_case(machine, history)
    return history
