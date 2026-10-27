from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from iced_x86 import (
    Code,
    Decoder,
    FlowControl,
    Instruction,
    InstructionInfoFactory,
    Mnemonic,
    OpAccess,
    OpKind,
    Register,
    RegisterExt,
)

from .models import (
    AmmoItemMapEvidence,
    AmmoNameRecord,
    DirectCallHit,
    Il2CppMethod,
    MotionSetHit,
    MotionTarget,
)
from .motion_catalogs import MotionTargetCatalog
from .motion_groups import MotionGroupCatalog
from .pe import PeImage
from .shells import ShellCatalog

_IMMEDIATE_KINDS = {
    OpKind.IMMEDIATE8,
    OpKind.IMMEDIATE8_2ND,
    OpKind.IMMEDIATE16,
    OpKind.IMMEDIATE32,
    OpKind.IMMEDIATE64,
    OpKind.IMMEDIATE8TO16,
    OpKind.IMMEDIATE8TO32,
    OpKind.IMMEDIATE8TO64,
    OpKind.IMMEDIATE32TO64,
}
_NEAR_BRANCH_KINDS = {
    OpKind.NEAR_BRANCH16,
    OpKind.NEAR_BRANCH32,
    OpKind.NEAR_BRANCH64,
}
_CODE_CONSTANT_NAMES = {
    value: name
    for name, value in vars(Code).items()
    if name.isupper() and isinstance(value, int)
}
_UPPERCASE_CODE_TOKENS = {
    "AL",
    "AX",
    "EAX",
    "RAX",
    "CL",
    "CX",
    "ECX",
    "RCX",
    "DL",
    "DX",
    "EDX",
    "RDX",
    "BL",
    "BX",
    "EBX",
    "RBX",
    "SP",
    "ESP",
    "RSP",
    "BP",
    "EBP",
    "RBP",
    "SI",
    "ESI",
    "RSI",
    "DI",
    "EDI",
    "RDI",
    "ES",
    "CS",
    "SS",
    "DS",
    "FS",
    "GS",
}
_ENCODING_PREFIXES = {"VEX", "EVEX", "XOP", "MVEX"}
_INSTRUCTION_INFO = InstructionInfoFactory()
_READS = {
    OpAccess.READ,
    OpAccess.COND_READ,
    OpAccess.READ_WRITE,
    OpAccess.READ_COND_WRITE,
}
_WRITES = {OpAccess.WRITE, OpAccess.COND_WRITE}
_COMPARISONS = {Mnemonic.CMP, Mnemonic.TEST, Mnemonic.SUB, Mnemonic.XOR}
_ARGUMENT_REGISTERS = {Register.RCX, Register.RDX, Register.R8, Register.R9}
_VOLATILE_REGISTERS = _ARGUMENT_REGISTERS | {
    Register.RAX,
    Register.R10,
    Register.R11,
}


class MotionSetScanner:
    def __init__(
        self,
        image: PeImage,
        targets: MotionTargetCatalog,
        function_addresses: list[int],
        max_function_bytes: int,
        groups: MotionGroupCatalog | None = None,
    ) -> None:
        self.image = image
        self.targets = targets
        self.function_addresses = function_addresses
        self.max_function_bytes = max_function_bytes
        self.groups = groups

    def scan(self, scope: str, method: Il2CppMethod) -> list[MotionSetHit]:
        code = self.image.read_function_bytes(
            method.function_address,
            _function_length(
                self.function_addresses,
                method.function_address,
                self.max_function_bytes,
            ),
        )
        if not code:
            return []
        hits: dict[tuple[str, str, int, int], MotionSetHit] = {}
        instructions = []
        for instruction in Decoder(64, code, ip=method.function_address):
            if instruction.code == Code.INVALID:
                break
            instructions.append(instruction)
        for index, instruction in enumerate(instructions):
            for operand in range(instruction.op_count):
                if instruction.op_kind(operand) not in _IMMEDIATE_KINDS:
                    continue
                for target, group in self._resolve(scope, instructions, index, operand):
                    hit = MotionSetHit(
                        action_class=method.type_name,
                        method_name=method.method_name,
                        function_address=method.function_address,
                        instruction_address=instruction.ip,
                        instruction_code=_code_name(instruction.code),
                        immediate_operand=operand,
                        target=target,
                        motion_group=group,
                    )
                    hits[
                        (
                            hit.action_class,
                            hit.method_name,
                            hit.instruction_address,
                            hit.target.motion_set_id,
                        )
                    ] = hit
        return sorted(
            hits.values(),
            key=lambda hit: (
                hit.function_address,
                hit.instruction_address,
                hit.target.motion_set_id,
            ),
        )

    def _resolve(
        self,
        scope: str,
        instructions: list[Instruction],
        index: int,
        operand: int,
    ) -> list[tuple[MotionTarget, tuple[tuple[str, str | int], ...]]]:
        immediate = instructions[index].immediate(operand)
        # A 64-bit MotionGroupSet is matched on the full immediate first; its
        # low half is a group hash and must not be read as a MotionSet.
        group = self.groups.find(scope, immediate) if self.groups else None
        if group is not None:
            if not _group_value_is_requested(instructions, index):
                return []
            return [
                (target, group.evidence(member))
                for member in group.members
                if (target := self.targets.find(scope, member.motion_set_id))
                is not None
            ]
        target = self.targets.find(scope, _to_int32(immediate))
        return [] if target is None else [(target, ())]


