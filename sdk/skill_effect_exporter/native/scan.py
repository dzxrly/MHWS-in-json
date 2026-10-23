"""Find which native functions use which skill, and the shared runtime globals.

A skill identity reaches native code as an immediate argument of a method
whose parameter is ``app.HunterDef.Skill``. Callers often load a default ID and
replace it from ``HunterSkillDef.SkillToGroupSkill`` with ``cmov``; the default
is the skill the code was written for.
"""

from __future__ import annotations

import bisect
import re
import struct
from collections import defaultdict

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone import x86_const as X

from sdk.enemy_logic_exporter.shared.native.pe import address_catalog

from ..config import (
    ARGUMENT_REGISTERS,
    ARRAY_DATA_OFFSET,
    CALLER_STACK_ARGUMENT,
    CALL_OPCODES,
    EXECUTABLE_SECTION,
    METHOD_RECORD,
    HUNTER_SKILL,
    MAX_HELPER_ALIASES,
    PARAM_GETTER,
    REMAP_BUILDER,
    SKILL_DEF,
    SKILL_PARAM_TYPES,
    VALUE_HELPER,
)

GPR = {}
for _base, _subs in {
    "rax": ("eax", "ax", "al"),
    "rbx": ("ebx", "bx", "bl"),
    "rcx": ("ecx", "cx", "cl"),
    "rdx": ("edx", "dx", "dl"),
    "rsi": ("esi", "si", "sil"),
    "rdi": ("edi", "di", "dil"),
    "rbp": ("ebp", "bp", "bpl"),
    "rsp": ("esp", "sp", "spl"),
}.items():
    GPR[_base] = _base
    for _sub in _subs:
        GPR[_sub] = _base
for _i in range(8, 16):
    for _suffix in ("", "d", "w", "b"):
        GPR[f"r{_i}{_suffix}"] = f"r{_i}"
VOLATILE = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")


def method_stem(name):
    return re.sub(r"\d+$", "", name)


