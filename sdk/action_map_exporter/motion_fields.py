"""Recover constructor MotionSet fields under the dump's RDX-this ABI.

Only known 32-bit Motion fields receive values. Control-flow joins retain
agreement, writes kill overlapping values, and calls follow the same object
through its constructor lineage. Unsupported effects yield unknown values.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace

from iced_x86 import (
    Code,
    Decoder,
    FlowControl,
    Instruction,
    InstructionInfoFactory,
    MemorySizeExt,
    Mnemonic,
    OpAccess,
    OpKind,
    Register,
    RegisterExt,
)

from .il2cpp_methods import Il2CppMethodCatalog, MotionField
from .models import Il2CppMethod, MotionSetHit
from .motion_catalogs import MotionTargetCatalog
from .pe import PeImage
from .scanners import _code_name, _function_length, _IMMEDIATE_KINDS

_WRITES = {
    OpAccess.WRITE,
    OpAccess.COND_WRITE,
    OpAccess.READ_WRITE,
    OpAccess.READ_COND_WRITE,
}
_VOLATILE = {
    Register.RAX,
    Register.RCX,
    Register.RDX,
    Register.R8,
    Register.R9,
    Register.R10,
    Register.R11,
}
_ARGUMENTS = {Register.RCX, Register.RDX, Register.R8, Register.R9}


@dataclass(frozen=True, slots=True)
class _Constant:
    value: int
    instruction: int
    code: int


@dataclass(frozen=True, slots=True)
class _Assignment:
    value: int
    method: Il2CppMethod
    instruction: int
    code: int
    load_instruction: int
    write_offset: int
    write_size: int
    lane: int
    chain: tuple[tuple[str, str, int, int], ...] = ()


@dataclass(slots=True)
class _State:
    aliases: dict[int, int] = field(default_factory=dict)
    constants: dict[int, _Constant] = field(default_factory=dict)
    # Absent means untouched; None means written but no longer known.
    values: dict[int, _Assignment | None] = field(default_factory=dict)

    def copy(self) -> _State:
        return _State(dict(self.aliases), dict(self.constants), dict(self.values))


def _join(left: _State, right: _State) -> _State:
    return _State(
        {k: v for k, v in left.aliases.items() if right.aliases.get(k) == v},
        {k: v for k, v in left.constants.items() if right.constants.get(k) == v},
        {
            k: (
                left.values[k]
                if k in left.values
                and k in right.values
                and left.values[k] == right.values[k]
                else None
            )
            for k in left.values.keys() | right.values.keys()
        },
    )


class ConstructorMotionScanner:
    def __init__(
        self,
        image: PeImage,
        methods: Il2CppMethodCatalog,
        targets: MotionTargetCatalog,
        max_function_bytes: int,
    ) -> None:
        self.image = image
        self.methods = methods
        self.targets = targets
        self.max_function_bytes = max_function_bytes
        self._instructions: dict[int, dict[int, Instruction]] = {}
        self._summaries: dict[
            tuple[str, Il2CppMethod], dict[int, _Assignment | None]
        ] = {}
        self._info = InstructionInfoFactory()

    def scan(self, scope: str, method: Il2CppMethod) -> list[MotionSetHit]:
        if not method.method_name.startswith(".ctor"):
            return []
        fields = self.methods.motion_fields(method.type_name)
        if not fields:
            return []
        values = self._analyze(method.type_name, method, fields, ())
        hits = []
        for offset, value in sorted(values.items()):
            if value is None:
                continue
            target = self.targets.find(scope, value.value)
            if target is None:
                continue
            member = fields[offset]
            hits.append(
                MotionSetHit(
                    action_class=method.type_name,
                    method_name=value.method.method_name,
                    function_address=value.method.function_address,
                    instruction_address=value.instruction,
                    instruction_code=_code_name(value.code),
                    immediate_operand=1,
                    target=target,
                    field_evidence=(
                        ("declaringType", member.declaring_type),
                        ("fieldName", member.name),
                        ("fieldOffset", offset),
                        ("fieldWidth", 4),
                        ("writeOffset", value.write_offset),
                        ("writeWidth", value.write_size),
                        ("laneByteOffset", value.lane),
                        ("loadInstructionAddress", f"0x{value.load_instruction:x}"),
                        ("initializerType", value.method.type_name),
                    ),
                    constructor_chain=value.chain,
                )
            )
        return hits

    def _decode(self, method: Il2CppMethod) -> dict[int, Instruction]:
        address = method.function_address
        if address not in self._instructions:
            size = _function_length(
                self.methods.function_addresses, address, self.max_function_bytes
            )
            code = self.image.read_function_bytes(address, size)
            self._instructions[address] = {
                i.ip: i for i in Decoder(64, code, ip=address)
            }
        return self._instructions[address]

    def _analyze(
        self,
        layout_type: str,
        method: Il2CppMethod,
        fields: dict[int, MotionField],
        stack: tuple[tuple[str, int], ...],
    ) -> dict[int, _Assignment | None]:
        key = (layout_type, method)
        frame = (method.type_name, method.function_address)
        if frame in stack or len(stack) >= 24:
            return dict.fromkeys(fields)
        if key in self._summaries:
            return self._summaries[key]
        instructions = self._decode(method)
        incoming = {method.function_address: _State(aliases={Register.RDX: 0})}
        pending = deque(incoming)
        result: _State | None = None
        steps = 0
        while pending:
            address = pending.popleft()
            state = incoming[address].copy()
            instruction = instructions.get(address)
            steps += 1
            if instruction is None or instruction.code == Code.INVALID or steps > 16384:
                return dict.fromkeys(fields)
            flow = instruction.flow_control
            if flow in {FlowControl.CALL, FlowControl.INDIRECT_CALL}:
                self._call(
                    state, instruction, layout_type, method, fields, (*stack, frame)
                )
                successors = (instruction.next_ip,)
            elif flow == FlowControl.UNCONDITIONAL_BRANCH:
                destination = instruction.near_branch_target
                if destination in instructions:
                    successors = (destination,)
                else:
                    self._call(
                        state, instruction, layout_type, method, fields, (*stack, frame)
                    )
                    successors = ()
            elif flow == FlowControl.RETURN:
                successors = ()
            elif flow in {FlowControl.NEXT, FlowControl.CONDITIONAL_BRANCH}:
                self._transfer(state, instruction, method, fields)
                successors = (
                    (instruction.next_ip, instruction.near_branch_target)
                    if flow == FlowControl.CONDITIONAL_BRANCH
                    else (instruction.next_ip,)
                )
            else:
                return dict.fromkeys(fields)
            if not successors:
                result = state if result is None else _join(result, state)
            for destination in successors:
                previous = incoming.get(destination)
                merged = state.copy() if previous is None else _join(previous, state)
                if previous != merged:
                    incoming[destination] = merged
                    pending.append(destination)
        values = result.values if result is not None else dict.fromkeys(fields)
        self._summaries[key] = values
        return values

    def _call(
        self,
        state: _State,
        instruction: Instruction,
        layout_type: str,
        method: Il2CppMethod,
        fields: dict[int, MotionField],
        stack: tuple[tuple[str, int], ...],
    ) -> None:
        direct = instruction.flow_control in {
            FlowControl.CALL,
            FlowControl.UNCONDITIONAL_BRANCH,
        }
        callee = (
            self.methods.constructor_at(
                method.type_name, instruction.near_branch_target
            )
            if direct
            else None
        )
        if callee is not None and state.aliases.get(Register.RDX) == 0:
            values = self._analyze(layout_type, callee, fields, stack)
            site = (
                method.type_name,
                method.method_name,
                method.function_address,
                instruction.ip,
            )
            state.values.update(
                {
                    offset: (
                        replace(value, chain=(site, *value.chain))
                        if value is not None
                        else None
                    )
                    for offset, value in values.items()
                }
            )
        elif any(reg in state.aliases for reg in _ARGUMENTS):
            # An unmodelled call that receives this (or an interior pointer)
            # may overwrite any member. Do not retain stale initializations.
            state.values.update(dict.fromkeys(fields))
        for reg in _VOLATILE:
            state.aliases.pop(reg, None)
            state.constants.pop(reg, None)

    def _transfer(
        self,
        state: _State,
        instruction: Instruction,
        method: Il2CppMethod,
        fields: dict[int, MotionField],
    ) -> None:
        aliases, constants = dict(state.aliases), dict(state.constants)
        info = self._info.info(instruction)
        for used in info.used_registers():
            if used.access in _WRITES:
                reg = RegisterExt.full_register(used.register)
                state.aliases.pop(reg, None)
                state.constants.pop(reg, None)

        constant = None
        alias = None
        if instruction.op_count >= 2:
            kind = instruction.op1_kind
            if kind in _IMMEDIATE_KINDS:
                constant = _Constant(
                    instruction.immediate(1), instruction.ip, instruction.code
                )
            elif kind == OpKind.REGISTER:
                reg = RegisterExt.full_register(instruction.op1_register)
                constant = constants.get(reg)
                alias = (
                    aliases.get(reg)
                    if RegisterExt.size(instruction.op1_register) == 8
                    else None
                )

        if instruction.op0_kind == OpKind.REGISTER:
            dest = instruction.op0_register
            reg = RegisterExt.full_register(dest)
            size = RegisterExt.size(dest)
            if instruction.mnemonic == Mnemonic.MOV:
                if constant is not None and size in (4, 8):
                    state.constants[reg] = replace(
                        constant, value=constant.value & ((1 << (size * 8)) - 1)
                    )
                if alias is not None and size == 8:
                    state.aliases[reg] = alias
            elif instruction.mnemonic == Mnemonic.LEA and size == 8:
                offset = _object_offset(instruction, aliases)
                if offset is not None:
                    state.aliases[reg] = offset

        writes_memory = any(m.access in _WRITES for m in info.used_memory())
        if (
            writes_memory
            and instruction.memory_base in aliases
            and instruction.memory_index != Register.NONE
        ):
            state.values.update(dict.fromkeys(fields))
        offset = _object_offset(instruction, aliases)
        if offset is None or not writes_memory:
            return
        size = MemorySizeExt.size(instruction.memory_size)
        touched = [p for p in fields if p < offset + size and offset < p + 4]
        state.values.update(dict.fromkeys(touched))
        if (
            instruction.mnemonic != Mnemonic.MOV
            or instruction.op0_kind != OpKind.MEMORY
            or constant is None
        ):
            return
        # A packed value is accepted only when BOTH lanes have explicit 32-bit
        # Motion metadata. An integer next to a pointer must never be split.
        if size not in (4, 8) or any(
            offset + lane not in fields for lane in range(0, size, 4)
        ):
            return
        for lane in range(0, size, 4):
            unsigned = (constant.value >> (lane * 8)) & 0xFFFFFFFF
            value = unsigned if unsigned < 0x80000000 else unsigned - 0x100000000
            state.values[offset + lane] = _Assignment(
                value,
                method,
                instruction.ip,
                instruction.code,
                constant.instruction,
                offset,
                size,
                lane,
            )


def _object_offset(instruction: Instruction, aliases: dict[int, int]) -> int | None:
    if instruction.memory_index != Register.NONE:
        return None
    base = aliases.get(instruction.memory_base)
    if base is None:
        return None
    displacement = instruction.memory_displacement
    if displacement >= 1 << 63:
        displacement -= 1 << 64
    return base + displacement