def _group_value_is_requested(
    instructions: list[Instruction],
    index: int,
    lookahead: int = 32,
) -> bool:
    """Accept a loaded group ID only when it is stored or passed to a call.

    Actions also compare the current motion group against other groups'
    IDs to choose transitions. Such a comparison does not play the motion.
    """
    loaded = instructions[index]
    if (
        loaded.mnemonic != Mnemonic.MOV
        or loaded.op0_kind != OpKind.REGISTER
        or RegisterExt.size(loaded.op0_register) != 8
    ):
        return False
    register = RegisterExt.full_register(loaded.op0_register)
    positions = {
        instruction.ip: position for position, instruction in enumerate(instructions)
    }
    position = index + 1
    for _ in range(lookahead):
        if position >= len(instructions):
            return False
        instruction = instructions[position]
        position += 1
        flow = instruction.flow_control
        if flow in {FlowControl.CALL, FlowControl.INDIRECT_CALL}:
            if register in _ARGUMENT_REGISTERS:
                return True
            if register in _VOLATILE_REGISTERS:
                return False
            continue
        if flow == FlowControl.UNCONDITIONAL_BRANCH:
            # Follow a jump to a shared store inside the same function.
            target = positions.get(instruction.near_branch_target)
            if target is None:
                return False
            position = target
            continue
        if flow in {FlowControl.RETURN, FlowControl.INDIRECT_BRANCH}:
            return False
        reads = writes = False
        for used in _INSTRUCTION_INFO.info(instruction).used_registers():
            if RegisterExt.full_register(used.register) != register:
                continue
            reads |= used.access in _READS
            writes |= used.access in _WRITES
        if reads:
            return instruction.mnemonic not in _COMPARISONS
        if writes:
            return False
    return False


class DirectCallScanner:
    def __init__(
        self,
        image: PeImage,
        function_addresses: list[int],
        targets: Iterable[Il2CppMethod],
        max_function_bytes: int,
    ) -> None:
        self.image = image
        self.function_addresses = function_addresses
        self.max_function_bytes = max_function_bytes
        grouped: dict[int, list[Il2CppMethod]] = defaultdict(list)
        for method in targets:
            grouped[method.function_address].append(method)
        self.targets = {
            address: sorted(
                methods,
                key=lambda method: (method.type_name, method.method_name),
            )[0]
            for address, methods in grouped.items()
        }

    def scan(self, method: Il2CppMethod) -> list[DirectCallHit]:
        code = self.image.read_function_bytes(
            method.function_address,
            _function_length(
                self.function_addresses,
                method.function_address,
                self.max_function_bytes,
            ),
        )
        if not code:
            return []
        hits: dict[tuple[str, str, int, int], DirectCallHit] = {}
        decoder = Decoder(64, code, ip=method.function_address)
        while decoder.can_decode:
            instruction = decoder.decode()
            if instruction.code == Code.INVALID:
                break
            if (
                instruction.mnemonic != Mnemonic.CALL
                or instruction.op0_kind not in _NEAR_BRANCH_KINDS
            ):
                continue
            callee = self.targets.get(instruction.near_branch_target)
            if callee is None:
                continue
            hit = DirectCallHit(
                caller_type=method.type_name,
                caller_method=method.method_name,
                caller_function_address=method.function_address,
                call_instruction_address=instruction.ip,
                callee=callee,
            )
            hits[
                (
                    hit.caller_type,
                    hit.caller_method,
                    hit.call_instruction_address,
                    hit.callee.function_address,
                )
            ] = hit
        return sorted(
            hits.values(),
            key=lambda hit: (
                hit.caller_function_address,
                hit.call_instruction_address,
            ),
        )


class AmmoItemMapCatalog:
    def __init__(
        self,
        by_shell_type: dict[str, AmmoNameRecord],
        evidence: list[AmmoItemMapEvidence],
    ) -> None:
        self._by_shell_type = {
            name.casefold(): record for name, record in by_shell_type.items()
        }
        self.evidence = evidence

    @property
    def count(self) -> int:
        return len(self._by_shell_type)

    def find(self, shell_type_name: str) -> AmmoNameRecord | None:
        return self._by_shell_type.get(shell_type_name.casefold())


@dataclass(frozen=True, slots=True)
class _InitializerPair:
    shell_type_value: int
    item_value: int
    call_address: int
    call_target: int


