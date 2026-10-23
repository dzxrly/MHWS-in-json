"""Concrete x64 emulation of skill accessors with named unknowns.

Inputs that the exports describe (skill level, SkillData slots, parameter
files) are concrete. Everything else is ``Unk``: a branch on an unknown forks
the path and records the condition, so a result reads "value under these
runtime conditions". Direct calls are inlined up to a depth limit; a callee
that cannot be emulated is replaced by an opaque call whose return value is an
unknown named after it. Heap writes end a path: accessors only read.
"""

from __future__ import annotations

import copy
import math
from itertools import product
import struct

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone import x86_const as X

from ..config import (
    ENTRY_STACK_PHASE,
    MAX_CALL_DEPTH,
    MAX_PATHS,
    MAX_STEPS,
    MAX_TOTAL_STEPS,
    REFERENCE_TAG_BIT,
)
from .values import Ptr, Unk, Unsupported, V, f32, f32_bits, unk

MASK = {1: 0xFF, 2: 0xFFFF, 4: 0xFFFFFFFF, 8: 0xFFFFFFFFFFFFFFFF}
GPR64 = (
    "rax",
    "rbx",
    "rcx",
    "rdx",
    "rsi",
    "rdi",
    "rbp",
    "rsp",
    "r8",
    "r9",
    "r10",
    "r11",
    "r12",
    "r13",
    "r14",
    "r15",
)
VOLATILE = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")
SUB = {}
for _base, _names in {
    "rax": ("eax", "ax", "al"),
    "rbx": ("ebx", "bx", "bl"),
    "rcx": ("ecx", "cx", "cl"),
    "rdx": ("edx", "dx", "dl"),
    "rsi": ("esi", "si", "sil"),
    "rdi": ("edi", "di", "dil"),
    "rbp": ("ebp", "bp", "bpl"),
    "rsp": ("esp", "sp", "spl"),
}.items():
    SUB[_base] = (_base, 8, 0)
    for _name, _size in zip(_names, (4, 2, 1)):
        SUB[_name] = (_base, _size, 0)
for _i in range(8, 16):
    SUB[f"r{_i}"] = (f"r{_i}", 8, 0)
    for _suffix, _size in (("d", 4), ("w", 2), ("b", 1)):
        SUB[f"r{_i}{_suffix}"] = (f"r{_i}", _size, 0)
for _name, _base in (("ah", "rax"), ("bh", "rbx"), ("ch", "rcx"), ("dh", "rdx")):
    SUB[_name] = (_base, 1, 8)

CONDITIONS = {
    "e": "==",
    "z": "==",
    "ne": "!=",
    "nz": "!=",
    "g": ">",
    "ge": ">=",
    "l": "<",
    "le": "<=",
    "a": ">u",
    "ae": ">=u",
    "b": "<u",
    "be": "<=u",
    "nb": ">=u",
    "nae": "<u",
    "nbe": ">u",
    "na": "<=u",
    "s": "<0",
    "ns": ">=0",
    "p": "unordered",
    "np": "ordered",
    "o": "overflow",
    "no": "no overflow",
    "c": "<u",
    "nc": ">=u",
}
# Conditions that read only CF or OF, the flags IMUL defines.
IMUL_DEFINED = frozenset({"o", "no", "b", "c", "nae", "ae", "nb", "nc"})

NEGATE = {
    "==": "!=",
    "!=": "==",
    ">": "<=",
    "<=": ">",
    "<": ">=",
    ">=": "<",
    ">u": "<=u",
    "<=u": ">u",
    "<u": ">=u",
    ">=u": "<u",
    "<0": ">=0",
    ">=0": "<0",
    "unordered": "ordered",
    "ordered": "unordered",
    "overflow": "no overflow",
    "no overflow": "overflow",
}


class Budget(Exception):
    """The whole evaluation exceeded its instruction budget."""


class PathEnd(Exception):
    def __init__(self, status, detail=""):
        super().__init__(detail)
        self.status, self.detail = status, detail


def signed(value, size):
    value &= (1 << (8 * size)) - 1
    return value - (1 << (8 * size)) if value >> (8 * size - 1) else value


def name_of(v):
    if isinstance(v.val, Unk):
        return v.val.name
    if isinstance(v.val, Half):
        return f"{name_of(v.val.whole)} 的{'低' if v.val.index == 0 else '高'}32位"
    if isinstance(v.val, Partial):
        return f"{name_of(v.val.old)} 低位={v.val.low}"
    if isinstance(v.val, Ptr):
        return f"&{v.val.obj.path}+0x{v.val.off:x}"
    return str(v.val)


def shorten(text, limit=160):
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _parity(value):
    """PF: set when the low byte of a result has an even number of one bits."""
    return int(bin(value & 0xFF).count("1") % 2 == 0)


def _feasible(kind):
    """Flag tuples (zf, sf, cf, of, pf) an instruction of this kind can produce."""
    every = list(product((0, 1), repeat=5))
    if kind == "cmp":  # a - b: equal means zero, so no sign, borrow or overflow
        return [t for t in every if not t[0] or t[1:] == (0, 0, 0, 1)]
    # A zero result has no sign and even parity.
    if kind == "test":  # logical result: CF = OF = 0
        return [
            t for t in every if t[2] == t[3] == 0 and not (t[0] and (t[1] or not t[4]))
        ]
    if kind == "result":  # arithmetic result: CF and OF free
        return [t for t in every if not (t[0] and (t[1] or not t[4]))]
    if kind == "imul":  # CF = OF = product overflowed; ZF, SF, PF undefined
        return [t for t in every if t[2] == t[3]]
    if kind == "float":  # ucomiss: unordered, less, equal, greater
        return [(1, 0, 1, 0, 1), (0, 0, 1, 0, 0), (1, 0, 0, 0, 0), (0, 0, 0, 0, 0)]
    return every  # bit tests, flags left by an opaque call


def _condition(flags, cc):
    z, s, c, o, p = flags
    table = {
        "e": z,
        "z": z,
        "ne": not z,
        "nz": not z,
        "g": not z and s == o,
        "ge": s == o,
        "l": s != o,
        "le": z or s != o,
        "a": not c and not z,
        "nbe": not c and not z,
        "ae": not c,
        "nb": not c,
        "nc": not c,
        "b": c,
        "nae": c,
        "c": c,
        "be": c or z,
        "na": c or z,
        "s": s,
        "ns": not s,
        "p": p,
        "np": not p,
        "o": o,
        "no": not o,
    }
    if cc not in table:
        raise Unsupported(f"条件码 {cc}")
    return bool(table[cc])


class Flags:
    """Concrete flag bits, or a comparison on unknown operands.

    An unknown comparison keeps the flag combinations still feasible on this
    path; each branch narrows them, so a later condition on the same flags
    only sees outcomes consistent with the earlier ones.
    """

    def __init__(
        self,
        zf=0,
        sf=0,
        cf=0,
        of=0,
        pf=0,
        label=None,
        kind=None,
        prov=frozenset(),
        candidates=None,
    ):
        self.zf, self.sf, self.cf, self.of, self.pf = zf, sf, cf, of, pf
        # kind: cmp / test / result / float / bit / any (see _feasible)
        self.label, self.kind, self.prov = label, kind, prov
        self.candidates = None
        if label is not None:
            self.candidates = (
                list(candidates) if candidates is not None else _feasible(kind)
            )

    def split(self, cc):
        """Feasible combinations where cc holds, and where it does not."""
        true = [t for t in self.candidates if _condition(t, cc)]
        false = [t for t in self.candidates if not _condition(t, cc)]
        return true, false

    def narrowed(self, candidates):
        if len(candidates) == 1:
            return Flags(*candidates[0], prov=self.prov)
        return Flags(
            label=self.label, kind=self.kind, prov=self.prov, candidates=candidates
        )

    def holds(self, cc):
        z, s, c, o, p = self.zf, self.sf, self.cf, self.of, self.pf
        table = {
            "e": z,
            "z": z,
            "ne": not z,
            "nz": not z,
            "g": not z and s == o,
            "ge": s == o,
            "l": s != o,
            "le": z or s != o,
            "a": not c and not z,
            "nbe": not c and not z,
            "ae": not c,
            "nb": not c,
            "nc": not c,
            "b": c,
            "nae": c,
            "c": c,
            "be": c or z,
            "na": c or z,
            "s": s,
            "ns": not s,
            "p": p,
            "np": not p,
            "o": o,
            "no": not o,
        }
        if cc not in table:
            raise Unsupported(f"条件码 {cc}")
        return bool(table[cc])


class Stack:
    type_name = "stack"
    path = "stack"

    def __init__(self):
        self.cells = {}  # off -> (size, V)

    def write(self, off, size, value):
        for start in [
            k for k, (s, _) in self.cells.items() if k < off + size and off < k + s
        ]:
            del self.cells[start]
        self.cells[off] = (size, value)

    def read(self, off, size, heap):
        if off in self.cells and self.cells[off][0] == size:
            return self.cells[off][1]
        for start, (s, value) in self.cells.items():
            if start <= off and off + size <= start + s and isinstance(value.val, int):
                shift = 8 * (off - start)
                return V((value.val >> shift) & MASK[size], value.prov)
        if size == 8 and off in self.cells and off + 4 in self.cells:
            lo, hi = self.cells[off][1], self.cells[off + 4][1]
            if self.cells[off][0] == 4 and self.cells[off + 4][0] == 4:
                if isinstance(lo.val, int) and isinstance(hi.val, int):
                    return V(lo.val | hi.val << 32, lo.prov | hi.prov)
                if (
                    isinstance(lo.val, Half)
                    and isinstance(hi.val, Half)
                    and lo.val.whole is hi.val.whole
                ):
                    return lo.val.whole
        if size == 4 and off in self.cells and self.cells[off][0] == 4:
            return self.cells[off][1]
        return unk(f"未写入的栈 {off:#x}")

    def clone(self):
        other = Stack()
        other.cells = dict(self.cells)
        return other


