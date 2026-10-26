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
from collections import defaultdict, deque

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
    TYPE_ADDRESS,
    TYPE_RECORD,
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


def indexed_fields(layout, offset, scale, layouts):
    """Fields read by [base + index*scale + offset]: the field covering offset
    and, with an index, the following fields spaced by scale whose names
    differ only in digits (per-weapon fields such as _Ballistic_Wp12AttackAdd
    and _Ballistic_Wp13AttackAdd)."""
    fields = []
    for start, (name, ftype) in layout.items():
        size = layouts.size(ftype) if layouts.is_value_type(ftype) else 8
        if start <= offset < start + max(size, 1):
            fields.append(name)
            if not scale or start != offset:
                return fields
            stem = re.sub(r"\d+", "", name)
            position = start + scale
            while (
                position in layout
                and layout[position][1] == ftype
                and re.sub(r"\d+", "", layout[position][0]) == stem
            ):
                fields.append(layout[position][0])
                position += scale
            return fields
    return fields


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

    def type_addresses(self):
        """Runtime type descriptor address -> type name, from the il2cpp dump.
        The dumped EXE's globals hold these pointers where code checks an
        object's exact type (cmp [[obj]], [rip+X])."""
        if not hasattr(self, "_types"):
            mapped = self.metadata._mapped
            heads = [
                (m.start(), m.group(1).decode())
                for m in re.finditer(TYPE_RECORD, mapped, re.M)
            ]
            positions = [h[0] for h in heads]
            self._types = {}
            for m in re.finditer(TYPE_ADDRESS, mapped, re.M):
                k = bisect.bisect_right(positions, m.start()) - 1
                if k >= 0:
                    self._types.setdefault(int(m.group(1), 16), heads[k][1])
        return self._types

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
        for target, owners in self.calls_to(targets).items():
            for owner, sites in owners.items():
                result[owner] += sites
        return {owner: sorted(sites) for owner, sites in result.items()}

    def calls_to(self, targets):
        """target -> {function start -> [call site]} for direct calls/jumps to targets."""
        result = defaultdict(lambda: defaultdict(list))
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
                        result[target][owner].append(base + offset)
        return result

    def reaching(self, start, sites):
        """Instructions of the function at start from which some site is
        reachable -> fewest instructions from there to a site.

        Successors come from the static control flow: conditional and direct
        jumps, fall-through after calls. An indirect jump, or a jump out of the
        function body (a tail call or a split-off block), may lead anywhere, so
        everything before it counts as reaching.
        """
        insns = self.disasm(start)
        end = self.pe.end(start)
        addresses = [insn.address for insn in insns]
        predecessors = defaultdict(set)
        anywhere = []
        for insn in insns:
            nxt = insn.address + insn.size
            m, ops = insn.mnemonic, insn.operands
            if m in ("ret", "retn", "int3", "ud2"):
                continue
            if m == "jmp" or m.startswith("j"):
                direct = ops and ops[0].type == X.X86_OP_IMM
                target = ops[0].imm if direct else None
                if target is None or not start <= target < end:
                    anywhere.append(insn.address)
                else:
                    predecessors[target].add(insn.address)
                if m != "jmp":
                    predecessors[nxt].add(insn.address)
                continue
            predecessors[nxt].add(insn.address)
        if anywhere:  # their successors are unknown: any instruction may follow
            for address in addresses:
                predecessors[address].update(anywhere)
        reach = {s: 0 for s in sites if start <= s < end}
        pending = deque(reach)
        while pending:  # breadth first: the first visit is the shortest
            address = pending.popleft()
            for previous in predecessors[address]:
                if previous not in reach:
                    reach[previous] = reach[address] + 1
                    pending.append(previous)
        return reach

    def exits(self, start):
        """Returns and jumps out of the function at start (tail calls)."""
        end = self.pe.end(start)
        found = []
        for insn in self.disasm(start):
            if insn.mnemonic in ("ret", "retn"):
                found.append(insn.address)
            elif insn.mnemonic == "jmp" and insn.operands:
                op = insn.operands[0]
                if op.type != X.X86_OP_IMM or not start <= op.imm < end:
                    found.append(insn.address)
        return found

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

    def param_reads(self, root, offsets, getter, layouts, global_type):
        """Static reads of parameter-file fields through PlayerGlobalParam.

        The singleton chain [rip+root] -> +offsets[0] -> +offsets[1] gives
        PlayerGlobalParam; one more load of one of its reference fields gives a
        parameter object (PlayerSkillParam, PlayerMealSkillParam, ...), whose
        field reads are recorded. get__SkillParam() returns the PlayerSkillParam
        object directly. Registers are followed linearly from each chain load
        to the next unconditional jump or return.

        Returns {(param type, field name): {function start: [site, ...]}}.
        """
        global_fields = layouts.fields(global_type)
        getter_type = global_fields.get(offsets[-1], (None, None))[1]
        starts = defaultdict(set)  # function -> addresses to start following at
        rip_load = re.compile(rb"[\x48\x4c]\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]")
        for (vsize, va, raw_size, raw), flags in zip(
            self.pe.sections, self.pe.section_flags
        ):
            if not flags & EXECUTABLE_SECTION:
                continue
            base = self.pe.base + va
            data = self.pe.data[raw : raw + raw_size]
            for match in rip_load.finditer(data):
                offset = match.start()
                if offset + 7 > len(data):
                    break
                address = base + offset
                if address + 7 + struct.unpack_from("<i", data, offset + 3)[0] == root:
                    owner = self.owner(address)
                    if owner is not None:
                        starts[owner].add(address)
        for owner, sites in self.callers({getter}).items():
            starts[owner].update(sites)
        reads = defaultdict(lambda: defaultdict(list))
        for function, entries in starts.items():
            code = self.disasm(function)
            positions = {insn.address: i for i, insn in enumerate(code)}
            seen = set()
            for entry in sorted(entries):
                if entry not in positions:
                    continue  # not an instruction boundary of the linear sweep
                # register -> chain stage (int) or parameter object type (str)
                stage = {}
                for insn in code[positions[entry] :]:
                    ops = insn.operands
                    m = insn.mnemonic
                    if insn.address == entry and m == "call":
                        stage = {"rax": getter_type}
                        continue
                    loaded = None
                    for op in ops:
                        if op.type != X.X86_OP_MEM or not op.mem.base:
                            continue
                        base_reg = GPR.get(insn.reg_name(op.mem.base))
                        if insn.reg_name(op.mem.base) == "rip":
                            target = insn.address + insn.size + op.mem.disp
                            if target == root and m == "mov":
                                loaded = 0
                            continue
                        held = stage.get(base_reg)
                        if isinstance(held, int) and not op.mem.index and m == "mov":
                            if held < len(offsets) - 1 and op.mem.disp == offsets[held]:
                                loaded = held + 1
                            elif held == len(offsets) - 1:
                                name, ftype = global_fields.get(
                                    op.mem.disp, (None, None)
                                )
                                if ftype and not layouts.is_value_type(ftype):
                                    loaded = ftype
                        elif isinstance(held, str) and (insn.address, held) not in seen:
                            seen.add((insn.address, held))
                            for field in indexed_fields(
                                layouts.fields(held),
                                op.mem.disp,
                                op.mem.scale if op.mem.index else 0,
                                layouts,
                            ):
                                reads[(held, field)][function].append(insn.address)
                    if m in ("ret", "jmp", "int3"):
                        break
                    if m == "call":
                        for reg in VOLATILE:
                            stage.pop(reg, None)
                        continue
                    try:
                        _, written = insn.regs_access()
                    except Exception:
                        written = ()
                    for reg in written:
                        stage.pop(GPR.get(insn.reg_name(reg)), None)
                    if (
                        loaded is not None
                        and ops
                        and ops[0].type == X.X86_OP_REG
                        and GPR.get(insn.reg_name(ops[0].reg))
                    ):
                        stage[GPR[insn.reg_name(ops[0].reg)]] = loaded
                    elif (
                        m == "mov"
                        and len(ops) == 2
                        and ops[0].type == X.X86_OP_REG
                        and ops[1].type == X.X86_OP_REG
                        and GPR.get(insn.reg_name(ops[1].reg)) in stage
                    ):
                        stage[GPR[insn.reg_name(ops[0].reg)]] = stage[
                            GPR[insn.reg_name(ops[1].reg)]
                        ]
                    if not stage:
                        break
        return {key: dict(value) for key, value in reads.items()}

    def param_chain(self):
        """Global slot and the two offsets leading to PlayerGlobalParam (get__SkillParam)."""
        _, start, _ = self.method(HUNTER_SKILL, PARAM_GETTER)
        code = self.disasm(start)
        if len(code) < 5 or code[4].mnemonic != "ret":
            raise ValueError("get__SkillParam 的单例链模式已变化")
        root = code[0].address + code[0].size + code[0].operands[1].mem.disp
        offsets = [insn.operands[1].mem.disp for insn in code[1:4]]
        return root, offsets
