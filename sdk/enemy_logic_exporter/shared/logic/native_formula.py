"""Recover field formulas from the x64 code of a command and the helpers it calls.

The pseudo-C recognizer (``formula.py``) stops at any call. This one executes
the command's ``onExecute`` instructions symbolically, starting from the real
argument registers (rcx thread, rdx command, r8 work, r9 argument), and
follows direct calls into the callee's own instructions. A getter or predicate
helper is therefore expanded with the registers it actually receives instead
of being trusted by name or wrapped as an opaque boolean.

Accepted: register and stack moves, typed loads, ``lea``, constant pointer
arithmetic, comparisons (integer and ``ucomiss``/``comiss``), conditional
jumps, ``setcc``/``cmovcc`` (forked like jumps), direct calls and tail jumps,
the stack-cookie check, the runtime class-hierarchy test, and a call followed
by ``int3`` (a throw that does not return; that path returns false, as in the
pseudo-C recognizer). Every path condition is kept.

Rejected (the command stays unknown): any store outside the stack, indirect
calls or jumps, loops, variable indexes, ``gs`` reads, unordered float checks
(``jp``), bit tests and any other instruction. Values are the same symbolic
tuples as ``formula.py`` so its metadata naming is reused; loads wider than a
field are split back into the fields they cover, and a runtime global compared
with a field is accepted only when a straight-line ``.cctor`` of the field's
value type stores that constant there.
"""

import re
import struct

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG

from ..config import (
    EXISTS_SUFFIX,
    FN_CLASS_HIERARCHY_CHECK,
    FN_STACK_COOKIE_CHECK,
    RUNTIME_DATA_START,
)
from ..native.evidence import evidence
from .formula import (
    Namer,
    Unsupported,
    _expression,
    _reads_state,
    b_join,
    b_not,
)

MAX_STEPS = 20000
MAX_CALL_DEPTH = 4
MAX_FUNCTION_BYTES = 0x1000
# Volatile argument registers on entry to onExecute(thread, command, work, argument).
ENTRY_REGISTERS = dict(rcx="param_1", rdx="param_2", r8="param_3", r9="param_4")
# Value sizes of primitive field types; enums use their value__ type.
FIELD_SIZES = {
    "System.Boolean": 1,
    "System.Byte": 1,
    "System.SByte": 1,
    "System.Int16": 2,
    "System.UInt16": 2,
    "System.Char": 2,
    "System.Int32": 4,
    "System.UInt32": 4,
    "System.Single": 4,
    "System.Int64": 8,
    "System.UInt64": 8,
    "System.Double": 8,
    "System.IntPtr": 8,
    "System.UIntPtr": 8,
}
# Static fields share offsets with instance fields in the dump; they are UPPER_SNAKE.
STATIC_NAME = re.compile(r"[A-Z][A-Z0-9_]*")

REGISTERS = {}
for _wide, _names in {
    "rax": ("eax", "ax", "al"),
    "rbx": ("ebx", "bx", "bl"),
    "rcx": ("ecx", "cx", "cl"),
    "rdx": ("edx", "dx", "dl"),
    "rsi": ("esi", "si", "sil"),
    "rdi": ("edi", "di", "dil"),
    "rbp": ("ebp", "bp", "bpl"),
    "rsp": ("esp", "sp", "spl"),
    **{f"r{n}": (f"r{n}d", f"r{n}w", f"r{n}b") for n in range(8, 16)},
}.items():
    REGISTERS[_wide] = (_wide, 64)
    for _name, _bits in zip(_names, (32, 16, 8)):
        REGISTERS[_name] = (_wide, _bits)
for _high in ("ah", "bh", "ch", "dh"):
    REGISTERS[_high] = ("r" + _high[0] + "x", -8)

# Condition codes after "cmp a, b" (signed and unsigned spellings).
SIGNED = {"e": "==", "z": "==", "ne": "!=", "nz": "!=", "l": "<", "nge": "<"}
SIGNED.update({"le": "<=", "ng": "<=", "g": ">", "nle": ">", "ge": ">=", "nl": ">="})
UNSIGNED = {"b": "<", "c": "<", "nae": "<", "be": "<=", "na": "<="}
UNSIGNED.update({"a": ">", "nbe": ">", "ae": ">=", "nb": ">=", "nc": ">="})
CONDITION_PREFIXES = ("j", "set", "cmov")
VEX_ALIASES = (
    "movss",
    "movsd",
    "movaps",
    "movups",
    "movd",
    "movq",
    "ucomiss",
    "comiss",
)
VEX_ALIASES += ("ucomisd", "comisd", "xorps", "pxor", "cvtss2sd", "cvtsd2ss")


def _const(value):
    return ("const", value)