class NativeIndex:
    """Method names, skill helpers and globals of one EXE / il2cpp pair."""

    def __init__(self, pe, metadata):
        self.pe, self.metadata = pe, metadata
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64)
        self.cs.detail = True
        self.catalog = address_catalog(metadata)  # address -> [(type, method)]
        self.names = {
            a: f"{t}.{m}" for a, items in self.catalog.items() for t, m in items[:1]
        }

    # ------------------------------------------------------------ helpers
    def method(self, type_name, stem):
        record = self.metadata.get(type_name) or {}
        found = [
            (name, info)
            for name, info in record.get("methods", {}).items()
            if method_stem(name) == stem and info.get("function")
        ]
        if len(found) != 1:
            raise ValueError(
                f"{type_name}.{stem} 在 il2cpp 中应唯一，实际 {len(found)} 个"
            )
        name, info = found[0]
        return name, int(info["function"], 16), info

    def disasm(self, start):
        end = self.pe.end(start)
        return list(self.cs.disasm(self.pe.read(start, end - start), start))

    def skill_helpers(self):
        """address -> (method, skill argument slots, int argument slots)."""
        mapped = self.metadata._mapped
        heads = [
            (m.start(), m.group(1).decode())
            for m in re.finditer(METHOD_RECORD, mapped, re.M)
        ]
        positions = [h[0] for h in heads]
        names = list(self.metadata._offsets)
        starts = list(self.metadata._offsets.values())
        owners = set()
        pattern = "|".join(re.escape(t) for t in SKILL_PARAM_TYPES)
        for match in re.finditer(rb'"type": "(?:' + pattern.encode() + rb')"', mapped):
            k = bisect.bisect_right(positions, match.start()) - 1
            if k >= 0:
                owners.add(
                    (names[bisect.bisect_right(starts, heads[k][0]) - 1], heads[k][1])
                )
        helpers = {}
        for type_name, method in sorted(owners):
            info = (self.metadata.get(type_name) or {}).get("methods", {}).get(method)
            if not info or not info.get("function"):
                continue
            address = int(info["function"], 16)
            if len(self.catalog.get(address, ())) > MAX_HELPER_ALIASES:
                continue  # shared stub (e.g. an empty virtual), not a skill consumer
            params = [p.get("type") for p in info.get("params", [])]
            if not any(p in SKILL_PARAM_TYPES for p in params):
                continue
            registers = list(
                ARGUMENT_REGISTERS[0 if "Static" in info.get("flags", "") else 1 :]
            )
            slots = [
                (
                    registers[i]
                    if i < len(registers)
                    else f"sp+{CALLER_STACK_ARGUMENT + 8 * (i - len(registers)):#x}"
                )
                for i in range(len(params))
            ]
            helpers[address] = dict(
                type=type_name,
                method=method,
                params=params,
                slots=slots,
                fixed=[p == SKILL_PARAM_TYPES[1] for p in params],
            )
        return helpers

    # ------------------------------------------------------------ call sites
    def callers(self, targets):
        """function start -> [call site address] for direct calls/jumps to targets."""
        result = defaultdict(list)
        for (vsize, va, raw_size, raw), flags in zip(
            self.pe.sections, self.pe.section_flags
        ):
            if not flags & EXECUTABLE_SECTION:
                continue
            base = self.pe.base + va
            data = self.pe.data[raw : raw + raw_size]
            for match in re.finditer(CALL_OPCODES, data):
                offset = match.start()
                if offset + 5 > len(data):
                    break
                target = (
                    base + offset + 5 + struct.unpack_from("<i", data, offset + 1)[0]
                )
                if target in targets:
                    owner = self.owner(base + offset)
                    if owner is not None:
                        result[owner].append(base + offset)
        return result

    def owner(self, address):
        k = bisect.bisect_right(self.pe.starts, address) - 1
        if k >= 0 and self.pe.functions[k][0] <= address < self.pe.functions[k][1]:
            return self.pe.functions[k][0]
        return None

    def references(self, helpers, skill_names, fixed_names):
        """Immediate skill arguments at every helper call site."""
        rows = []
        for start, _ in sorted(self.callers(set(helpers)).items()):
            imm = {}
            for insn in self.disasm(start):
                ops = insn.operands
                if (
                    insn.mnemonic in ("call", "jmp")
                    and ops
                    and ops[0].type == X.X86_OP_IMM
                ):
                    target = ops[0].imm
                    helper = helpers.get(target)
                    if helper is not None:
                        args = {slot: imm.get(slot) for slot in helper["slots"]}
                        for index, (ptype, slot) in enumerate(
                            zip(helper["params"], helper["slots"])
                        ):
                            if ptype not in SKILL_PARAM_TYPES:
                                continue
                            value = imm.get(slot)
                            names = (
                                fixed_names if helper["fixed"][index] else skill_names
                            )
                            ints = [
                                args[s]
                                for p, s in zip(helper["params"], helper["slots"])
                                if p == "System.Int32"
                            ]
                            rows.append(
                                dict(
                                    function=start,
                                    site=insn.address,
                                    helper=target,
                                    skill=(
                                        names.get(value) if value is not None else None
                                    ),
                                    raw=value,
                                    intArgs=ints,
                                )
                            )
                    if insn.mnemonic == "call":
                        for reg in VOLATILE:
                            imm.pop(reg, None)
                    continue
                if (
                    insn.mnemonic.startswith("cmov")
                    and ops[0].type == X.X86_OP_REG
                    and GPR.get(insn.reg_name(ops[0].reg)) in imm
                ):
                    continue  # the default ID stays; the override comes from SkillToGroupSkill
                if insn.mnemonic == "mov" and len(ops) == 2:
                    dst, src = ops
                    if (
                        dst.type == X.X86_OP_MEM
                        and dst.mem.base
                        and insn.reg_name(dst.mem.base) == "rsp"
                        and not dst.mem.index
                    ):
                        slot = f"sp+{dst.mem.disp:#x}"
                        if src.type == X.X86_OP_IMM:
                            imm[slot] = src.imm & 0xFFFFFFFF
                        elif (
                            src.type == X.X86_OP_REG
                            and GPR.get(insn.reg_name(src.reg)) in imm
                        ):
                            imm[slot] = imm[GPR[insn.reg_name(src.reg)]]
                        else:
                            imm.pop(slot, None)
                        continue
                    if dst.type == X.X86_OP_REG and src.type == X.X86_OP_IMM:
                        imm[GPR[insn.reg_name(dst.reg)]] = src.imm & 0xFFFFFFFF
                        continue
                    if dst.type == X.X86_OP_REG and src.type == X.X86_OP_REG:
                        d, s = GPR.get(insn.reg_name(dst.reg)), GPR.get(
                            insn.reg_name(src.reg)
                        )
                        if s in imm:
                            imm[d] = imm[s]
                        else:
                            imm.pop(d, None)
                        continue
                if (
                    insn.mnemonic == "xor"
                    and len(ops) == 2
                    and ops[0].type == X.X86_OP_REG
                    and ops[1].type == X.X86_OP_REG
                    and ops[0].reg == ops[1].reg
                ):
                    imm[GPR[insn.reg_name(ops[0].reg)]] = 0
                    continue
                try:
                    _, written = insn.regs_access()
                except Exception:
                    written = ()
                for reg in written:
                    imm.pop(GPR.get(insn.reg_name(reg)), None)
        return rows

    # ------------------------------------------------------------ globals
    def remap_pairs(self):
        """(skill, group skill) runtime values set by HunterSkillDef.createSkillToGroupSkill."""
        _, start, _ = self.method(SKILL_DEF, REMAP_BUILDER)
        calls, imm, pairs = defaultdict(list), {}, []
        for insn in self.disasm(start):
            ops = insn.operands
            if (
                insn.mnemonic == "mov"
                and len(ops) == 2
                and ops[0].type == X.X86_OP_REG
                and ops[1].type == X.X86_OP_IMM
            ):
                imm[GPR[insn.reg_name(ops[0].reg)]] = ops[1].imm
            elif insn.mnemonic == "call" and ops[0].type == X.X86_OP_IMM:
                if "r8" in imm and "r9" in imm:
                    calls[ops[0].imm].append((imm["r8"], imm["r9"]))
                for reg in VOLATILE:
                    imm.pop(reg, None)
        setter, pairs = max(calls.items(), key=lambda item: len(item[1]))
        if len(pairs) < 10:
            raise ValueError("createSkillToGroupSkill 的成对写入模式已变化")
        return setter, pairs

    def value_helper_globals(self):
        """Static slot of SkillToGroupSkill and the stack-cookie check, from getSkillValue."""
        _, start, _ = self.method(HUNTER_SKILL, VALUE_HELPER)
        code = self.disasm(start)
        table = cookie = None
        meaningful = [insn for insn in code if insn.mnemonic != "vzeroupper"]
        for previous, insn in zip(meaningful, meaningful[1:]):
            ops = insn.operands
            if (
                table is None
                and insn.mnemonic == "mov"
                and ops[1].type == X.X86_OP_MEM
                and insn.reg_name(ops[1].mem.base) == "rip"
            ):
                following = meaningful[meaningful.index(insn) + 2]
                if (
                    following.mnemonic == "mov"
                    and following.operands[1].type == X.X86_OP_MEM
                    and following.operands[1].mem.scale == 4
                    and following.operands[1].mem.disp == ARRAY_DATA_OFFSET
                ):
                    table = insn.address + insn.size + ops[1].mem.disp
            if (
                insn.mnemonic == "call"
                and previous.mnemonic == "xor"
                and previous.op_str == "rcx, rsp"
            ):
                cookie = insn.operands[0].imm
        if table is None or cookie is None:
            raise ValueError(
                "getSkillValue 的 SkillToGroupSkill 读取或栈保护调用模式已变化"
            )
        return table, cookie

    def param_chain(self):
        """Global slot and the two offsets leading to PlayerGlobalParam (get__SkillParam)."""
        _, start, _ = self.method(HUNTER_SKILL, PARAM_GETTER)
        code = self.disasm(start)
        if len(code) < 5 or code[4].mnemonic != "ret":
            raise ValueError("get__SkillParam 的单例链模式已变化")
        root = code[0].address + code[0].size + code[0].operands[1].mem.disp
        offsets = [insn.operands[1].mem.disp for insn in code[1:4]]
        return root, offsets