def scan_ammo_item_map(
    image: PeImage,
    initializer: Il2CppMethod,
    shells: ShellCatalog,
    max_function_bytes: int,
) -> AmmoItemMapCatalog:
    code = image.read_function_bytes(initializer.function_address, max_function_bytes)
    decoder = Decoder(64, code, ip=initializer.function_address)
    item_by_value = {name.item_value: name for name in shells.ammo_names.names}
    candidates_by_target: dict[int, list[_InitializerPair]] = defaultdict(list)
    assignments: dict[int, int] = {}

    while decoder.can_decode:
        instruction = decoder.decode()
        if instruction.code == Code.INVALID or instruction.mnemonic == Mnemonic.RET:
            break
        if (
            instruction.op_count >= 2
            and instruction.op_kind(0) == OpKind.REGISTER
            and instruction.op_kind(1) in _IMMEDIATE_KINDS
            and _code_name(instruction.code).startswith("Mov_r32_imm")
        ):
            assignments[instruction.op_register(0)] = _to_int32(
                instruction.immediate(1)
            )
        elif (
            instruction.op_count == 2
            and instruction.mnemonic == Mnemonic.XOR
            and instruction.op_kind(0) == OpKind.REGISTER
            and instruction.op_kind(1) == OpKind.REGISTER
            and instruction.op_register(0) == instruction.op_register(1)
        ):
            assignments[instruction.op_register(0)] = 0

        if (
            instruction.mnemonic != Mnemonic.CALL
            or instruction.op_kind(0) != OpKind.NEAR_BRANCH64
        ):
            continue
        values = set(assignments.values())
        shell_types = [value for value in values if value in shells.core_ammo_types]
        items = [value for value in values if value in item_by_value]
        if len(shell_types) == 1 and len(items) == 1:
            candidates_by_target[instruction.near_branch_target].append(
                _InitializerPair(
                    shell_type_value=shell_types[0],
                    item_value=items[0],
                    call_address=instruction.ip,
                    call_target=instruction.near_branch_target,
                )
            )
        assignments.clear()

    expected_types = set(shells.core_ammo_types)
    selections: list[list[_InitializerPair]] = []
    for pairs in candidates_by_target.values():
        by_shell: dict[int, list[_InitializerPair]] = defaultdict(list)
        for pair in pairs:
            by_shell[pair.shell_type_value].append(pair)
        selected = [
            values[0]
            for values in by_shell.values()
            if len({pair.item_value for pair in values}) == 1
        ]
        if {pair.shell_type_value for pair in selected} == expected_types:
            selections.append(selected)
    selected = max(selections, key=len, default=None)
    if selected is None:
        best_coverage = max(
            (
                len({pair.shell_type_value for pair in pairs})
                for pairs in candidates_by_target.values()
            ),
            default=0,
        )
        raise ValueError(
            "无法恢复 WeaponGunDef 的完整弹种/道具表 "
            f"({best_coverage}/{len(expected_types)} types found)"
        )

    mapping = {
        shells.core_ammo_types[pair.shell_type_value]: item_by_value[pair.item_value]
        for pair in selected
    }
    evidence = sorted(
        (
            AmmoItemMapEvidence(
                action_class=initializer.type_name,
                method_name=initializer.method_name,
                function_address=f"0x{initializer.function_address:x}",
                call_address=f"0x{pair.call_address:x}",
                call_target=f"0x{pair.call_target:x}",
                shell_type_value=pair.shell_type_value,
                shell_type_name=shells.core_ammo_types[pair.shell_type_value],
                item_value=pair.item_value,
                item_id=item_by_value[pair.item_value].item_id,
            )
            for pair in selected
        ),
        key=lambda item: item.shell_type_value,
    )
    return AmmoItemMapCatalog(mapping, evidence)


def _function_length(addresses: list[int], address: int, maximum: int) -> int:
    index = bisect_left(addresses, address)
    if (
        index < len(addresses)
        and addresses[index] == address
        and index + 1 < len(addresses)
    ):
        next_address = addresses[index + 1]
        if next_address > address:
            return min(maximum, next_address - address)
    return maximum


def _to_int32(value: int) -> int:
    unsigned = value & 0xFFFFFFFF
    return unsigned if unsigned < 0x80000000 else unsigned - 0x100000000


def _code_name(code: int) -> str:
    constant = _CODE_CONSTANT_NAMES.get(code, "INVALID")
    if constant == "INVALID":
        return "INVALID"
    if constant == "DECLAREBYTE":
        return "DeclareByte"
    if constant == "DECLAREWORD":
        return "DeclareWord"
    if constant == "DECLAREDWORD":
        return "DeclareDword"
    if constant == "DECLAREQWORD":
        return "DeclareQword"
    parts = constant.split("_")
    output: list[str] = []
    for index, part in enumerate(parts):
        if index == 0 and part in _ENCODING_PREFIXES:
            output.append(part)
        elif index == 0 or (index == 1 and parts[0] in _ENCODING_PREFIXES):
            output.append(part.capitalize())
        elif part in _UPPERCASE_CODE_TOKENS:
            output.append(part)
        elif part == "SREG":
            output.append("Sreg")
        else:
            output.append(part.lower())
    return "_".join(output)