def _is_bool(sym):
    return sym[0] in ("cmp", "and", "or", "not", "isa", "bool_bit") or (
        sym[0] == "const" and type(sym[1]) is bool
    )


def _narrow(sym, bits):
    """The low ``bits`` of a value, or an opaque value."""
    if bits >= 64:
        return sym
    kind = sym[0]
    if kind == "const":
        if type(sym[1]) is bool:
            return sym
        if type(sym[1]) is int:
            return _const(sym[1] & ((1 << bits) - 1))
        return ("opaque",)
    if kind == "load":
        size = sym[1]
        return sym if size * 8 <= bits else ("load", bits // 8, sym[2], sym[3])
    if _is_bool(sym):
        return sym
    if kind == "low8":
        return sym[2] if bits == 8 else ("opaque",)
    return ("opaque",)


def _offset(sym, delta):
    kind = sym[0]
    if kind in ("stack", "gaddr"):
        return (kind, sym[1] + delta)
    if kind == "addr":
        return ("addr", sym[1], sym[2] + delta)
    if kind in ("param", "load", "global"):
        return ("addr", sym, delta) if delta else sym
    if sym == ("const", 0):
        raise NullAccess("空对象访问")
    raise Unsupported("无法作为地址的值：" + kind)


class Fatal(Unsupported):
    """The whole command leaves the subset, even for a partial formula."""


class NullAccess(Unsupported):
    """A path that reads through a null pointer (a runtime exception)."""


# Result of a path that reads through null: the exception's effect on the
# command result is not verified, so the path stays unknown.
NULL_PATH = ("unknown", "原生代码在此路径访问空对象（运行时异常），结果未核实")


def _fold(test):
    """A comparison of two constants is decided."""
    if test[0] == "cmp" and test[2][0] == "const" and test[3][0] == "const":
        a, b = test[2][1], test[3][1]
        return _const(
            {
                "==": a == b,
                "!=": a != b,
                "<": a < b,
                "<=": a <= b,
                ">": a > b,
                ">=": a >= b,
            }[test[1]]
        )
    if test[0] in ("and", "or"):
        return b_join(test[0], tuple(_fold(x) for x in test[1]))
    if test[0] == "not":
        inner = _fold(test[1])
        return b_not(inner)
    return test


def _mask_zero(value, mask):
    """``value & mask == 0`` for the masks that test signs or a Boolean field.

    Accepted: the sign bit of a whole load, the sign bits of the two Int32
    halves of an 8-byte load (a packed index pair), and bit 0 of a byte load,
    which naming accepts only for a System.Boolean field.
    """
    if mask[0] != "const" or value[0] != "load" or type(mask[1]) is not int:
        raise Unsupported("位测试")
    size, bits = value[1], mask[1]
    if bits == 1 << (size * 8 - 1):
        return ("cmp", ">=", value, _const(0))
    if size == 8 and bits == 0x8000000080000000:
        low = ("load", 4, value[2], value[3])
        high = ("load", 4, value[2], value[3] + 4)
        return ("and", (("cmp", ">=", low, _const(0)), ("cmp", ">=", high, _const(0))))
    if size == 1 and bits == 1:
        return ("not", ("bool_bit", value))
    raise Unsupported("位测试")


def _truth(sym):
    if _is_bool(sym):
        return sym if sym[0] != "const" else _const(bool(sym[1]))
    if sym[0] == "const":
        return _const(bool(sym[1]))
    if sym[0] in ("load", "param", "global", "addr"):
        return ("cmp", "!=", sym, _const(0))
    raise Unsupported("返回值不是可识别的布尔值")


class State:
    __slots__ = ("regs", "xmm", "stack", "flags", "calls", "visits", "facts")

    def __init__(self):
        self.regs, self.xmm, self.stack = {}, {}, {}
        self.flags = None
        self.calls = ()
        self.visits = {}
        self.facts = frozenset()

    def copy(self):
        other = State()
        other.regs, other.xmm, other.stack = (
            dict(self.regs),
            dict(self.xmm),
            dict(self.stack),
        )
        other.flags, other.calls = self.flags, self.calls
        other.visits, other.facts = dict(self.visits), self.facts
        return other


class Executor:
    """Symbolic execution of one command body and the helpers it calls."""

    def __init__(self, pe, partial=False):
        self.pe = pe
        self.partial = partial
        self.unknown_paths = set()
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True
        self.steps = 0
        self.functions = {}
        self.decoded = {}

    def _read_only(self, address, size):
        # Runtime-initialized data has no value in the image even if read-only.
        return address < RUNTIME_DATA_START and self.pe.read_only(address, size)

    def instruction(self, address):
        if address not in self.decoded:
            start = address
            end = self.pe.end(address)
            if not 0 < end - start <= MAX_FUNCTION_BYTES * 4:
                end = start + 16
            code = self.pe.read(start, min(end - start, 16))
            found = next(self.md.disasm(code, start, 1), None)
            if found is None:
                raise Fatal(f"无法解码 {address:#x}")
            self.decoded[address] = found
        return self.decoded[address]

    def function(self, address):
        """Record the callee range as evidence."""
        if address not in self.functions:
            end = self.pe.end(address)
            if not 0 < end - address <= MAX_FUNCTION_BYTES:
                raise Unsupported(f"被调函数过大或边界未知：{address:#x}")
            self.functions[address] = end
        return self.functions[address]

    # ---------------------------------------------------------- operands

    def address(self, ins, op, state):
        mem = op.mem
        if mem.segment:
            raise Unsupported("段寄存器寻址")
        if mem.index:
            index = self.reg(state, ins.reg_name(mem.index))
            if index[0] != "const" or type(index[1]) is not int:
                raise Unsupported("变量索引")
            displacement = mem.disp + index[1] * mem.scale
        else:
            displacement = mem.disp
        if not mem.base:
            raise Unsupported("绝对地址")
        base = ins.reg_name(mem.base)
        if base == "rip":
            return ("gaddr", ins.address + ins.size + displacement)
        return _offset(self.reg(state, base), displacement)

    def load(self, address, size, state, floating=False):
        kind = address[0]
        if kind == "stack":
            stored = state.stack.get(address[1])
            if stored is None:
                return ("opaque",)
            stored_size, value = stored
            if stored_size == size:
                return value
            if stored_size > size and not floating:
                return _narrow(value, size * 8)
            return ("opaque",)
        if kind == "gaddr":
            where = address[1]
            if self._read_only(where, size):
                raw = self.pe.read(where, size)
                if len(raw) != size:
                    raise Unsupported("常量读取失败")
                if floating:
                    return _const(struct.unpack("<f" if size == 4 else "<d", raw)[0])
                return _const(int.from_bytes(raw, "little"))
            return ("global", f"_DAT_{where:x}", size)
        if kind == "addr":
            return ("load", size, address[1], address[2])
        return ("load", size, address, 0)

    def store(self, address, size, value, state):
        if address[0] != "stack":
            raise Fatal("写入栈以外的内存")
        state.stack[address[1]] = (size, value)

    def reg(self, state, name, bits=None):
        if name.startswith("xmm"):
            return state.xmm.get(name, ("opaque",))
        if name not in REGISTERS:
            raise Unsupported("寄存器 " + name)
        wide, width = REGISTERS[name]
        value = state.regs.get(wide, ("opaque",))
        if width < 0:
            return ("opaque",)
        return _narrow(value, bits or width)

    def set_reg(self, state, name, value):
        if name.startswith("xmm"):
            state.xmm[name] = value
            return
        if name not in REGISTERS:
            raise Unsupported("寄存器 " + name)
        wide, width = REGISTERS[name]
        if width == 64:
            state.regs[wide] = value
        elif width == 32:
            state.regs[wide] = _narrow(value, 32)
        elif width == 8:
            state.regs[wide] = ("low8", state.regs.get(wide, ("opaque",)), value)
        else:
            state.regs[wide] = ("opaque",)

    def read(self, ins, op, state, floating=False):
        if op.type == X86_OP_REG:
            return self.reg(state, ins.reg_name(op.reg))
        if op.type == X86_OP_IMM:
            return _const(op.imm & ((1 << (op.size * 8)) - 1))
        if op.type == X86_OP_MEM:
            return self.load(self.address(ins, op, state), op.size, state, floating)
        raise Unsupported("操作数")

    def write(self, ins, op, value, state):
        if op.type == X86_OP_REG:
            self.set_reg(state, ins.reg_name(op.reg), value)
        elif op.type == X86_OP_MEM:
            self.store(self.address(ins, op, state), op.size, value, state)
        else:
            raise Unsupported("写入目标")

    # -------------------------------------------------------- conditions

    @staticmethod
    def condition(flags, code):
        if flags is None:
            raise Unsupported("条件码没有来源")
        kind = flags[0]
        if kind == "test":
            a, b = flags[1], flags[2]
            if a != b:
                if b[0] == "const" and _is_bool(a) and b[1] & 1:
                    b = a
                elif a[0] == "const" and _is_bool(b) and a[1] & 1:
                    a = b
                else:
                    if a[0] == "const":
                        a, b = b, a
                    zero = _mask_zero(a, b)
                    if code in ("e", "z"):
                        return zero
                    if code in ("ne", "nz"):
                        return b_not(zero)
                    raise Unsupported("位测试的条件码 " + code)
            zero = ("cmp", "==", a, _const(0)) if not _is_bool(a) else b_not(a)
            if code in ("e", "z"):
                return zero
            if code in ("ne", "nz"):
                return b_not(zero)
            if _is_bool(a):
                raise Unsupported("布尔值的符号测试")
            signs = {"s": "<", "ns": ">=", "le": "<=", "ng": "<=", "g": ">", "nle": ">"}
            if code in signs:
                return ("cmp", signs[code], a, _const(0))
            raise Unsupported("条件码 " + code)
        if kind == "cmp":
            a, b, bits = flags[1], flags[2], flags[3]
            if code in SIGNED:
                if b[0] == "const" and type(b[1]) is int and b[1] >> (bits - 1):
                    b = _const(b[1] - (1 << bits))
                return ("cmp", SIGNED[code], a, b)
            if code in UNSIGNED:
                if b[0] != "const" or type(b[1]) is not int or b[1] >> (bits - 1):
                    raise Unsupported("无符号比较")
                test = ("cmp", UNSIGNED[code], a, b)
                negative = ("cmp", "<", a, _const(0))
                if UNSIGNED[code] in (">", ">="):
                    return b_join("or", (test, negative))
                return b_join("and", (b_not(negative), test))
            raise Unsupported("条件码 " + code)
        if kind == "fcmp":
            ordered = {"a": ">", "nbe": ">", "ae": ">=", "nb": ">=", "nc": ">="}
            ordered.update({"b": "<", "c": "<", "nae": "<", "be": "<=", "na": "<="})
            if code in ordered:
                return ("cmp", ordered[code], flags[1], flags[2])
            raise Unsupported("浮点相等或无序判断")
        raise Unsupported("条件码来源")

    # --------------------------------------------------------- execution

    def run(self, address, state):
        """Formula that the outermost function returns true from here.

        In partial mode a path that leaves the recognised subset (a variable
        index, a loop, an unsupported instruction...) ends as an explicit
        unknown from its last branch on; other paths keep their formula.
        """
        try:
            return self.trace(address, state)
        except Fatal:
            raise
        except Unsupported as error:
            if not self.partial or isinstance(error, NullAccess):
                raise
            self.unknown_paths.add(str(error))
            return (
                "unknown",
                f"原生代码在此路径超出可核实的范围（{error}），结果未核实",
            )

    def trace(self, address, state):
        while True:
            self.steps += 1
            if self.steps > MAX_STEPS:
                raise Fatal("路径过多")
            key = (address, state.calls)
            state.visits[key] = state.visits.get(key, 0) + 1
            if state.visits[key] > 1:
                raise Unsupported("循环")
            ins = self.instruction(address)
            following = ins.address + ins.size
            mnemonic, ops = ins.mnemonic, ins.operands
            for prefix in CONDITION_PREFIXES:
                code = mnemonic[len(prefix) :]
                if mnemonic.startswith(prefix) and (
                    code in SIGNED or code in UNSIGNED or code in ("s", "ns", "p", "np")
                ):
                    if code in ("p", "np"):
                        raise Unsupported("无序浮点判断")
                    test = _fold(self.condition(state.flags, code))
                    return self.fork(ins, prefix, test, state, following)
            if mnemonic in ("nop", "endbr64") or mnemonic.startswith("nop"):
                address = following
                continue
            if mnemonic == "ret":
                if not state.calls:
                    return _truth(self.reg(state, "al"))
                target = self.load(self.reg(state, "rsp"), 8, state)
                if target != ("retaddr", state.calls[-1]):
                    raise Fatal("返回地址不平衡")
                state.regs["rsp"] = _offset(
                    self.reg(state, "rsp"), 8 + (ops[0].imm if ops else 0)
                )
                address, state.calls = state.calls[-1], state.calls[:-1]
                continue
            if mnemonic == "call" or (mnemonic == "jmp" and ops[0].type == X86_OP_IMM):
                if ops[0].type != X86_OP_IMM:
                    raise Unsupported("间接调用或跳转")
                target = ops[0].imm
                if mnemonic == "jmp":
                    address = target
                    continue
                result = self.call(ins, target, state, following)
                if result is not None:
                    return result
                address = following
                if target not in (FN_STACK_COOKIE_CHECK, FN_CLASS_HIERARCHY_CHECK):
                    address = target
                continue
            if mnemonic == "jmp":
                raise Unsupported("间接跳转")
            try:
                self.step(ins, state)
            except NullAccess:
                return NULL_PATH
            address = following

    def fork(self, ins, prefix, test, state, following):
        def go(taken):
            branch = state.copy()
            facts = branch.facts | {test if taken else b_not(test)}
            branch.facts = frozenset(facts)
            if prefix == "j":
                return self.run(ins.operands[0].imm if taken else following, branch)
            if prefix == "set":
                self.write(ins, ins.operands[0], _const(1 if taken else 0), branch)
            elif taken:
                self.set_reg(
                    branch,
                    ins.reg_name(ins.operands[0].reg),
                    self.read(ins, ins.operands[1], branch),
                )
            elif ins.operands[0].size == 4:
                # A 32-bit cmov zero-extends its destination even when not taken.
                name = ins.reg_name(ins.operands[0].reg)
                self.set_reg(branch, name, self.reg(branch, name))
            return self.run(following, branch)

        if prefix == "set" and test[0] != "const":
            # The flag value itself, without forking.
            self.write(ins, ins.operands[0], test, state)
            return self.run(following, state)
        if test in state.facts or test == ("const", True):
            return go(True)
        if b_not(test) in state.facts or test == ("const", False):
            return go(False)
        then, otherwise = go(True), go(False)
        if then == otherwise:
            return then
        return b_join(
            "or", (b_join("and", (test, then)), b_join("and", (b_not(test), otherwise)))
        )

    def throws(self, address):
        """The call at hand starts a straight run of calls ending in ``int3``.

        Exceptions are built by one helper and raised by the next, as in
        ``e = create(thread, klass, 0); raise(thread, e); int3``.
        """
        for _ in range(8):
            ins = self.instruction(address)
            if ins.mnemonic == "int3":
                return True
            if ins.mnemonic not in ("mov", "lea", "call", "xor"):
                return False
            address = ins.address + ins.size
        return False

    def call(self, ins, target, state, following):
        """Handle a direct call; returns a formula when the path ends here."""
        if target == FN_STACK_COOKIE_CHECK:
            return None
        if target == FN_CLASS_HIERARCHY_CHECK:
            klass, base = self.reg(state, "rcx"), self.reg(state, "rdx")
            state.regs["rax"] = ("isa", klass, base)
            for name in ("rcx", "rdx", "r8", "r9", "r10", "r11"):
                state.regs[name] = ("opaque",)
            state.flags = None
            return None
        if self.throws(following):
            # A throw sequence; the path does not return (pseudo-C: swi(3)).
            return _const(False)
        if len(state.calls) >= MAX_CALL_DEPTH:
            raise Unsupported("调用层数过深")
        self.function(target)
        rsp = _offset(self.reg(state, "rsp"), -8)
        state.regs["rsp"] = rsp
        state.stack[rsp[1]] = (8, ("retaddr", following))
        state.calls = state.calls + (following,)
        return None

    def step(self, ins, state):
        mnemonic, ops = ins.mnemonic, ins.operands
        if mnemonic.startswith("v") and mnemonic[1:] in VEX_ALIASES:
            # VEX forms; the three-operand xor and moves keep their meaning.
            if len(ops) == 3 and mnemonic[1:] in ("xorps", "pxor"):
                if not ops[1].reg == ops[2].reg:
                    raise Unsupported("指令 " + mnemonic)
                self.write(ins, ops[0], _const(0.0), state)
                return
            if len(ops) != 2:
                raise Unsupported("指令 " + mnemonic)
            mnemonic = mnemonic[1:]
        if mnemonic in ("mov", "movabs"):
            self.write(ins, ops[0], self.read(ins, ops[1], state), state)
        elif mnemonic in ("movzx", "movsx", "movsxd"):
            value = self.read(ins, ops[1], state)
            if mnemonic != "movzx" and value[0] == "const":
                bits = ops[1].size * 8
                if value[1] >> (bits - 1):
                    value = _const(value[1] - (1 << bits))
            self.write(ins, ops[0], value, state)
        elif mnemonic in ("movss", "movsd", "movaps", "movups", "movd", "movq"):
            floating = mnemonic in ("movss", "movsd")
            if ops[1].type == X86_OP_MEM:
                value = self.load(
                    self.address(ins, ops[1], state), ops[1].size, state, floating
                )
            else:
                value = self.read(ins, ops[1], state)
            self.write(ins, ops[0], value, state)
        elif mnemonic in ("cvtss2sd", "cvtsd2ss"):
            self.write(ins, ops[0], self.read(ins, ops[1], state, True), state)
        elif mnemonic == "lea":
            self.write(ins, ops[0], self.address(ins, ops[1], state), state)
        elif mnemonic == "push":
            rsp = _offset(self.reg(state, "rsp"), -8)
            state.regs["rsp"] = rsp
            self.store(rsp, 8, self.read(ins, ops[0], state), state)
        elif mnemonic == "pop":
            rsp = self.reg(state, "rsp")
            self.write(ins, ops[0], self.load(rsp, 8, state), state)
            state.regs["rsp"] = _offset(rsp, 8)
        elif mnemonic in ("add", "sub"):
            a, b = self.read(ins, ops[0], state), self.read(ins, ops[1], state)
            bits = ops[0].size * 8
            if mnemonic == "sub":
                state.flags = ("cmp", a, b, bits)
            else:
                state.flags = None
            if b[0] == "const" and type(b[1]) is int:
                delta = b[1] - (1 << bits) if b[1] >> (bits - 1) else b[1]
                delta = -delta if mnemonic == "sub" else delta
                if a[0] == "const" and type(a[1]) is int:
                    value = _const((a[1] + delta) & ((1 << bits) - 1))
                elif bits == 64:
                    value = _offset(a, delta)
                else:
                    value = ("opaque",)
            else:
                value = ("opaque",)
            self.write(ins, ops[0], value, state)
        elif mnemonic in ("cmp", "test"):
            a, b = self.read(ins, ops[0], state), self.read(ins, ops[1], state)
            state.flags = (mnemonic, a, b, ops[0].size * 8)
        elif mnemonic in ("ucomiss", "comiss", "ucomisd", "comisd"):
            a = self.read(ins, ops[0], state, True)
            b = self.read(ins, ops[1], state, True)
            state.flags = ("fcmp", a, b)
        elif (
            mnemonic in ("xor", "xorps", "pxor")
            and ops[0].type == ops[1].type == X86_OP_REG
            and ops[0].reg == ops[1].reg
        ):
            zero = _const(0) if mnemonic == "xor" else _const(0.0)
            self.write(ins, ops[0], zero, state)
            state.flags = ("test", zero, zero, ops[0].size * 8)
        elif mnemonic in ("and", "or", "xor"):
            a, b = self.read(ins, ops[0], state), self.read(ins, ops[1], state)
            value = ("opaque",)
            if a[0] == b[0] == "const" and type(a[1]) is int and type(b[1]) is int:
                value = _const(
                    {"and": a[1] & b[1], "or": a[1] | b[1], "xor": a[1] ^ b[1]}[
                        mnemonic
                    ]
                )
            elif mnemonic == "and" and b[0] == "const" and b[1] == 1 and _is_bool(a):
                value = a
            elif mnemonic in ("and", "or") and _is_bool(a) and _is_bool(b):
                value = b_join(mnemonic, (_truth(a), _truth(b)))
            elif (
                mnemonic == "and"
                and b[0] == "const"
                and a[0] == "load"
                and b[1] == (1 << (a[1] * 8)) - 1
            ):
                value = a
            self.write(ins, ops[0], value, state)
            state.flags = ("test", value, value, ops[0].size * 8)
        elif mnemonic in ("shr", "sar"):
            a, b = self.read(ins, ops[0], state), self.read(ins, ops[1], state)
            value = ("opaque",)
            if (
                a[0] == "load"
                and b[0] == "const"
                and b[1] % 8 == 0
                and b[1] // 8 < a[1]
            ):
                value = ("load", a[1] - b[1] // 8, a[2], a[3] + b[1] // 8)
            self.write(ins, ops[0], value, state)
            state.flags = None
        elif mnemonic in (
            "shl",
            "imul",
            "inc",
            "dec",
            "neg",
            "not",
            "bsr",
            "bsf",
            "sbb",
            "adc",
        ):
            self.write(ins, ops[0], ("opaque",), state)
            state.flags = None
        elif mnemonic in ("cdqe", "cwde", "cdq", "cqo"):
            state.regs["rdx"] = (
                ("opaque",)
                if mnemonic in ("cdq", "cqo")
                else state.regs.get("rdx", ("opaque",))
            )
        else:
            raise Unsupported("指令 " + mnemonic)


def evaluate(pe, address, partial=False):
    """The formula over symbolic loads that the command at ``address`` returns.

    The third value lists why paths ended unknown (partial mode only).
    """
    executor = Executor(pe, partial)
    state = State()
    for register, name in ENTRY_REGISTERS.items():
        state.regs[register] = ("param", name)
    state.regs["rsp"] = ("stack", 0)
    state.stack[0] = (8, ("retaddr", None))
    formula = executor.run(address, state)
    return formula, executor.functions, sorted(executor.unknown_paths)


# ------------------------------------------------------------- semantics


class NativeNamer(Namer):
    """Formula naming where a load at a struct field reads its first member.

    Machine code reads the members of a value-type field one by one; the
    pseudo-C recognizer never sees such reads, so only this namer descends.
    """

    def field(self, owner, offset):
        found = super().field(owner, offset)
        seen = set()
        while found is not None and found[1] not in seen:
            seen.add(found[1])
            record = self.metadata.get(found[1]) or {}
            if (
                (
                    found[1].startswith("System.")
                    and not found[1].startswith("System.Nullable")
                )
                or record.get("parent") != "System.ValueType"
                or self.metadata.enum(found[1])[0]
            ):
                break
            inner = super().field(found[1], 0x10)
            if inner is None or STATIC_NAME.fullmatch(inner[0][-1]):
                break
            found = (found[0] + inner[0], inner[1])
        return found

    def argument_field(self, offset):
        """Like Namer.argument_field, but keeps every field at the offset.

        Argument types can declare a static default next to the edited field
        at the same offset (``_EditType`` and ``_EditTypeDefault``); the
        candidates are joined with "|" and ``instantiate`` keeps the one the
        resource argument actually serializes.
        """
        argument_type = (self.row.get("parameters") or [{}])[-1].get("type")
        if not argument_type or len(self.row.get("parameters") or []) < 2:
            return None
        names = [
            k
            for k, v in self.metadata.fields(argument_type).items()
            if k != "Null"
            and v.get("offset_from_base") == hex(offset)
            and "default" not in v
        ]
        if not names:
            return None
        field = "|".join(names)
        if field not in self.argument_fields:
            self.argument_fields.append(field)
        return ("arg", field, argument_type)

    def field_size(self, type_name):
        """Bytes a field of this type occupies, "reference" for objects, or None."""
        if type_name in FIELD_SIZES:
            return FIELD_SIZES[type_name]
        record = self.metadata.get(type_name) or {}
        if record.get("parent") == "System.Enum":
            underlying = record.get("fields", {}).get("value__", {}).get("type")
            return FIELD_SIZES.get(underlying, 4 if underlying is None else None)
        if record.get("parent") == "System.ValueType" or not record:
            return None
        return "reference"

    def exists(self, sym):
        """Runtime key for a null check of an object field (not a guard)."""
        named = self.leaf(sym) if sym[0] == "load" and sym[1] == 8 else None
        if named and named[0] == "key" and self.field_size(named[2]) == "reference":
            return named[1] + EXISTS_SUFFIX
        return None

    def value_types(self, sym):
        """Value types that enclose the field read by ``sym``, innermost last."""
        if sym[0] != "load":
            return []
        parent = self.path(sym[2])
        if parent is None:
            return []
        root, owner, _ = parent
        owners = self.extends if root == "extend" and owner is None else [owner]
        for owner in owners:
            chain, offset = [], sym[3]
            while True:
                rows = [
                    (int(d.get("offset_from_base", "0x0"), 16), d["type"])
                    for n, d in self.metadata.fields(owner).items()
                    if n != "Null"
                    and "default" not in d
                    and not STATIC_NAME.fullmatch(n)
                ]
                inside = [
                    (start, kind)
                    for start, kind in rows
                    if (self.metadata.get(kind) or {}).get("parent")
                    == "System.ValueType"
                    and not self.metadata.enum(kind)[0]
                    and start
                    <= offset
                    < start
                    + int((self.metadata.get(kind) or {}).get("size", "0"), 16)
                    - 0x10
                ]
                if len(inside) != 1:
                    break
                start, owner = inside[0]
                if owner in chain:
                    break
                chain.append(owner)
                offset = offset - start + 0x10
            if chain:
                return chain
        return []


def split_wide(sym, namer):
    """Split equality tests of loads that span several fields; reject mismatches.

    Compilers compare adjacent fields with one wide read (``cmp rax, imm``
    over two Int32 fields). Equality of the bytes is the conjunction of the
    halves, so the halves are compared separately and then named. Any other
    comparison whose read is wider or narrower than the named field is
    rejected instead of being named after its first member.
    """
    kind = sym[0]
    if kind in ("and", "or"):
        return b_join(kind, tuple(split_wide(x, namer) for x in sym[1]))
    if kind == "not":
        return b_not(split_wide(sym[1], namer))
    if kind != "cmp":
        return sym
    operator, left, right = sym[1], sym[2], sym[3]
    for a, b in ((left, right), (right, left)):
        if a[0] != "load" or (a[1] == 8 and a[3] == 0 and b[0] == "global"):
            continue
        named = namer.leaf(a)
        size = named and named[0] == "key" and namer.field_size(named[2])
        if size in (a[1], "reference", None) or size is False:
            continue
        if (
            operator in ("==", "!=")
            and b[0] == "const"
            and type(b[1]) is int
            and a[1] in (2, 4, 8)
        ):
            half, value = a[1] // 2, b[1] & ((1 << (a[1] * 8)) - 1)
            parts = (
                (
                    "cmp",
                    operator,
                    ("load", half, a[2], a[3]),
                    _const(value & ((1 << (half * 8)) - 1)),
                ),
                (
                    "cmp",
                    operator,
                    ("load", half, a[2], a[3] + half),
                    _const(value >> (half * 8)),
                ),
            )
            joined = (
                "and" if operator == "==" else "or",
                tuple(split_wide(p, namer) for p in parts),
            )
            return b_join(*joined)
        raise Unsupported("读取宽度与字段不符")
    return sym


def resolve_statics(sym, namer, metadata, pe, used):
    """Replace runtime globals compared with a field by their ``.cctor`` value."""
    kind = sym[0]
    if kind in ("and", "or"):
        return (
            kind,
            tuple(resolve_statics(x, namer, metadata, pe, used) for x in sym[1]),
        )
    if kind == "not":
        return ("not", resolve_statics(sym[1], namer, metadata, pe, used))
    if kind != "cmp":
        return sym
    left, right = sym[2], sym[3]
    for a, b, swap in ((left, right, False), (right, left, True)):
        if b[0] != "global" or a[0] != "load" or (a[1] == 8 and a[3] == 0):
            continue
        address = int(b[1][len("_DAT_") :], 16)
        for type_name in reversed(namer.value_types(a)):
            found = static_constant(metadata, pe, type_name, address, a[1])
            if found is not None:
                value, source = found
                if source not in used:
                    used.append(source)
                constant = ("const", value)
                return (
                    ("cmp", sym[1], constant, a)
                    if swap
                    else ("cmp", sym[1], a, constant)
                )
    return sym


def static_constant(metadata, pe, type_name, address, size):
    """Value that a straight-line ``.cctor`` of ``type_name`` stores at ``address``."""
    record = metadata.get(type_name) or {}
    # The one runtime static of the type's own type (a sentinel such as INVALID).
    statics = [
        name
        for name, d in record.get("fields", {}).items()
        if STATIC_NAME.fullmatch(name)
        and "default" not in d
        and d.get("type") == type_name
    ]
    if len(statics) != 1:
        return None
    cctors = [
        int(m["function"], 16)
        for name, m in record.get("methods", {}).items()
        if name.startswith(".cctor") and m.get("function")
    ]
    if len(cctors) != 1:
        return None
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    start = cctors[0]
    stores = {}
    for ins in md.disasm(pe.read(start, 0x100), start):
        if ins.mnemonic == "ret":
            break
        ops = ins.operands
        if (
            ins.mnemonic != "mov"
            or len(ops) != 2
            or ops[0].type != X86_OP_MEM
            or ins.reg_name(ops[0].mem.base) != "rip"
            or ops[0].mem.index
            or ops[1].type != X86_OP_IMM
        ):
            return None
        target = ins.address + ins.size + ops[0].mem.disp
        width = ops[0].size
        value = ops[1].imm & ((1 << (width * 8)) - 1)
        for i in range(width):
            stores[target + i] = (value >> (8 * i)) & 0xFF
    else:
        return None
    if not all(address + i in stores for i in range(size)):
        return None
    return sum(stores[address + i] << (8 * i) for i in range(size)), dict(
        type=type_name,
        method=".cctor",
        address=hex(start),
        end=hex(pe.end(start)),
        field=statics[0],
    )


def recover_native_formula_leaf(row, metadata, pe, names=None, partial=False):
    """A leaf rule ``kind=formula`` from the command's x64 code and its helpers.

    With ``partial`` the formula may keep explicitly unknown paths; it is
    accepted only when its known part still reads monster state.
    """
    try:
        formula, helpers, unknown_paths = evaluate(pe, int(row["address"], 16), partial)
        namer = NativeNamer(metadata, row, ("param", "param_3"), ("param", "param_4"))
        statics = []
        formula = resolve_statics(formula, namer, metadata, pe, statics)
        formula = split_wide(formula, namer)
        expression = _expression(formula, namer)
    except Unsupported:
        return None
    if expression.get("kind") == "constant" or not _reads_state(expression):
        return None
    inlined = []
    if helpers and callable(names):
        names = names()
    for start, end in sorted(helpers.items()):
        owner = (names or {}).get(start) or [("<native>", f"sub_{start:x}")]
        inlined.append(
            dict(type=owner[0][0], method=owner[0][1], address=hex(start), end=hex(end))
        )
    argument_type = (row.get("parameters") or [{}])[-1].get("type")
    return dict(
        kind="formula",
        commandType=row["type"],
        argumentType=argument_type if namer.argument_fields else None,
        argumentField=namer.argument_fields[0] if namer.argument_fields else None,
        argumentFields=namer.argument_fields,
        contextFieldType=None,
        formula=expression,
        inputEnums=namer.enums,
        evidence=evidence(row),
        inlinedHelpers=inlined,
        staticConstants=statics,
        unknownPaths=unknown_paths,
        semanticStatus=(
            "native_x64_field_formula_partial"
            if unknown_paths
            else "native_x64_field_formula_recovered"
        ),
    )