class _StackRef:
    """Stack pointers name the current path's stack, so cloned paths stay independent."""

    type_name = "stack"
    path = "栈"


STACK = _StackRef()


class Partial:
    """A register whose low ``size`` bytes were overwritten with a known integer."""

    def __init__(self, old, low, size):
        self.old, self.low, self.size = old, low, size


class Half:
    """One 32-bit lane of a split 64-bit pointer or unknown."""

    def __init__(self, whole, index):
        self.whole, self.index = whole, index


class State:
    def __init__(self):
        self.regs = {}
        self.vregs = {}
        self.flags = Flags()
        self.stack = Stack()
        self.rip = 0
        self.depth = 0
        self.conditions = []
        self.snapshot = None  # state before the outermost pending inline call
        self.opaque = []
        self.steps = 0
        # (object id, offset) -> (object, offset, size, V); globals keyed by
        # ("global", address). Entries of one object never overlap.
        self.writes = {}

    def clone(self):
        other = copy.copy(self)
        other.regs = dict(self.regs)
        other.vregs = {k: list(v) for k, v in self.vregs.items()}
        other.stack = self.stack.clone()
        other.conditions = list(self.conditions)
        other.opaque = list(self.opaque)
        other.writes = dict(self.writes)
        return other


class Emulator:
    def __init__(
        self,
        pe,
        heap,
        names,
        *,
        intercept=None,
        skip_calls=(),
        inline_ok=None,
        globals_=None,
    ):
        self.pe, self.heap, self.names = pe, heap, names
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64)
        self.cs.detail = True
        self.cache = {}
        self.intercept = (
            intercept or {}
        )  # address -> fn(emulator, state) handling the call
        self.skip_calls = set(skip_calls)  # stack cookie checks and similar no-ops
        self.inline_ok = inline_ok or (lambda address: True)
        self.globals = globals_ or {}  # rip-relative address -> V (pointer slots)

    # ------------------------------------------------------------ decoding
    def insn(self, address):
        if address not in self.cache:
            code = self.pe.read(address, 16)
            decoded = next(self.cs.disasm(code, address), None)
            if decoded is None:
                raise Unsupported(f"无法解码 {address:#x}")
            self.cache[address] = decoded
        return self.cache[address]

    # ------------------------------------------------------------ registers
    def get(self, st, reg):
        base, size, shift = SUB[reg]
        if base == "rip":
            raise Unsupported("rip 操作数")
        value = st.regs.get(base, unk(f"寄存器 {base}"))
        if size == 8:
            return value
        if isinstance(value.val, Partial) and size <= value.val.size and not shift:
            return V(value.val.low & MASK[size], value.prov)
        if isinstance(value.val, int):
            return V((value.val >> shift) & MASK[size], value.prov)
        if isinstance(value.val, Ptr) and size == 4:
            return V(Half(value, 0), value.prov)
        return V(
            Unk(
                value.val.name
                if isinstance(value.val, Unk)
                else f"{name_of(value)} 低位"
            ),
            value.prov,
        )

    def put(self, st, reg, value, size=None):
        base, rsize, shift = SUB[reg]
        size = size or rsize
        if size == 8:
            st.regs[base] = value
            return
        if size == 4:
            if isinstance(value.val, int):
                st.regs[base] = V(value.val & MASK[4], value.prov)
            else:
                st.regs[base] = (
                    value
                    if isinstance(value.val, Unk)
                    else unk(name_of(value), value.prov)
                )
            return
        old = st.regs.get(base, V(0))
        if isinstance(old.val, int) and isinstance(value.val, int):
            mask = MASK[size] << shift
            st.regs[base] = V(
                (old.val & ~mask) | ((value.val & MASK[size]) << shift),
                old.prov | value.prov,
            )
        elif isinstance(value.val, int) and not shift:
            # Low bits replaced over a pointer/unknown: later reads of those bits stay exact.
            st.regs[base] = V(Partial(old, value.val & MASK[size], size), value.prov)
        else:
            # The low bits are what later code reads; name the result after them.
            st.regs[base] = unk(
                (
                    name_of(value)
                    if isinstance(value.val, Unk)
                    else f"{name_of(old)} 部分写入"
                ),
                old.prov | value.prov,
            )

    def vget(self, st, reg):
        name = self.cs.reg_name(reg)
        index = int(name[3:])
        return self.vget_index(st, index)

    def vput(self, st, reg, lanes, width):
        name = self.cs.reg_name(reg)
        index = int(name[3:])
        result = list(lanes[: width // 4]) + [V(0)] * (8 - width // 4)
        st.vregs[index] = result

    # ------------------------------------------------------------ memory
    def address(self, st, insn, mem):
        if mem.base and self.cs.reg_name(mem.base) == "rip":
            return ("rip", insn.address + insn.size + mem.disp)
        base = self.get(st, self.cs.reg_name(mem.base)) if mem.base else V(0)
        index = self.get(st, self.cs.reg_name(mem.index)) if mem.index else V(0)
        if isinstance(index.val, Half):
            index = index.val.whole
        if not isinstance(index.val, int):
            return (
                "unknown",
                f"{name_of(base)}[{name_of(index)}]",
                base.prov | index.prov,
            )
        offset = signed(index.val, 8) * (mem.scale or 1) + mem.disp
        if isinstance(base.val, Half):
            base = base.val.whole
        if isinstance(base.val, Ptr):
            return ("ptr", base.val.add(offset), base.prov | index.prov)
        if isinstance(base.val, Unk):
            return ("unknown", f"{base.val.name}+{offset:#x}", base.prov)
        if isinstance(base.val, int) and base.val:
            target = (base.val + offset) & MASK[8]
            if self.pe.read(target, 1):
                return ("rip", target)  # an image address computed from lea [rip+x]
        raise PathEnd("null", f"读取空指针 {insn.address:#x}")

    def load(self, st, insn, mem, size):
        kind, *rest = self.address(st, insn, mem)
        if kind == "rip":
            target = rest[0]
            return _overlay_read(
                st.writes,
                "global",
                target,
                size,
                lambda: self.global_value(target, size),
            )
        if kind == "unknown":
            return unk(f"[{rest[0]}]", rest[1])
        ptr = rest[0]
        if ptr.obj is STACK:
            return st.stack.read(ptr.off, size, self.heap)

        def original():
            value = ptr.obj.read(ptr.off, size, self.heap)
            return V(value.val, value.prov | rest[1])

        return _overlay_read(st.writes, id(ptr.obj), ptr.off, size, original)

    def global_value(self, target, size):
        if target in self.globals:
            return self.globals[target]
        if self.pe.read_only(target, size):
            raw = self.pe.read(target, size)
            return V(
                int.from_bytes(raw, "little"),
                frozenset({f"EXE 常量 {target:#x}:{raw.hex()}"}),
            )
        return unk(f"全局量 {target:#x}")

    def store(self, st, insn, mem, size, value):
        kind, *rest = self.address(st, insn, mem)
        if kind == "ptr" and rest[0].obj is STACK:
            st.stack.write(rest[0].off, size, value)
            return
        # Writes to runtime state are effects: kept per path and reported with the result.
        if kind == "ptr":
            ptr = rest[0]
            _overlay_write(st.writes, id(ptr.obj), ptr.obj, ptr.off, size, value)
        elif kind == "rip":
            _overlay_write(st.writes, "global", None, rest[0], size, value)
        else:
            st.writes[("unknown", rest[0])] = (None, rest[0], size, value)

    def vload(self, st, insn, mem, width):
        """Load width bytes as 32-bit lanes; 64-bit values split into halves."""
        lanes, pos = [], 0
        while pos < width:
            chunk = min(self.natural_width(st, insn, _Mem(mem, pos)), width - pos)
            if chunk not in (4, 8):
                raise Unsupported(f"向量读取跨越 {chunk} 字节字段")
            value = self.load(st, insn, _Mem(mem, pos), chunk)
            if chunk == 8:
                if isinstance(value.val, int):
                    lanes += [
                        V(value.val & MASK[4], value.prov),
                        V(value.val >> 32, value.prov),
                    ]
                else:
                    lanes += [
                        V(Half(value, 0), value.prov),
                        V(Half(value, 1), value.prov),
                    ]
            else:
                lanes.append(value)
            pos += chunk
        return lanes

    def natural_width(self, st, insn, mem):
        kind, *rest = self.address(st, insn, mem)
        if kind != "ptr":
            return 4 if kind == "rip" else 8
        ptr = rest[0]
        if ptr.obj is STACK:
            cell = st.stack.cells.get(ptr.off)
            return cell[0] if cell and cell[0] in (4, 8) else 4
        return ptr.obj.width(ptr.off, self.heap)

    def vstore(self, st, insn, mem, lanes, width):
        for index in range(width // 4):
            self.store(st, insn, _Mem(mem, 4 * index), 4, lanes[index])

    # ------------------------------------------------------------ operands
    def read_op(self, st, insn, op, size=None):
        if op.type == X.X86_OP_REG:
            return self.get(st, self.cs.reg_name(op.reg))
        if op.type == X.X86_OP_IMM:
            return V(op.imm & MASK[size or op.size or 8])
        if op.type == X.X86_OP_MEM:
            return self.load(st, insn, op.mem, size or op.size)
        raise Unsupported("操作数类型")

    def write_op(self, st, insn, op, value, size=None):
        if op.type == X.X86_OP_REG:
            self.put(st, self.cs.reg_name(op.reg), value)
        elif op.type == X.X86_OP_MEM:
            self.store(st, insn, op.mem, size or op.size, value)
        else:
            raise Unsupported("写入操作数")

    # ------------------------------------------------------------ arithmetic
    def arith(self, op, a, b, size):
        prov = a.prov | b.prov
        av, bv = a.val, b.val
        if isinstance(av, Half):
            av = av.whole.val if av.index == 0 else Unk("指针高位")
        if isinstance(bv, Half):
            bv = bv.whole.val if bv.index == 0 else Unk("指针高位")
        if isinstance(av, int) and isinstance(bv, int):
            m = MASK[size]
            if op == "add":
                r = (av + bv) & m
            elif op == "sub":
                r = (av - bv) & m
            elif op == "and":
                r = av & bv & m
            elif op == "or":
                r = (av | bv) & m
            elif op == "xor":
                r = (av ^ bv) & m
            elif op == "imul":
                r = (signed(av, size) * signed(bv, size)) & m
            else:
                raise Unsupported(op)
            return V(r, prov)
        if isinstance(av, Ptr) and isinstance(bv, int):
            if op == "add":
                return V(av.add(signed(bv, 8)), prov)
            if op == "sub":
                return V(av.add(-signed(bv, 8)), prov)
            if op == "and" and size == 8 and not bv >> REFERENCE_TAG_BIT:
                return V(Ptr(av.obj, self.align(av, bv), 0), prov)
            if op == "or" and bv == 1 << REFERENCE_TAG_BIT:
                return V(Ptr(av.obj, av.off, 1), prov)
        if isinstance(bv, Ptr) and isinstance(av, int):
            if op == "add":
                return V(bv.add(signed(av, 8)), prov)
            if op == "or" and av == 1 << REFERENCE_TAG_BIT:
                return V(Ptr(bv.obj, bv.off, 1), prov)
            if op == "and" and size == 8 and not av >> REFERENCE_TAG_BIT:
                return V(Ptr(bv.obj, self.align(bv, av), 0), prov)
        if (
            isinstance(av, Ptr)
            and isinstance(bv, Ptr)
            and op == "sub"
            and av.obj is bv.obj
        ):
            return V((av.off - bv.off) & MASK[size], prov)
        sym = {"add": "+", "sub": "-", "and": "&", "or": "|", "xor": "^", "imul": "*"}[
            op
        ]
        return unk(shorten(f"({name_of(V(av))} {sym} {name_of(V(bv))})"), prov)

    @staticmethod
    def align(ptr, mask):
        """Pointer & mask that clears tag and low bits; the stack base is 8 mod 16."""
        low = mask & 0xF
        base = ENTRY_STACK_PHASE if ptr.obj is STACK else 0
        return ((ptr.off + base) & ~(~low & 0xF)) - base

    def compare_flags(self, a, b, size, label):
        av, bv = a.val, b.val
        if isinstance(av, Half) and av.index == 0:
            av = av.whole.val
        if isinstance(bv, Half) and bv.index == 0:
            bv = bv.whole.val
        prov = a.prov | b.prov
        if isinstance(av, int) and isinstance(bv, int):
            r = (av - bv) & MASK[size]
            sa, sb, sr = signed(av, size), signed(bv, size), signed(r, size)
            return Flags(
                zf=int(r == 0),
                sf=int(sr < 0),
                cf=int((av & MASK[size]) < (bv & MASK[size])),
                of=int((sa < 0) != (sb < 0) and (sr < 0) != (sa < 0)),
                pf=_parity(r),
                prov=prov,
            )
        if isinstance(av, Ptr) and isinstance(bv, Ptr) and av.obj is bv.obj:
            d = av.off - bv.off
            return Flags(zf=int(d == 0), sf=int(d < 0), cf=int(d < 0), prov=prov)
        if isinstance(av, Ptr) and bv == 0 or isinstance(bv, Ptr) and av == 0:
            return Flags(
                zf=0, sf=0, cf=int(av == 0), prov=prov
            )  # live references are non-null
        return Flags(label=(name_of(V(av)), name_of(V(bv))), kind="cmp", prov=prov)

    def result_flags(self, r, size, prov, kind="test"):
        """Flags of a result; kind "test" (logical ops) also means CF = OF = 0."""
        if isinstance(r.val, int):
            v = r.val & MASK[size]
            return Flags(
                zf=int(v == 0), sf=int(signed(v, size) < 0), pf=_parity(v), prov=prov
            )
        if isinstance(r.val, Ptr):
            if kind == "test":
                return Flags(zf=0, sf=0, prov=prov)
            nonzero = [t for t in _feasible(kind) if t[0] == t[1] == 0]
            return Flags(
                label=(name_of(r), "0"), kind=kind, prov=prov, candidates=nonzero
            )
        return Flags(label=(name_of(r), "0"), kind=kind, prov=prov)

    # ------------------------------------------------------------ float lanes
    @staticmethod
    def lane_float(v):
        if not isinstance(v.val, int):
            return None
        return f32(v.val)

    def fbin(self, a, b, fn, label):
        fa, fb = self.lane_float(a), self.lane_float(b)
        if fa is None or fb is None:
            return unk(
                shorten(
                    f"({name_of(a) if fa is None else fa} {label} {name_of(b) if fb is None else fb})"
                ),
                a.prov | b.prov,
            )
        return V(f32_bits(fn(fa, fb)), a.prov | b.prov)

    # ------------------------------------------------------------ control
    @staticmethod
    def condition_texts(flags, cc):
        if cc not in CONDITIONS:
            raise Unsupported(f"条件码 {cc}")
        relation = CONDITIONS[cc]
        negated = NEGATE.get(relation, f"not {relation}")
        if flags.kind == "imul" and cc not in IMUL_DEFINED:
            raise Unsupported(f"imul 后读取未定义的标志（{cc}）")
        left, right = flags.label
        texts = []
        for rel in (relation, negated):
            if flags.kind == "float":
                rel = rel.replace("u", "") if rel.endswith("u") else rel
            texts.append(
                shorten(
                    (
                        f"{left} {rel}"
                        if rel in ("<0", ">=0")
                        else f"{left} {rel} {right}"
                    ),
                    240,
                )
            )
        return texts

    def branch(self, st, insn, cc, target, fallthrough, worklist):
        flags = st.flags
        if flags.label is None:
            st.rip = target if flags.holds(cc) else fallthrough
            return
        true, false = flags.split(cc)
        if not false or not true:
            # Decided by conditions this path already took on the same flags.
            st.rip = target if true else fallthrough
            st.flags = flags.narrowed(true or false)
            return
        taken, not_taken = self.condition_texts(flags, cc)
        other = st.clone()
        st.conditions.append(taken)
        st.flags = flags.narrowed(true)
        st.rip = target
        other.conditions.append(not_taken)
        other.flags = flags.narrowed(false)
        other.rip = fallthrough
        worklist.append(other)

    def condition_value(self, st, cc, worklist, insn):
        """setcc/cmovcc on unknown flags: this path takes the condition as true,
        a copy re-executes the instruction with it false."""
        flags = st.flags
        if flags.label is None:
            return flags.holds(cc)
        true, false = flags.split(cc)
        if not false or not true:
            st.flags = flags.narrowed(true or false)
            return bool(true)
        taken, not_taken = self.condition_texts(flags, cc)
        other = st.clone()
        other.conditions.append(not_taken)
        other.flags = flags.narrowed(false)
        other.rip = insn.address
        worklist.append(other)
        st.conditions.append(taken)
        st.flags = flags.narrowed(true)
        return True

    def run(self, entry, setup, return_type):
        """Run from entry; setup(state) seeds registers. Returns path results."""
        start = State()
        start.rip = entry
        setup(start)
        self.total_steps = 0
        worklist, results = [start], []
        reverted = {}  # id -> snapshot; holding it keeps the id from being reused
        while worklist:
            if len(results) + len(worklist) > MAX_PATHS:
                raise PathEnd("too_many_paths", f"路径超过 {MAX_PATHS}")
            st = worklist.pop()
            try:
                result = self.path(st, worklist, return_type)
            except Budget as error:
                raise PathEnd("too_long", str(error)) from None
            except (Unsupported, PathEnd) as error:
                status = error.status if isinstance(error, PathEnd) else "unsupported"
                recoverable = status in (
                    "unsupported",
                    "writes_state",
                    "too_long",
                    "null",
                )
                if recoverable and st.snapshot is not None:
                    # An inlined callee failed: replay the outermost call as opaque.
                    snap, callee = st.snapshot
                    if id(snap) not in reverted:
                        reverted[id(snap)] = snap
                        resumed = snap.clone()
                        resumed.snapshot = None
                        self.opaque_effects(resumed, callee)
                        detail = (
                            error.detail if isinstance(error, PathEnd) else str(error)
                        )
                        resumed.opaque[-1] = f"{resumed.opaque[-1]}（未模拟：{detail}）"
                        if resumed.resume == "exit":
                            results.append(self.finish(resumed, return_type))
                        else:
                            resumed.rip = resumed.resume
                            worklist.append(resumed)
                    continue
                if status == "dropped":
                    continue
                detail = error.detail if isinstance(error, PathEnd) else str(error)
                results.append(
                    dict(status=status, detail=detail, conditions=st.conditions)
                )
                continue
            results.append(result)
        return results

    def opaque_effects(self, st, callee):
        """A call whose body is not emulated: volatile state becomes unknown."""
        name = (
            self.names.get(callee, f"sub_{callee:x}")
            if isinstance(callee, int)
            else callee
        )
        st.opaque.append(name)
        for reg in VOLATILE:
            st.regs[reg] = unk(f"{name}() 后的 {reg}")
        st.regs["rax"] = unk(f"{name}()")
        st.vregs[0] = [unk(f"{name}()")] + unknown_lanes(f"{name}() 后的 xmm0")[1:]
        for index in range(1, 6):
            st.vregs[index] = unknown_lanes(f"{name}() 后的 xmm{index}")
        st.flags = Flags(label=(f"{name}() 后的标志", "0"), kind="any")

    def path(self, st, worklist, return_type):
        while True:
            st.steps += 1
            self.total_steps += 1
            if self.total_steps > MAX_TOTAL_STEPS:
                raise Budget(f"全部路径合计超过 {MAX_TOTAL_STEPS} 条指令")
            if st.steps > MAX_STEPS:
                raise PathEnd("too_long", f"超过 {MAX_STEPS} 条指令")
            if st.rip is None:  # forked by setcc/cmovcc; this copy re-executes nothing
                raise PathEnd("dropped")
            insn = self.insn(st.rip)
            nxt = insn.address + insn.size
            outcome = self.step(st, insn, nxt, worklist, return_type)
            if outcome is not None:
                return outcome
            rsp = st.regs.get("rsp")
            if rsp is None or not isinstance(rsp.val, Ptr) or rsp.val.obj is not STACK:
                # e.g. a stack probe by an unknown size; frames can no longer be tracked
                raise Unsupported(f"栈指针未知 @ {insn.address:#x}")

    def step(self, st, insn, nxt, worklist, return_type):
        m, ops = insn.mnemonic, insn.operands
        if m in (
            "nop",
            "vzeroupper",
            "endbr64",
            "prefetcht0",
            "prefetchw",
            "pause",
            "lfence",
        ):
            st.rip = nxt
            return None
        if m == "int3":
            raise PathEnd("throws", f"异常路径 {insn.address:#x}")
        if m == "ret":
            rsp = st.regs["rsp"]
            ret = self.load(st, insn, _Mem.at_rsp(), 8)
            st.regs["rsp"] = V(rsp.val.add(8 + (ops[0].imm if ops else 0)))
            if isinstance(ret.val, str):
                if ret.val == "exit":
                    return self.finish(st, return_type)
                raise Unsupported("返回地址异常")
            if not isinstance(ret.val, int):
                raise Unsupported("返回地址未知")
            st.depth -= 1
            if st.depth == 0:
                st.snapshot = None
            st.rip = ret.val
            return None
        if m in ("call", "jmp") and ops and ops[0].type == X.X86_OP_IMM:
            target = ops[0].imm
            if m == "jmp" and self.same_function(insn.address, target):
                st.rip = target
                return None
            return self.call(
                st, insn, target, nxt if m == "call" else None, return_type
            )
        if m in ("call", "jmp"):
            # Indirect: virtual call or jump table; the result stays unknown.
            if m == "jmp":
                target = self.read_op(st, insn, ops[0], 8)
                if isinstance(target.val, int) and self.same_function(
                    insn.address, target.val
                ):
                    st.rip = target.val
                    return None
                raise Unsupported(f"间接跳转 {insn.address:#x}")
            self.opaque_effects(st, f"间接调用@{insn.address:#x}")
            st.rip = nxt
            return None
        if m.startswith("j"):
            cc = m[1:]
            if cc == "rcxz" or cc == "ecxz":
                raise Unsupported(m)
            self.branch(st, insn, cc, ops[0].imm, nxt, worklist)
            return None
        handler = getattr(self, "op_" + m, None)
        if handler is None:
            raise Unsupported(f"指令 {m} @ {insn.address:#x}")
        handler(st, insn, ops, worklist)
        if st.rip is not None and st.rip == insn.address:
            st.rip = nxt  # handlers that do not jump fall through
        return None

    def same_function(self, a, b):
        """Both addresses lie in one function range of the exception directory."""
        import bisect

        index = bisect.bisect_right(self.pe.starts, a) - 1
        if index < 0:
            return False
        start, end = self.pe.functions[index]
        return start <= a < end and start <= b < end

    def call(self, st, insn, target, resume, return_type):
        """Direct call (resume = next insn) or tail jump (resume = None)."""
        tail = resume is None
        if tail:
            resume = st.stack.read(st.regs["rsp"].val.off, 8, self.heap).val
            st.regs["rsp"] = V(st.regs["rsp"].val.add(8))
            if resume != "exit":
                st.depth -= 1
        elif self.insn(resume).mnemonic == "int3":
            raise PathEnd("throws", f"抛出异常 {insn.address:#x}")
        if target in self.skip_calls or target in self.intercept:
            if target in self.intercept:
                self.intercept[target](self, st)
            return self.resume_at(st, resume, return_type)
        if st.depth >= MAX_CALL_DEPTH or not self.inline_ok(target):
            self.opaque_effects(st, target)
            return self.resume_at(st, resume, return_type)
        if st.snapshot is None:
            snap = st.clone()
            snap.resume = resume
            st.snapshot = (snap, target)
        rsp = st.regs["rsp"].val.add(-8)
        st.regs["rsp"] = V(rsp)
        st.stack.write(rsp.off, 8, V(resume))
        if resume != "exit":
            st.depth += 1
        st.rip = target
        return None

    def resume_at(self, st, resume, return_type):
        if resume == "exit":
            return self.finish(st, return_type)
        st.rip = resume
        return None

    def finish(self, st, return_type):
        if return_type in ("System.Single",):
            lane = self.vget_index(st, 0)[0]
            value = f32(lane.val) if isinstance(lane.val, int) else lane.val
            prov = lane.prov
        elif return_type == "System.Double":
            lanes = self.vget_index(st, 0)
            if isinstance(lanes[0].val, int) and isinstance(lanes[1].val, int):
                value = struct.unpack(
                    "<d", struct.pack("<Q", lanes[0].val | lanes[1].val << 32)
                )[0]
            else:
                value = Unk("double")
            prov = lanes[0].prov | lanes[1].prov
        elif return_type == "System.Void":
            value, prov = None, frozenset()
        else:
            raw = st.regs.get("rax", unk("rax"))
            size = {
                "System.Boolean": 1,
                "System.Byte": 1,
                "System.Int16": 2,
                "System.UInt16": 2,
                "System.Int64": 8,
                "System.UInt64": 8,
            }.get(return_type, 4)
            if isinstance(raw.val, int):
                value = (
                    signed(raw.val, size)
                    if return_type
                    not in (
                        "System.Boolean",
                        "System.UInt32",
                        "System.UInt64",
                        "System.Byte",
                    )
                    else raw.val & MASK[size]
                )
                if return_type == "System.Boolean":
                    value = bool(value)
            elif isinstance(raw.val, Ptr):
                value = Unk(f"对象 {raw.val.obj.path}")
            else:
                value = raw.val if isinstance(raw.val, Unk) else Unk(name_of(raw))
            prov = raw.prov
        return dict(
            status="ok",
            value=value,
            prov=prov,
            conditions=st.conditions,
            opaque=st.opaque,
            writes=[self.describe_write(entry) for entry in st.writes.values()],
        )

    def describe_write(self, entry):
        """Target field path and value, shown by the field's declared type."""
        obj, off, size, value = entry
        ftype = None
        if obj is None:
            target = off if isinstance(off, str) else f"全局 {off:#x}"
        else:
            layout = self.heap.layouts.fields(obj.type_name) if obj.type_name else {}
            name, ftype = layout.get(off, (None, None))
            target = f"{obj.path}.{name}" if name else f"{obj.path}+0x{off:x}"
        if isinstance(value.val, int):
            if ftype == "System.Single" and size == 4:
                shown = float(f"{f32(value.val):.7g}")
            elif ftype == "System.Boolean":
                shown = bool(value.val & 0xFF)
            else:
                shown = signed(value.val, size) if size in (1, 2, 4, 8) else value.val
        else:
            shown = name_of(value)
        return dict(target=target, type=ftype, value=shown, prov=value.prov)

    def vget_index(self, st, index):
        lanes = st.vregs.get(index)
        return lanes if lanes is not None else unknown_lanes(f"调用者 xmm{index}")

    # ------------------------------------------------------------ integer ops
    def op_mov(self, st, insn, ops, _):
        dst, src = ops
        size = dst.size
        value = self.read_op(st, insn, src, size)
        if src.type == X.X86_OP_IMM and dst.type == X.X86_OP_REG and size == 8:
            value = V(src.imm & MASK[8])
        self.write_op(st, insn, dst, value, size)

    op_movabs = op_mov

    def op_movzx(self, st, insn, ops, _):
        value = self.read_op(st, insn, ops[1], ops[1].size)
        if isinstance(value.val, int):
            value = V(value.val & MASK[ops[1].size], value.prov)
        self.put(st, self.cs.reg_name(ops[0].reg), value)

    def op_movsx(self, st, insn, ops, _):
        value = self.read_op(st, insn, ops[1], ops[1].size)
        if isinstance(value.val, int):
            value = V(signed(value.val, ops[1].size) & MASK[ops[0].size], value.prov)
        self.put(st, self.cs.reg_name(ops[0].reg), value)

    op_movsxd = op_movsx

    def op_lea(self, st, insn, ops, _):
        mem = ops[1].mem
        if mem.base and self.cs.reg_name(mem.base) == "rip":
            value = V(insn.address + insn.size + mem.disp)
        else:
            # Plain arithmetic: an integer base is not a pointer dereference.
            base = self.get(st, self.cs.reg_name(mem.base)) if mem.base else V(0)
            index = self.get(st, self.cs.reg_name(mem.index)) if mem.index else V(0)
            scaled = (
                self.arith("imul", index, V((mem.scale or 1) & MASK[8]), 8)
                if mem.index
                else V(0)
            )
            value = self.arith(
                "add", self.arith("add", base, scaled, 8), V(mem.disp & MASK[8]), 8
            )
        if ops[0].size == 4 and isinstance(value.val, int):
            value = V(value.val & MASK[4], value.prov)
        self.put(st, self.cs.reg_name(ops[0].reg), value)

    def _binary(self, st, insn, ops, op):
        dst, src = ops
        size = dst.size
        a = self.read_op(st, insn, dst, size)
        b = self.read_op(st, insn, src, size)
        if src.type == X.X86_OP_IMM:
            b = V(src.imm & MASK[size])
        if (
            op == "xor"
            and dst.type == X.X86_OP_REG
            and src.type == X.X86_OP_REG
            and dst.reg == src.reg
        ):
            r = V(0)
        else:
            r = self.arith(op, a, b, size)
        self.write_op(st, insn, dst, r, size)
        if op == "sub":
            st.flags = self.compare_flags(a, b, size, None)
            return
        logical = op in ("and", "or", "xor")
        st.flags = self.result_flags(r, size, r.prov, "test" if logical else "result")
        if op == "add" and isinstance(a.val, int) and isinstance(b.val, int):
            st.flags.cf = int((a.val & MASK[size]) + (b.val & MASK[size]) > MASK[size])
            sa, sb, sr = signed(a.val, size), signed(b.val, size), signed(r.val, size)
            st.flags.of = int((sa < 0) == (sb < 0) and (sr < 0) != (sa < 0))

    def op_add(self, st, insn, ops, _):
        self._binary(st, insn, ops, "add")

    def op_sub(self, st, insn, ops, _):
        self._binary(st, insn, ops, "sub")

    def op_and(self, st, insn, ops, _):
        self._binary(st, insn, ops, "and")

    def op_or(self, st, insn, ops, _):
        self._binary(st, insn, ops, "or")

    def op_xor(self, st, insn, ops, _):
        self._binary(st, insn, ops, "xor")

    def op_imul(self, st, insn, ops, _):
        size = ops[0].size
        if len(ops) == 3:
            a = self.read_op(st, insn, ops[1], size)
            b = V(ops[2].imm & MASK[size])
        elif len(ops) == 2:
            a = self.read_op(st, insn, ops[0], size)
            b = self.read_op(st, insn, ops[1], size)
        else:
            raise Unsupported("单操作数 imul")
        r = self.arith("imul", a, b, size)
        self.put(st, self.cs.reg_name(ops[0].reg), r)
        label = (f"{name_of(a)} * {name_of(b)}", f"{8 * size} 位")
        flags = Flags(label=label, kind="imul", prov=r.prov)
        if isinstance(a.val, int) and isinstance(b.val, int):
            overflow = int(
                signed(r.val, size) != signed(a.val, size) * signed(b.val, size)
            )
            flags = flags.narrowed([t for t in flags.candidates if t[2] == overflow])
        st.flags = flags

    def _step(self, st, insn, ops, op):
        """inc / dec: OF from the result, CF kept from the previous instruction."""
        size = ops[0].size
        a = self.read_op(st, insn, ops[0])
        r = self.arith(op, a, V(1), size)
        self.write_op(st, insn, ops[0], r)
        old = st.flags
        new = self.result_flags(r, size, r.prov, "result")
        if new.label is None:
            edge = 1 << (8 * size - 1)  # signed minimum after inc, maximum after dec
            new.of = int(r.val & MASK[size] == (edge if op == "add" else edge - 1))
        if old.label is None:
            if new.label is None:
                new.cf = old.cf
                st.flags = new
                return
            new.candidates = [t for t in new.candidates if t[2] == old.cf]
            st.flags = new
            return
        if new.label is None:
            # The flags left are still those of the earlier comparison, through CF.
            carries = {t[2] for t in old.candidates}
            st.flags = old.narrowed(
                [(new.zf, new.sf, c, new.of, new.pf) for c in sorted(carries)]
            )
            return
        raise Unsupported(f"{insn.mnemonic} 的结果和保留的 CF 都依赖未知量")

    def op_inc(self, st, insn, ops, _):
        self._step(st, insn, ops, "add")

    def op_dec(self, st, insn, ops, _):
        self._step(st, insn, ops, "sub")

    def op_neg(self, st, insn, ops, _):
        size = ops[0].size
        a = self.read_op(st, insn, ops[0])
        r = self.arith("sub", V(0), a, size)
        self.write_op(st, insn, ops[0], r)
        st.flags = self.result_flags(r, size, r.prov, "result")
        if isinstance(a.val, int):
            st.flags.cf = int(a.val & MASK[size] != 0)
            st.flags.of = int(a.val & MASK[size] == 1 << (8 * size - 1))

    def op_not(self, st, insn, ops, _):
        a = self.read_op(st, insn, ops[0])
        r = (
            V(~a.val & MASK[ops[0].size], a.prov)
            if isinstance(a.val, int)
            else unk(f"~{name_of(a)}", a.prov)
        )
        self.write_op(st, insn, ops[0], r)

    def _shift(self, st, insn, ops, kind):
        size = ops[0].size
        a = self.read_op(st, insn, ops[0])
        count = self.read_op(st, insn, ops[1], 1) if len(ops) > 1 else V(1)
        if not isinstance(count.val, int):
            raise Unsupported("未知移位量")
        n = count.val & (63 if size == 8 else 31)
        if isinstance(a.val, int):
            if kind == "shl":
                r = (a.val << n) & MASK[size]
            elif kind == "shr":
                r = (a.val & MASK[size]) >> n
            else:
                r = (signed(a.val, size) >> n) & MASK[size]
            value = V(r, a.prov)
        else:
            value = unk(f"({name_of(a)} {kind} {n})", a.prov)
        self.write_op(st, insn, ops[0], value)
        if n:
            st.flags = self.result_flags(value, size, value.prov, "result")
            if isinstance(a.val, int):  # CF is the last bit shifted out
                bits = 8 * size
                if kind == "shl":
                    st.flags.cf = int(n <= bits and (a.val >> (bits - n)) & 1)
                else:
                    source = (
                        a.val & MASK[size] if kind == "shr" else signed(a.val, size)
                    )
                    st.flags.cf = (source >> (n - 1)) & 1
                st.flags.of = int(
                    n == 1
                    and (
                        (r >> (bits - 1)) ^ st.flags.cf
                        if kind == "shl"
                        else kind == "shr" and (a.val & MASK[size]) >> (bits - 1)
                    )
                )

    def op_shl(self, st, insn, ops, _):
        self._shift(st, insn, ops, "shl")

    op_sal = op_shl

    def op_shr(self, st, insn, ops, _):
        self._shift(st, insn, ops, "shr")

    def op_sar(self, st, insn, ops, _):
        self._shift(st, insn, ops, "sar")

    def op_cmp(self, st, insn, ops, _):
        size = ops[0].size
        a = self.read_op(st, insn, ops[0], size)
        b = self.read_op(st, insn, ops[1], size)
        if ops[1].type == X.X86_OP_IMM:
            b = V(ops[1].imm & MASK[size])
        st.flags = self.compare_flags(a, b, size, None)

    def op_test(self, st, insn, ops, _):
        size = ops[0].size
        a = self.read_op(st, insn, ops[0], size)
        b = self.read_op(st, insn, ops[1], size)
        if ops[1].type == X.X86_OP_IMM:
            b = V(ops[1].imm & MASK[size])
        same = (
            ops[0].type == X.X86_OP_REG
            and ops[1].type == X.X86_OP_REG
            and ops[0].reg == ops[1].reg
        )
        if same and isinstance(a.val, (Ptr, Half)):
            st.flags = Flags(zf=0, sf=0, prov=a.prov)
            return
        r = self.arith("and", a, b, size)
        if not r.known and same:
            st.flags = Flags(label=(name_of(a), "0"), kind="test", prov=a.prov)
            return
        if not r.known:
            st.flags = Flags(
                label=(f"({name_of(a)} & {name_of(b)})", "0"), kind="test", prov=r.prov
            )
            return
        st.flags = self.result_flags(r, size, r.prov)

    def op_bt(self, st, insn, ops, _):
        a = self.read_op(st, insn, ops[0])
        b = self.read_op(st, insn, ops[1], 1)
        if not (isinstance(a.val, int) and isinstance(b.val, int)):
            st.flags = Flags(
                label=(f"位 {name_of(b)} of {name_of(a)}", "0"),
                kind="bit",
                prov=a.prov | b.prov,
            )
            return
        st.flags = Flags(
            cf=(a.val >> (b.val & (8 * ops[0].size - 1))) & 1, prov=a.prov | b.prov
        )

    def op_btr(self, st, insn, ops, _):
        a = self.read_op(st, insn, ops[0])
        bit = ops[1].imm if ops[1].type == X.X86_OP_IMM else None
        if bit is None:
            index = self.read_op(st, insn, ops[1], ops[1].size)
            if isinstance(index.val, int):
                bit = index.val & (8 * ops[0].size - 1)
        if bit == REFERENCE_TAG_BIT and isinstance(a.val, Ptr):
            self.write_op(st, insn, ops[0], V(Ptr(a.val.obj, a.val.off, 0), a.prov))
            st.flags = Flags(cf=a.val.tag, prov=a.prov)
            return
        if bit is None or not isinstance(a.val, int):
            # Unknown operand or bit: the result and CF stay unknown, named after the operand.
            label = f"{name_of(a)} 清除位 {bit if bit is not None else '?'}"
            self.write_op(st, insn, ops[0], unk(label, a.prov))
            st.flags = Flags(
                label=(f"{name_of(a)} 的位 {bit}", "0"), kind="bit", prov=a.prov
            )
            return
        st.flags = Flags(cf=(a.val >> bit) & 1, prov=a.prov)
        self.write_op(st, insn, ops[0], V(a.val & ~(1 << bit), a.prov))

    def op_bts(self, st, insn, ops, _):
        a = self.read_op(st, insn, ops[0])
        bit = ops[1].imm if ops[1].type == X.X86_OP_IMM else None
        if bit is None or not isinstance(a.val, int):
            self.write_op(st, insn, ops[0], unk(f"{name_of(a)} 置位 {bit}", a.prov))
            st.flags = Flags(
                label=(f"{name_of(a)} 的位 {bit}", "0"), kind="bit", prov=a.prov
            )
            return
        st.flags = Flags(cf=(a.val >> bit) & 1, prov=a.prov)
        self.write_op(st, insn, ops[0], V(a.val | (1 << bit), a.prov))

    def op_push(self, st, insn, ops, _):
        value = self.read_op(st, insn, ops[0], 8)
        rsp = st.regs["rsp"].val.add(-8)
        st.regs["rsp"] = V(rsp)
        st.stack.write(rsp.off, 8, value)

    def op_pop(self, st, insn, ops, _):
        rsp = st.regs["rsp"].val
        value = st.stack.read(rsp.off, 8, self.heap)
        st.regs["rsp"] = V(rsp.add(8))
        self.put(st, self.cs.reg_name(ops[0].reg), value)

    def op_cqo(self, st, insn, ops, _):
        a = st.regs.get("rax", unk("rax"))
        st.regs["rdx"] = (
            V(MASK[8] if signed(a.val, 8) < 0 else 0, a.prov)
            if isinstance(a.val, int)
            else unk(f"符号扩展 {name_of(a)}", a.prov)
        )

    def op_cdq(self, st, insn, ops, _):
        a = self.get(st, "eax")
        st.regs["rdx"] = (
            V(MASK[4] if signed(a.val, 4) < 0 else 0, a.prov)
            if isinstance(a.val, int)
            else unk(f"符号扩展 {name_of(a)}", a.prov)
        )

    def op_cdqe(self, st, insn, ops, _):
        a = self.get(st, "eax")
        st.regs["rax"] = (
            V(signed(a.val, 4) & MASK[8], a.prov) if isinstance(a.val, int) else a
        )

    def op_idiv(self, st, insn, ops, _):
        size = ops[0].size
        divisor = self.read_op(st, insn, ops[0], size)
        lo = self.get(st, {8: "rax", 4: "eax"}[size])
        hi = self.get(st, {8: "rdx", 4: "edx"}[size])
        if not all(isinstance(v.val, int) for v in (divisor, lo, hi)):
            prov = divisor.prov | lo.prov
            self.put(
                st,
                {8: "rax", 4: "eax"}[size],
                unk(f"({name_of(lo)} / {name_of(divisor)})", prov),
            )
            self.put(st, {8: "rdx", 4: "edx"}[size], unk("余数", prov))
            return
        dividend = (
            signed(lo.val | hi.val << (8 * size), 2 * size)
            if size <= 4
            else signed(lo.val | hi.val << 64, 16)
        )
        d = signed(divisor.val, size)
        if d == 0:
            raise PathEnd("throws", "除以零")
        q = abs(dividend) // abs(d) * (1 if (dividend < 0) == (d < 0) else -1)
        r = dividend - q * d
        if not -(1 << (8 * size - 1)) <= q < 1 << (8 * size - 1):
            raise PathEnd("throws", "除法溢出")
        prov = divisor.prov | lo.prov | hi.prov
        self.put(st, {8: "rax", 4: "eax"}[size], V(q & MASK[size], prov))
        self.put(st, {8: "rdx", 4: "edx"}[size], V(r & MASK[size], prov))

    def op_setcc(self, st, insn, cc, worklist):
        truth = self.condition_value(st, cc, worklist, insn)
        if st.rip is None:
            return
        op = insn.operands[0]
        self.write_op(st, insn, op, V(int(truth), st.flags.prov), 1)

    def op_cmovcc(self, st, insn, cc, worklist):
        truth = self.condition_value(st, cc, worklist, insn)
        if st.rip is None:
            return
        dst, src = insn.operands
        if truth:
            self.put(
                st, self.cs.reg_name(dst.reg), self.read_op(st, insn, src, dst.size)
            )
        elif dst.size == 4:
            self.put(
                st, self.cs.reg_name(dst.reg), self.get(st, self.cs.reg_name(dst.reg))
            )

    def op_xchg(self, st, insn, ops, _):
        a, b = self.read_op(st, insn, ops[0]), self.read_op(st, insn, ops[1])
        self.write_op(st, insn, ops[0], b)
        self.write_op(st, insn, ops[1], a)

    # ------------------------------------------------------------ vector ops
    def _vsrc(self, st, insn, op, width):
        if op.type == X.X86_OP_REG:
            return self.vget(st, op.reg)
        return self.vload(st, insn, op.mem, width) + [V(0)] * ((32 - width) // 4)

    def op_vmovss(self, st, insn, ops, _):
        if len(ops) == 3:  # vmovss xmm1, xmm2, xmm3: merge
            low = self.vget(st, ops[2].reg)[0]
            lanes = list(self.vget(st, ops[1].reg))
            lanes[0] = low
            self.vput(st, ops[0].reg, lanes, 16)
            return
        dst, src = ops
        if dst.type == X.X86_OP_MEM:
            self.store(st, insn, dst.mem, 4, self.vget(st, src.reg)[0])
            return
        if src.type == X.X86_OP_MEM:
            value = self.load(st, insn, src.mem, 4)
            self.vput(st, dst.reg, [value, V(0), V(0), V(0)], 16)
        else:  # legacy movss xmm1, xmm2: the upper lanes of xmm1 stay
            lanes = list(self.vget(st, dst.reg))
            lanes[0] = self.vget(st, src.reg)[0]
            self.vput(st, dst.reg, lanes, 16)

    op_movss = op_vmovss

    def op_vmovsd(self, st, insn, ops, _):
        if len(ops) == 3:
            lanes = list(self.vget(st, ops[1].reg))
            lanes[:2] = self.vget(st, ops[2].reg)[:2]
            self.vput(st, ops[0].reg, lanes, 16)
            return
        dst, src = ops
        if dst.type == X.X86_OP_MEM:
            self.vstore(st, insn, dst.mem, self.vget(st, src.reg), 8)
            return
        if src.type == X.X86_OP_REG:  # legacy movsd xmm1, xmm2: upper lanes stay
            lanes = list(self.vget(st, dst.reg))
            lanes[:2] = self.vget(st, src.reg)[:2]
            self.vput(st, dst.reg, lanes, 16)
            return
        lanes = self._vsrc(st, insn, src, 8)
        self.vput(st, dst.reg, lanes[:2] + [V(0), V(0)], 16)

    def _vmove(self, st, insn, ops, width=None):
        dst, src = ops
        width = width or max(dst.size, src.size)
        if dst.type == X.X86_OP_MEM:
            self.vstore(st, insn, dst.mem, self.vget(st, src.reg), width)
            return
        self.vput(st, dst.reg, self._vsrc(st, insn, src, width), width)

    def op_vmovaps(self, st, insn, ops, _):
        self._vmove(st, insn, ops)

    op_vmovups = op_vmovapd = op_vmovupd = op_vmovdqu = op_vmovdqa = op_movaps = (
        op_movups
    ) = op_vmovaps
    op_vmovdqu64 = op_vmovdqu32 = op_vmovdqa64 = op_movdqu = op_movdqa = op_vmovaps

    def op_vmovlps(self, st, insn, ops, _):
        if ops[0].type == X.X86_OP_MEM:
            self.vstore(st, insn, ops[0].mem, self.vget(st, ops[1].reg), 8)
            return
        lanes = list(self.vget(st, ops[1].reg))
        lanes[0:2] = self.vload(st, insn, ops[2].mem, 8)
        self.vput(st, ops[0].reg, lanes, 16)

    def op_vpshufd(self, st, insn, ops, _):
        a = self._vsrc(st, insn, ops[1], 16)
        imm = ops[2].imm
        self.vput(st, ops[0].reg, [a[(imm >> (2 * i)) & 3] for i in range(4)], 16)

    def op_vmovd(self, st, insn, ops, _):
        dst, src = ops
        if dst.type == X.X86_OP_REG and self.cs.reg_name(dst.reg).startswith(
            ("xmm", "ymm")
        ):
            value = self.read_op(st, insn, src, 4)
            self.vput(st, dst.reg, [value, V(0), V(0), V(0)], 16)
        else:
            self.write_op(st, insn, dst, self.vget(st, src.reg)[0], 4)

    op_movd = op_vmovd

    def op_vmovq(self, st, insn, ops, _):
        dst, src = ops
        if dst.type == X.X86_OP_REG and self.cs.reg_name(dst.reg).startswith(
            ("xmm", "ymm")
        ):
            if src.type == X.X86_OP_REG and self.cs.reg_name(src.reg).startswith(
                ("xmm", "ymm")
            ):
                lanes = self.vget(st, src.reg)[:2]
            elif src.type == X.X86_OP_MEM:
                lanes = self.vload(st, insn, src.mem, 8)
            else:
                value = self.read_op(st, insn, src, 8)
                lanes = (
                    [V(value.val & MASK[4], value.prov), V(value.val >> 32, value.prov)]
                    if isinstance(value.val, int)
                    else [V(Half(value, 0)), V(Half(value, 1))]
                )
            self.vput(st, dst.reg, lanes + [V(0), V(0)], 16)
        else:
            lanes = self.vget(st, src.reg)
            if dst.type == X.X86_OP_MEM:
                self.vstore(st, insn, dst.mem, lanes, 8)
                return
            lo, hi = lanes[0], lanes[1]
            if isinstance(lo.val, int) and isinstance(hi.val, int):
                self.put(
                    st,
                    self.cs.reg_name(dst.reg),
                    V(lo.val | hi.val << 32, lo.prov | hi.prov),
                )
            elif (
                isinstance(lo.val, Half)
                and isinstance(hi.val, Half)
                and lo.val.whole is hi.val.whole
            ):
                self.put(st, self.cs.reg_name(dst.reg), lo.val.whole)
            else:
                self.put(
                    st, self.cs.reg_name(dst.reg), unk("向量转整数", lo.prov | hi.prov)
                )

    op_movq = op_vmovq

    def _vlogic(self, st, insn, ops, kind):
        dst = ops[0]
        a = self.vget(st, ops[-2].reg) if len(ops) == 3 else self.vget(st, dst.reg)
        b = self._vsrc(st, insn, ops[-1], max(dst.size, 16))
        if (
            len(ops) >= 2
            and ops[-2].type == X.X86_OP_REG
            and ops[-1].type == X.X86_OP_REG
            and ops[-2].reg == ops[-1].reg
            and kind == "xor"
        ):
            self.vput(st, dst.reg, [V(0)] * 8, dst.size)
            return
        lanes = [self.arith(kind, x, y, 4) for x, y in zip(a, b)]
        self.vput(st, dst.reg, lanes, dst.size)

    def op_vxorps(self, st, insn, ops, _):
        self._vlogic(st, insn, ops, "xor")

    op_vxorpd = op_vpxor = op_xorps = op_pxor = op_vpxord = op_vxorps

    def op_vandps(self, st, insn, ops, _):
        self._vlogic(st, insn, ops, "and")

    op_vandpd = op_vpand = op_andps = op_vandps

    def op_vorps(self, st, insn, ops, _):
        self._vlogic(st, insn, ops, "or")

    op_vpor = op_orps = op_vorps

    def _scalar(self, st, insn, ops, fn, label):
        dst = ops[0]
        if len(ops) == 3:
            base, a, src = (
                self.vget(st, ops[1].reg),
                self.vget(st, ops[1].reg)[0],
                ops[2],
            )
        else:
            base, a, src = self.vget(st, dst.reg), self.vget(st, dst.reg)[0], ops[1]
        b = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        lanes = list(base)
        lanes[0] = self.fbin(a, b, fn, label)
        self.vput(st, dst.reg, lanes, 16)

    def op_vaddss(self, st, insn, ops, _):
        self._scalar(st, insn, ops, lambda x, y: x + y, "+")

    def op_vsubss(self, st, insn, ops, _):
        self._scalar(st, insn, ops, lambda x, y: x - y, "-")

    def op_vmulss(self, st, insn, ops, _):
        self._scalar(st, insn, ops, lambda x, y: x * y, "*")

    def op_vdivss(self, st, insn, ops, _):
        self._scalar(
            st,
            insn,
            ops,
            _divide,
            "/",
        )

    def op_vmaxss(self, st, insn, ops, _):
        self._scalar(st, insn, ops, lambda x, y: x if x > y else y, "max")

    def op_vminss(self, st, insn, ops, _):
        self._scalar(st, insn, ops, lambda x, y: x if x < y else y, "min")

    op_addss, op_subss, op_mulss, op_divss = op_vaddss, op_vsubss, op_vmulss, op_vdivss
    op_maxss, op_minss = op_vmaxss, op_vminss

    # Scalar doubles occupy lanes 0-1.
    @staticmethod
    def lane_double(lanes):
        lo, hi = lanes[0], lanes[1]
        if isinstance(lo.val, int) and isinstance(hi.val, int):
            return (
                struct.unpack("<d", struct.pack("<Q", lo.val | hi.val << 32))[0],
                lo.prov | hi.prov,
            )
        return None, lo.prov | hi.prov

    def _scalar_double(self, st, insn, ops, fn, label):
        dst = ops[0]
        base = self.vget(st, ops[1].reg if len(ops) == 3 else dst.reg)
        src = ops[-1]
        other = (
            self.vget(st, src.reg)
            if src.type == X.X86_OP_REG
            else self.vload(st, insn, src.mem, 8)
        )
        (a, pa), (b, pb) = self.lane_double(base), self.lane_double(other)
        lanes = list(base)
        if a is None or b is None:
            left = name_of(base[0]) if a is None else f"{a:g}"
            right = name_of(other[0]) if b is None else f"{b:g}"
            lanes[0:2] = [unk(shorten(f"({left} {label} {right})"), pa | pb)] * 2
        else:
            bits = struct.unpack("<Q", struct.pack("<d", fn(a, b)))[0]
            lanes[0:2] = [V(bits & MASK[4], pa | pb), V(bits >> 32, pa | pb)]
        self.vput(st, dst.reg, lanes, 16)

    def op_vaddsd(self, st, insn, ops, _):
        self._scalar_double(st, insn, ops, lambda x, y: x + y, "+")

    def op_vsubsd(self, st, insn, ops, _):
        self._scalar_double(st, insn, ops, lambda x, y: x - y, "-")

    def op_vmulsd(self, st, insn, ops, _):
        self._scalar_double(st, insn, ops, lambda x, y: x * y, "*")

    def op_vdivsd(self, st, insn, ops, _):
        self._scalar_double(st, insn, ops, _divide, "/")

    def op_vmaxsd(self, st, insn, ops, _):
        self._scalar_double(st, insn, ops, lambda x, y: x if x > y else y, "max")

    def op_vminsd(self, st, insn, ops, _):
        self._scalar_double(st, insn, ops, lambda x, y: x if x < y else y, "min")

    def op_vcvtsi2sd(self, st, insn, ops, _):
        src = ops[-1]
        value = self.read_op(st, insn, src, src.size)
        lanes = list(self.vget(st, ops[1].reg if len(ops) == 3 else ops[0].reg))
        if isinstance(value.val, int):
            bits = struct.unpack(
                "<Q", struct.pack("<d", float(signed(value.val, src.size)))
            )[0]
            lanes[0:2] = [V(bits & MASK[4], value.prov), V(bits >> 32, value.prov)]
        else:
            lanes[0:2] = [unk(name_of(value), value.prov)] * 2
        self.vput(st, ops[0].reg, lanes, 16)

    def op_vcvttsd2si(self, st, insn, ops, _):
        src = ops[1]
        lanes = (
            self.vget(st, src.reg)
            if src.type == X.X86_OP_REG
            else self.vload(st, insn, src.mem, 8)
        )
        d, prov = self.lane_double(lanes)
        self.put(
            st,
            self.cs.reg_name(ops[0].reg),
            (
                V(_to_int(d, ops[0].size, int), prov)
                if d is not None
                else unk("int(double)", prov)
            ),
        )

    def op_vucomisd(self, st, insn, ops, _):
        a, pa = self.lane_double(self.vget(st, ops[0].reg))
        src = ops[1]
        b, pb = self.lane_double(
            self.vget(st, src.reg)
            if src.type == X.X86_OP_REG
            else self.vload(st, insn, src.mem, 8)
        )
        if a is None or b is None:
            st.flags = Flags(label=("double", "double"), kind="float", prov=pa | pb)
        elif a != a or b != b:
            st.flags = Flags(zf=1, pf=1, cf=1, prov=pa | pb)
        else:
            st.flags = Flags(zf=int(a == b), cf=int(a < b), prov=pa | pb)

    op_vcomisd = op_vucomisd

    def op_vsqrtss(self, st, insn, ops, _):
        src = ops[-1]
        b = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        base = list(self.vget(st, ops[1].reg if len(ops) == 3 else ops[0].reg))
        f = self.lane_float(b)
        base[0] = (
            V(f32_bits(f**0.5), b.prov)
            if f is not None and f >= 0
            else unk(f"sqrt({name_of(b)})", b.prov)
        )
        self.vput(st, ops[0].reg, base, 16)

    def _fma(self, st, insn, ops, order, sign=1.0, nsign=1.0):
        a = self.vget(st, ops[0].reg)[0]
        b = self.vget(st, ops[1].reg)[0]
        src = ops[2]
        c = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        x, y, z = {"132": (a, c, b), "213": (b, a, c), "231": (b, c, a)}[order]
        fx, fy, fz = map(self.lane_float, (x, y, z))
        lanes = list(self.vget(st, ops[0].reg))
        if None in (fx, fy, fz):
            lanes[0] = unk(
                f"fma({name_of(x)}, {name_of(y)}, {name_of(z)})",
                x.prov | y.prov | z.prov,
            )
        else:
            lanes[0] = V(
                f32_bits(nsign * fx * fy + sign * fz), x.prov | y.prov | z.prov
            )
        self.vput(st, ops[0].reg, lanes, 16)

    def op_vfmadd132ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "132")

    def op_vfmadd213ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "213")

    def op_vfmadd231ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "231")

    def op_vfmsub132ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "132", -1.0)

    def op_vfmsub213ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "213", -1.0)

    def op_vfmsub231ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "231", -1.0)

    def op_vfnmadd132ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "132", 1.0, -1.0)

    def op_vfnmadd213ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "213", 1.0, -1.0)

    def op_vfnmadd231ss(self, st, insn, ops, _):
        self._fma(st, insn, ops, "231", 1.0, -1.0)

    def op_vcvtsi2ss(self, st, insn, ops, _):
        src = ops[-1]
        size = src.size
        value = self.read_op(st, insn, src, size)
        lanes = list(self.vget(st, ops[1].reg if len(ops) == 3 else ops[0].reg))
        if isinstance(value.val, int):
            lanes[0] = V(f32_bits(float(signed(value.val, size))), value.prov)
        else:
            lanes[0] = unk(name_of(value), value.prov)
        self.vput(st, ops[0].reg, lanes, 16)

    op_cvtsi2ss = op_vcvtsi2ss

    def op_vcvttss2si(self, st, insn, ops, _):
        src = ops[1]
        lane = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        f = self.lane_float(lane)
        value = (
            V(_to_int(f, ops[0].size, int), lane.prov)
            if f is not None
            else unk(f"int({name_of(lane)})", lane.prov)
        )
        self.put(st, self.cs.reg_name(ops[0].reg), value)

    op_cvttss2si = op_vcvttss2si

    def op_vcvttps2dq(self, st, insn, ops, _):
        lanes = self._vsrc(st, insn, ops[1], ops[0].size)
        out = []
        for lane in lanes[: ops[0].size // 4]:
            f = self.lane_float(lane)
            out.append(
                V(_to_int(f, 4, int), lane.prov)
                if f is not None
                else unk(f"int({name_of(lane)})", lane.prov)
            )
        self.vput(st, ops[0].reg, out, ops[0].size)

    def op_vcvtdq2ps(self, st, insn, ops, _):
        lanes = self._vsrc(st, insn, ops[1], ops[0].size)
        out = [
            (
                V(f32_bits(float(signed(l.val, 4))), l.prov)
                if isinstance(l.val, int)
                else unk(name_of(l), l.prov)
            )
            for l in lanes[: ops[0].size // 4]
        ]
        self.vput(st, ops[0].reg, out, ops[0].size)

    def op_vcvtss2si(self, st, insn, ops, _):
        src = ops[1]
        lane = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        f = self.lane_float(lane)
        value = (  # MXCSR default: round to nearest even, as Python's round
            V(_to_int(f, ops[0].size, round), lane.prov)
            if f is not None
            else unk(f"round({name_of(lane)})", lane.prov)
        )
        self.put(st, self.cs.reg_name(ops[0].reg), value)

    def op_vcvtss2sd(self, st, insn, ops, _):
        src = ops[-1]
        lane = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        f = self.lane_float(lane)
        lanes = list(self.vget(st, ops[1].reg if len(ops) == 3 else ops[0].reg))
        if f is None:
            lanes[0:2] = [unk(name_of(lane), lane.prov), unk(name_of(lane), lane.prov)]
        else:
            bits = struct.unpack("<Q", struct.pack("<d", f))[0]
            lanes[0:2] = [V(bits & MASK[4], lane.prov), V(bits >> 32, lane.prov)]
        self.vput(st, ops[0].reg, lanes, 16)

    def op_vcvtsd2ss(self, st, insn, ops, _):
        src = ops[-1]
        lanes_src = (
            self.vget(st, src.reg)
            if src.type == X.X86_OP_REG
            else self.vload(st, insn, src.mem, 8)
        )
        lo, hi = lanes_src[0], lanes_src[1]
        lanes = list(self.vget(st, ops[1].reg if len(ops) == 3 else ops[0].reg))
        if isinstance(lo.val, int) and isinstance(hi.val, int):
            d = struct.unpack("<d", struct.pack("<Q", lo.val | hi.val << 32))[0]
            lanes[0] = V(f32_bits(d), lo.prov | hi.prov)
        else:
            lanes[0] = unk("double", lo.prov)
        self.vput(st, ops[0].reg, lanes, 16)

    def op_vucomiss(self, st, insn, ops, _):
        a = self.vget(st, ops[0].reg)[0]
        src = ops[1]
        b = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        fa, fb = self.lane_float(a), self.lane_float(b)
        if fa is None or fb is None:
            st.flags = Flags(
                label=(
                    name_of(a) if fa is None else repr(fa),
                    name_of(b) if fb is None else repr(fb),
                ),
                kind="float",
                prov=a.prov | b.prov,
            )
            return
        if fa != fa or fb != fb:
            st.flags = Flags(zf=1, pf=1, cf=1, prov=a.prov | b.prov)
        else:
            st.flags = Flags(zf=int(fa == fb), cf=int(fa < fb), prov=a.prov | b.prov)

    op_vcomiss = op_ucomiss = op_comiss = op_vucomiss

    def op_vbroadcastss(self, st, insn, ops, _):
        src = ops[1]
        lane = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        self.vput(st, ops[0].reg, [lane] * 8, ops[0].size)

    def op_vshufps(self, st, insn, ops, _):
        a, b = self.vget(st, ops[1].reg), self._vsrc(st, insn, ops[2], 16)
        imm = ops[3].imm
        lanes = [a[imm & 3], a[(imm >> 2) & 3], b[(imm >> 4) & 3], b[(imm >> 6) & 3]]
        self.vput(st, ops[0].reg, lanes, 16)

    def op_vinsertps(self, st, insn, ops, _):
        a = list(self.vget(st, ops[1].reg))
        imm = ops[3].imm
        src = ops[2]
        value = (
            self.vget(st, src.reg)[(imm >> 6) & 3]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        a[(imm >> 4) & 3] = value
        for index in range(4):
            if imm >> index & 1:
                a[index] = V(0)
        self.vput(st, ops[0].reg, a, 16)

    def op_vpinsrd(self, st, insn, ops, _):
        a = list(self.vget(st, ops[1].reg))
        a[ops[3].imm & 3] = self.read_op(st, insn, ops[2], 4)
        self.vput(st, ops[0].reg, a, 16)

    def op_vunpcklps(self, st, insn, ops, _):
        a, b = self.vget(st, ops[1].reg), self._vsrc(st, insn, ops[2], 16)
        self.vput(st, ops[0].reg, [a[0], b[0], a[1], b[1]], 16)

    def op_vmovshdup(self, st, insn, ops, _):
        a = self._vsrc(st, insn, ops[1], 16)
        self.vput(st, ops[0].reg, [a[1], a[1], a[3], a[3]], 16)

    def op_vpermilps(self, st, insn, ops, _):
        a = self._vsrc(st, insn, ops[1], 16)
        imm = ops[2].imm
        self.vput(st, ops[0].reg, [a[(imm >> (2 * i)) & 3] for i in range(4)], 16)

    def op_vextractps(self, st, insn, ops, _):
        lane = self.vget(st, ops[1].reg)[ops[2].imm & 3]
        self.write_op(st, insn, ops[0], lane, 4)

    def op_vroundss(self, st, insn, ops, _):
        src = ops[2]
        lane = (
            self.vget(st, src.reg)[0]
            if src.type == X.X86_OP_REG
            else self.load(st, insn, src.mem, 4)
        )
        f = self.lane_float(lane)
        mode = 0 if ops[3].imm & 4 else ops[3].imm & 3
        lanes = list(self.vget(st, ops[1].reg))
        if f is None:
            lanes[0] = unk(f"round({name_of(lane)})", lane.prov)
        elif not math.isfinite(f):
            lanes[0] = lane
        else:
            lanes[0] = V(
                f32_bits(float([round, math.floor, math.ceil, math.trunc][mode](f))),
                lane.prov,
            )
        self.vput(st, ops[0].reg, lanes, 16)


class _Mem:
    """Memory operand with an extra displacement (for lane-wise vector access)."""

    def __init__(self, mem, extra):
        self.base, self.index, self.scale, self.segment = (
            mem.base,
            mem.index,
            mem.scale,
            getattr(mem, "segment", 0),
        )
        self.disp = mem.disp + extra

    @staticmethod
    def at_rsp():
        m = _Mem.__new__(_Mem)
        m.base, m.index, m.scale, m.segment, m.disp = X.X86_REG_RSP, 0, 1, 0, 0
        return m


def _divide(x, y):
    """IEEE division: x / 0 is a signed infinity, 0 / 0 is NaN."""
    if y:
        return x / y
    if x == 0 or x != x:
        return float("nan")
    return math.copysign(float("inf"), x) * math.copysign(1.0, y)


def _to_int(f, size, rounding):
    """cvt(t)ss2si result: NaN, infinity and out-of-range give the integer indefinite."""
    indefinite = 1 << (8 * size - 1)
    if not math.isfinite(f):
        return indefinite
    value = rounding(f)
    if not -indefinite <= value < indefinite:
        return indefinite
    return value & MASK[size]


def _bytes_mask(count):
    """Mask of count bytes; merged overlay entries need not be 1, 2, 4 or 8 wide."""
    return (1 << 8 * count) - 1


def _overlapping(writes, region, off, size):
    return [
        key
        for key, (_, start, width, _) in writes.items()
        if key[0] == region and start < off + size and off < start + width
    ]


def _overlay_write(writes, region, obj, off, size, value):
    """Record a write; a partial overlap with an earlier write is merged by bytes."""
    keys = _overlapping(writes, region, off, size)
    partial = [
        k
        for k in keys
        if not (off <= writes[k][1] and writes[k][1] + writes[k][2] <= off + size)
    ]
    for key in keys:
        if key not in partial:
            del writes[key]
    if not partial:
        writes[(region, off)] = (obj, off, size, value)
        return
    # The union is contiguous: every merged entry overlaps the new write.
    start = min([off] + [writes[k][1] for k in partial])
    end = max([off + size] + [writes[k][1] + writes[k][2] for k in partial])
    pieces = [writes.pop(k) for k in partial] + [(obj, off, size, value)]
    merged, prov = 0, frozenset()
    for _, at, width, piece in pieces:  # older first, the new write last
        if not isinstance(piece.val, int):
            raise Unsupported("不同宽度的重叠写入涉及非整数值")
        shift = 8 * (at - start)
        merged = (
            merged & ~(_bytes_mask(width) << shift)
            | (piece.val & _bytes_mask(width)) << shift
        )
        prov |= piece.prov
    writes[(region, start)] = (obj, start, end - start, V(merged, prov))


def _overlay_read(writes, region, off, size, original):
    """Read through this path's writes, combining bytes when widths differ."""
    keys = _overlapping(writes, region, off, size)
    if not keys:
        return original()
    if len(keys) == 1 and writes[keys[0]][1:3] == (off, size):
        return writes[keys[0]][3]
    covered = sum(
        min(off + size, at + width) - max(off, at)
        for _, at, width, _ in (writes[k] for k in keys)
    )
    if covered < size:
        base = original()
        if not isinstance(base.val, int):
            raise Unsupported("部分覆盖的读取，未写入部分不是整数")
        result, prov = base.val & _bytes_mask(size), base.prov
    else:
        result, prov = 0, frozenset()
    for key in keys:
        _, at, width, piece = writes[key]
        if not isinstance(piece.val, int):
            raise Unsupported("不同宽度的读取涉及非整数写入值")
        lo, hi = max(off, at), min(off + size, at + width)
        part = (piece.val >> 8 * (lo - at)) & _bytes_mask(hi - lo)
        shift = 8 * (lo - off)
        result = result & ~(_bytes_mask(hi - lo) << shift) | part << shift
        prov |= piece.prov
    return V(result, prov)


def unknown_lanes(name):
    """Eight 32-bit lanes of a SIMD register whose contents are not known."""
    return [unk(f"{name}[{lane}]") for lane in range(8)]


# setcc / cmovcc dispatch by mnemonic suffix.
for _cc in CONDITIONS:
    setattr(
        Emulator,
        f"op_set{_cc}",
        lambda self, st, insn, ops, worklist, cc=_cc: self.op_setcc(
            st, insn, cc, worklist
        ),
    )
    setattr(
        Emulator,
        f"op_cmov{_cc}",
        lambda self, st, insn, ops, worklist, cc=_cc: self.op_cmovcc(
            st, insn, cc, worklist
        ),
    )
