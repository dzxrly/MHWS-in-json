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

Also accepted: array elements at an index read from a field, field AND
constant-mask tests, comparisons between two fields, ``adc``/``sbb`` of
constants, and virtual getters whose every implementation returns a constant.

Rejected (the command stays unknown): any store outside the stack, other
indirect calls or jumps, loops, indexes that are no field, ``gs`` reads,
unordered float checks (``jp``) and any other instruction. Values are the
same symbolic tuples as ``formula.py`` so its metadata naming is reused; loads
wider than a field are split back into the fields they cover, and a runtime
global compared with a field is accepted only when a straight-line ``.cctor``
of the field's value type stores that constant there. When inlining exceeds
MAX_STEPS, ``evaluate`` reruns with paths merged at helper returns.
"""

import re
import struct

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG

from ..config import (
    CONTEXT_KEY_ALIASES,
    EDIT_FIELD_VALUE,
    EXISTS_SUFFIX,
    REFERENCE_PREFIXES,
    FN_CLASS_HIERARCHY_CHECK,
    FN_STACK_COOKIE_CHECK,
    PENDING_EXCEPTION,
    RUNTIME_DATA_START,
    THREAD_EXCEPTION_HOLDER,
    VTABLE_METHODS_OFFSET,
)
from ..native.evidence import evidence
from .expressions import expression_unknown
from .formula import (
    ARRAY_DATA,
    Namer,
    Unsupported,
    _join,
    _expression,
    _reads_state,
    b_join,
    b_not,
)

MAX_STEPS = 60000
TOO_MANY_PATHS = "路径过多"
# Enum arguments with more declared values are not forked.
MAX_ENUM_FORK = 64
# Reference lookups modelled as named roots instead of being traced: they
# index the global EnemyManager tables, which hold no static data. Identified
# by metadata (type, method without suffix, parameter types) in every build.
REFERENCE_LOOKUPS = {
    # getEnemyManageInfo(key, flag): the enemy a TARGET_ACCESS_KEY refers to,
    # or null when the key is not an enemy key or its slot was reused.
    "enemy": (
        "app.TargetAccessKeyUtil",
        "getEnemyManageInfo",
        ("app.TARGET_ACCESS_KEY", "System.Boolean"),
        "app.cEnemyManageInfo",
    ),
    # EnemyManager.findSquad(group): the squad that this Group module is in.
    "squad": (
        "app.EnemyManager",
        "findSquad",
        ("app.cEmModuleGroup",),
        "app.cEnemySquadManageInfo",
    ),
}
TARGET_ACCESS_KEY = "app.TARGET_ACCESS_KEY"
# Boolean resource arguments are forked on false/true.
BOOL_EDIT_FIELD = "ace.btable.cEditFieldBool"
MAX_CALL_DEPTH = 6
MAX_FUNCTION_BYTES = 0x1000
# Registers a callee may leave changed (Windows x64); rax and xmm0 hold results.
VOLATILE_REGISTERS = ("rcx", "rdx", "r8", "r9", "r10", "r11")
VOLATILE_XMM = ("xmm1", "xmm2", "xmm3", "xmm4", "xmm5")
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
# Values that name a field (or a field plus a constant, or a constant-returning
# virtual getter); two of them compared form a relation between fields.
FIELD_VALUES = ("load", "off", "vcall")
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
    return sym[0] in ("cmp", "and", "or", "not", "isa", "bool_bit", "bits") or (
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
        # The low byte stays known through wider moves (mov eax, r9d; ret).
        return sym[2] if bits == 8 else ("low8", _narrow(sym[1], bits), sym[2])
    if kind == "addr" and bits == 32 and sym[1][0] in ("load", "off"):
        # lea r32, [field + c]: a 32-bit field plus a constant, not a pointer.
        return _plus(sym[1], sym[2])
    if kind == "off" and bits == 32:
        return sym
    if kind == "masked" and bits >= sym[1][1] * 8:
        return sym
    if kind == "vcall" and bits >= sym[1] * 8:
        # The constant an override returns in eax/al, upper bits clear.
        return sym
    return ("opaque",)


def _sign_extend(sym, source, wide):
    """``sym`` (the low ``source`` bits) sign-extended to ``wide`` bits.

    Field reads stand for the field's own (signed) value, so they keep their
    symbol only when the read is no wider than the source bits.
    """
    if sym[0] == "const" and type(sym[1]) is int:
        value = sym[1] & ((1 << source) - 1)
        if value >> (source - 1):
            value -= 1 << source
        return _const(value & ((1 << wide) - 1))
    if (sym[0] == "load" and sym[1] * 8 <= source) or _is_bool(sym):
        return sym
    return ("opaque",)


def _to_signed(value, bits):
    return value - (1 << bits) if value >> (bits - 1) else value


def _signed64(value):
    return value - (1 << 64) if value >> 63 else value


def _wrap32(value):
    return (value + (1 << 31)) % (1 << 32) - (1 << 31)


def _plus(sym, delta):
    """A 32-bit value plus a constant (wrapping)."""
    if sym[0] == "off":
        sym, delta = sym[1], sym[2] + delta
    delta = _wrap32(delta)
    return sym if delta == 0 else ("off", sym, delta)


def _offset(sym, delta):
    kind = sym[0]
    if kind in ("stack", "gaddr"):
        return (kind, sym[1] + delta)
    if kind == "addr":
        return ("addr", sym[1], sym[2] + delta)
    if kind == "elem":
        return ("elem", sym[1], sym[2], sym[3], sym[4] + delta)
    if kind in ("param", "load", "global", "ref_enemy", "ref_squad"):
        return ("addr", sym, delta) if delta else sym
    if sym == ("const", 0):
        raise NullAccess("空对象访问")
    raise Unsupported("无法作为地址的值：" + kind)


class Fatal(Unsupported):
    """The whole command leaves the subset, even for a partial formula."""


class Concretize(Unsupported):
    """An enum resource argument is read: continue once per declared value."""

    def __init__(self, sym, values):
        super().__init__("资源参数分叉")
        self.sym, self.values = sym, values


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


# A throw inside a merged call: the command result false, kept apart from
# the callee's own false return until evaluate settles it.
HALT = ("halt",)


def _substitute(formula, leaves):
    """Replace path results (merged-call returns, HALT) by formulas.

    Path results only appear un-negated under and/or, so this is exact.
    """
    if formula[0] in ("return", "halt"):
        return leaves.get(formula, formula)
    if formula[0] in ("and", "or"):
        return b_join(formula[0], tuple(_substitute(x, leaves) for x in formula[1]))
    return formula


def _branch(test, then, otherwise):
    """``(test & then) | (!test & otherwise)``, sharing a repeated continuation.

    Merged paths reach one continuation from several branches; when
    ``otherwise`` already has a disjunct ``u & then`` (or the converse), this
    uses (t & A) | (!t & ((u & A) | R)) = ((t | u) & A) | (!t & R), so the
    continuation is written once.
    """
    for first, second, condition in (
        (then, otherwise, test),
        (otherwise, then, b_not(test)),
    ):
        if second[0] != "or" or first[0] == "const":
            continue
        wanted = first[1] if first[0] == "and" else (first,)
        for index, part in enumerate(second[1]):
            items = part[1] if part[0] == "and" else (part,)
            if part != first and not (
                part[0] == "and" and all(x in items for x in wanted)
            ):
                continue
            rest = tuple(x for x in items if x not in wanted)
            reached = b_join("or", (condition, b_join("and", rest)))
            others = b_join("or", second[1][:index] + second[1][index + 1 :])
            return b_join(
                "or",
                (
                    b_join("and", (reached, first)),
                    b_join("and", (b_not(condition), others)),
                ),
            )
    return b_join(
        "or", (b_join("and", (test, then)), b_join("and", (b_not(test), otherwise)))
    )


def _has_terminal(formula):
    """True when a path of ``formula`` ends in a throw or an unknown result."""
    if formula == HALT or formula[0] == "unknown":
        return True
    if formula[0] in ("and", "or"):
        return any(_has_terminal(x) for x in formula[1])
    return False


def _mask_zero(value, mask):
    """``value & mask == 0`` for a field read and a constant mask.

    The sign bit of a whole load, the sign bits of the two Int32 halves of an
    8-byte load (a packed index pair) and bit 0 of a byte load (naming accepts
    it only for a System.Boolean field) keep their usual meaning; any other
    mask is the atom ``("bits", load, mask)``, "the field has a bit of mask".
    """
    if mask[0] != "const" or value[0] != "load" or type(mask[1]) is not int:
        raise Unsupported("位测试")
    size, bits = value[1], mask[1] & ((1 << (value[1] * 8)) - 1)
    if bits == 1 << (size * 8 - 1):
        return ("cmp", ">=", value, _const(0))
    if size == 8 and bits == 0x8000000080000000:
        low = ("load", 4, value[2], value[3])
        high = ("load", 4, value[2], value[3] + 4)
        return ("and", (("cmp", ">=", low, _const(0)), ("cmp", ">=", high, _const(0))))
    if size == 1 and bits == 1:
        return ("not", ("bool_bit", value))
    if bits == 0:
        return _const(True)
    return b_not(("bits", value, bits))


# Most free bits a masked equality may enumerate (x & ~1 == 8: x is 8 or 9).
MAX_MASK_FREE_BITS = 3


def _masked_condition(masked, other, bits, code):
    """Conditions on ``field & mask`` against a constant (after ``and``; ``cmp``).

    Equality enumerates the field values whose free bits differ; unsigned
    ``< 1`` / ``>= 1`` (and ``<= 0`` / ``> 0``) are the zero test.
    """
    value, mask = masked[1], masked[2]
    if other[0] != "const" or type(other[1]) is not int:
        raise Unsupported("掩码值与非常量比较")
    constant = other[1] & ((1 << bits) - 1)
    zero = _mask_zero(value, _const(mask))
    if code in ("e", "z", "ne", "nz"):
        if constant == 0:
            test = zero
        elif constant & ~mask:
            test = _const(False)
        else:
            free = [1 << i for i in range(bits) if not mask >> i & 1]
            if len(free) > MAX_MASK_FREE_BITS:
                raise Unsupported("掩码相等判断的取值过多")
            values = [constant]
            for bit in free:
                values += [v | bit for v in values]
            test = b_join(
                "or",
                tuple(
                    ("cmp", "==", value, _const(_to_signed(v, bits))) for v in values
                ),
            )
        return test if code in ("e", "z") else b_not(test)
    operator = UNSIGNED.get(code)
    if (operator, constant) in (("<", 1), ("<=", 0)):
        return zero
    if (operator, constant) in ((">=", 1), (">", 0)):
        return b_not(zero)
    raise Unsupported("掩码值的比较")


def _relatable(sym, bits):
    """A field read (or a narrow field plus a constant) in a ``bits``-wide compare.

    ``field + d`` stays exact only when it cannot wrap: a field of at most two
    bytes and a small constant in a 32-bit register.
    """
    if sym[0] in ("load", "vcall"):
        return sym[1] * 8 <= bits
    return (
        sym[0] == "off"
        and sym[1][0] == "load"
        and sym[1][1] <= 2
        and bits == 32
        and abs(sym[2]) < 1 << 15
    )


def _negative(sym):
    if sym[0] == "off":
        return ("cmp", "<", sym[1], _const(-sym[2]))
    return ("cmp", "<", sym, _const(0))


def _relation(a, b, bits, code):
    """``a OP b`` between two field reads; unsigned compares split on the signs.

    As unsigned numbers, a negative value is above every non-negative one;
    values of the same sign keep their signed order.
    """
    if not (_relatable(a, bits) and _relatable(b, bits)):
        raise Unsupported("字段与字段的比较")
    if code in SIGNED:
        return ("cmp", SIGNED[code], a, b)
    operator = UNSIGNED.get(code)
    if operator is None:
        raise Unsupported("条件码 " + code)
    na, nb = _negative(a), _negative(b)
    same = b_join(
        "or", (b_join("and", (na, nb)), b_join("and", (b_not(na), b_not(nb))))
    )
    if operator in ("<", "<="):
        cross = b_join("and", (b_not(na), nb))
    else:
        cross = b_join("and", (na, b_not(nb)))
    return b_join("or", (cross, b_join("and", (same, ("cmp", operator, a, b)))))


def _unsigned(operator, a, bound, bits):
    """Unsigned ``a OP bound`` over a value read as signed ``bits``-bit.

    Non-negative values keep their order; negative ones are above every
    non-negative value and keep their order among themselves.
    """
    k = bound - (1 << bits) if bound >> (bits - 1) else bound
    negative = ("cmp", "<", a, _const(0))
    test = ("cmp", operator, a, _const(k))
    if k >= 0:
        if operator in (">", ">="):
            return b_join("or", (test, negative))
        return b_join("and", (b_not(negative), test))
    if operator in ("<", "<="):
        return b_join("or", (b_not(negative), test))
    return b_join("and", (negative, test))


def _truth(sym):
    if _is_bool(sym):
        return sym if sym[0] != "const" else _const(bool(sym[1]))
    if sym[0] == "const":
        return _const(bool(sym[1]))
    if sym[0] in ("load", "param", "global", "addr"):
        return ("cmp", "!=", sym, _const(0))
    if sym[0] == "masked":
        return b_not(_mask_zero(sym[1], _const(sym[2])))
    raise Unsupported("返回值不是可识别的布尔值")


class State:
    __slots__ = ("regs", "xmm", "stack", "flags", "calls", "visits", "facts", "bound")

    def __init__(self):
        self.regs, self.xmm, self.stack = {}, {}, {}
        self.flags = None
        self.calls = ()
        self.visits = {}
        self.facts = frozenset()
        # Argument loads fixed to one enum value on this path.
        self.bound = {}

    def copy(self):
        other = State()
        other.regs, other.xmm, other.stack = (
            dict(self.regs),
            dict(self.xmm),
            dict(self.stack),
        )
        other.flags, other.calls = self.flags, self.calls
        other.visits, other.facts = dict(self.visits), self.facts
        other.bound = dict(self.bound)
        return other


class Executor:
    """Symbolic execution of one command body and the helpers it calls."""

    def __init__(self, pe, partial=False, domain=None):
        self.pe = pe
        self.partial = partial
        # sym -> declared enum values of a resource argument field, or None.
        self.domain = domain
        # The command's own range; jumps outside it are recorded helpers.
        self.entry = (0, 0)
        # Function address -> reference lookup kind (REFERENCE_LOOKUPS).
        self.lookups = {}
        # (type, global sym, size) -> value proven by the type's .cctor, or None.
        self.statics = None
        # (object sym, slot offset) -> (value sym, override addresses), or None.
        self.virtuals = None
        self.unknown_paths = set()
        # Merge paths at helper returns (see merged_call); markers -> returns.
        self.merge = False
        self.marks = 0
        self.returns = {}
        # Merge mode: (address, machine state) -> formula from there.
        self.memo = {}
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

    def inside(self, address):
        """True when ``address`` lies in the command or a recorded helper."""
        return any(
            start <= address < end
            for start, end in (self.entry, *self.functions.items())
        )

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
        if not mem.base:
            raise Unsupported("绝对地址")
        base = ins.reg_name(mem.base)
        if mem.index:
            index = self.reg(state, ins.reg_name(mem.index))
            if index[0] in ("load", "off") and base != "rip":
                # An array element at an index read from a field:
                # ("elem", array, index, scale, displacement).
                pointer = self.reg(state, base)
                if pointer[0] == "addr":
                    pointer, displacement = pointer[1], pointer[2] + mem.disp
                else:
                    displacement = mem.disp
                if pointer[0] not in ("load", "param", "ref_enemy", "ref_squad"):
                    raise Unsupported("变量索引")
                return ("elem", pointer, index, mem.scale, displacement)
            if index[0] != "const" or type(index[1]) is not int:
                raise Unsupported("变量索引")
            displacement = mem.disp + index[1] * mem.scale
        else:
            displacement = mem.disp
        if base == "rip":
            return ("gaddr", ins.address + ins.size + displacement)
        return _offset(self.reg(state, base), displacement)

    def load(self, address, size, state, floating=False):
        kind = address[0]
        if kind == "stack":
            return self.stack_load(address[1], size, state, floating)
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
            sym = ("load", size, address[1], address[2])
        elif kind == "elem":
            sym = ("load", size, address[:4], address[4])
        else:
            sym = ("load", size, address, 0)
        if sym in state.bound:
            return state.bound[sym]
        values = self.domain(sym) if self.domain and not floating else None
        if values:
            raise Concretize(sym, values)
        return sym

    @staticmethod
    def stack_load(offset, size, state, floating):
        """A local slot, or part of a wider copy of a field (e.g. a 16-byte struct)."""
        stored = state.stack.get(offset)
        if stored is not None and stored[0] == size:
            return stored[1]
        if stored is not None and stored[0] > size and not floating:
            return _narrow(stored[1], size * 8)
        for start, (width, value) in state.stack.items():
            if (
                start < offset
                and offset + size <= start + width
                and value[0] == "load"
                and value[1] == width
            ):
                # Bytes inside a copied field read: the field's own bytes.
                return ("load", size, value[2], value[3] + offset - start)
        return ("opaque",)

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
            old = state.regs.get(wide, ("opaque",))
            if (
                old[0] == "const"
                and type(old[1]) is int
                and value[0] == "const"
                and type(value[1]) in (int, bool)
            ):
                # xor r12d, r12d; setne r12b: the other bytes stay known.
                state.regs[wide] = _const(old[1] & ~0xFF | int(value[1]) & 0xFF)
            else:
                state.regs[wide] = ("low8", old, value)
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
            if a == b and a[0] == "masked":
                # and reg, mask; je/jne: the masked field is (non-)zero.
                a, b = a[1], _const(a[2])
            if a != b and all(v[0] == "const" and type(v[1]) is int for v in (a, b)):
                zero = _const(a[1] & b[1] == 0)
                if code in ("e", "z"):
                    return zero
                if code in ("ne", "nz"):
                    return b_not(zero)
                raise Unsupported("位测试的条件码 " + code)
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
            if a[0] == "off":
                zero = ("cmp", "==", a[1], _const(_wrap32(-a[2])))
            else:
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
            if a[0] == "masked":
                return _masked_condition(a, b, bits, code)
            if a[0] in FIELD_VALUES and b[0] in FIELD_VALUES:
                return _relation(a, b, bits, code)
            if a[0] == "off":
                return Executor.offset_condition(a, b, bits, code)
            mask = (1 << bits) - 1
            if a[0] == b[0] == "const" and type(a[1]) is int and type(b[1]) is int:
                # Both known (often after an argument fork): decide on the bits.
                x, y = a[1] & mask, b[1] & mask
                if code in SIGNED:
                    x, y = _to_signed(x, bits), _to_signed(y, bits)
                operator = SIGNED.get(code) or UNSIGNED.get(code)
                if operator is None:
                    raise Unsupported("条件码 " + code)
                return _fold(("cmp", operator, _const(x), _const(y)))
            if code in SIGNED:
                if b[0] == "const" and type(b[1]) is int:
                    b = _const(_to_signed(b[1] & mask, bits))
                return ("cmp", SIGNED[code], a, b)
            if code in UNSIGNED:
                if b[0] != "const" or type(b[1]) is not int:
                    raise Unsupported("无符号比较")
                return _unsigned(UNSIGNED[code], a, b[1] & mask, bits)
            raise Unsupported("条件码 " + code)
        if kind == "fcmp":
            ordered = {"a": ">", "nbe": ">", "ae": ">=", "nb": ">=", "nc": ">="}
            ordered.update({"b": "<", "c": "<", "nae": "<", "be": "<=", "na": "<="})
            if code in ordered:
                return ("cmp", ordered[code], flags[1], flags[2])
            raise Unsupported("浮点相等或无序判断")
        raise Unsupported("条件码来源")

    @staticmethod
    def offset_condition(a, b, bits, code):
        """Conditions on ``field + d``: equality and the range idiom.

        ``lea eax, [x - c]; cmp eax, k; jbe`` tests c <= x <= c + k; as the
        arithmetic wraps, only equality and unsigned ranges stay exact.
        """
        if b[0] != "const" or type(b[1]) is not int or bits != 32:
            raise Unsupported("偏移值的比较")
        x, d = a[1], a[2]
        k = b[1] - (1 << 32) if b[1] >> 31 else b[1]
        if code in ("e", "z", "ne", "nz"):
            test = ("cmp", "==", x, _const(_wrap32(k - d)))
            return test if code in ("e", "z") else b_not(test)
        if code in UNSIGNED and 0 <= b[1] < (1 << 31):
            low, high = -d, -d + b[1]
            if not -(1 << 31) <= low <= high < (1 << 31):
                raise Unsupported("区间跨越 32 位边界")
            inside = {"<": high - 1, "<=": high, ">": high, ">=": high - 1}
            operator = UNSIGNED[code]
            test = b_join(
                "and",
                (
                    ("cmp", ">=", x, _const(low)),
                    ("cmp", "<=", x, _const(inside[operator])),
                ),
            )
            return test if operator in ("<", "<=") else b_not(test)
        raise Unsupported("偏移值的有符号比较")

    # --------------------------------------------------------- execution

    def run(self, address, state):
        """Formula that the outermost function returns true from here.

        In partial mode a path that leaves the recognised subset (a variable
        index, a loop, an unsupported instruction...) ends as an explicit
        unknown from its last branch on; other paths keep their formula.

        With ``merge`` the result depends only on the machine state, never on
        path facts (they are dropped), so equal states at one address share
        one result; a revisit on the same path still reports the loop.
        """
        if self.merge and not state.visits.get((address, state.calls)):
            state.facts = frozenset()
            rsp = state.regs.get("rsp", ("opaque",))
            live = rsp[1] if rsp[0] == "stack" else None
            key = (
                address,
                state.calls,
                tuple(sorted(state.regs.items())),
                tuple(sorted(state.xmm.items())),
                tuple(
                    sorted(
                        (k, v)
                        for k, v in state.stack.items()
                        if live is None or k >= live
                    )
                ),
                state.flags,
                tuple(sorted(state.bound.items())),
            )
            if key not in self.memo:
                self.memo[key] = self.guarded(address, state)
            return self.memo[key]
        return self.guarded(address, state)

    def guarded(self, address, state):
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
                raise Fatal(TOO_MANY_PATHS)
            key = (address, state.calls)
            state.visits[key] = state.visits.get(key, 0) + 1
            if state.visits[key] > 1:
                raise Unsupported("循环")
            if address in self.lookups and address != self.entry[0]:
                # Entered by call, jump or conditional tail jump alike.
                root = self.reference(self.lookups[address], state)
                if root is not None:
                    self.function(address)
                    state.regs["rax"] = root
                    for name in ("rcx", "rdx", "r8", "r9", "r10", "r11"):
                        state.regs[name] = ("opaque",)
                    state.flags = None
                    rsp = self.reg(state, "rsp")
                    back = self.load(rsp, 8, state)
                    if back[0] != "retaddr":
                        raise Fatal("返回地址不平衡")
                    state.regs["rsp"] = _offset(rsp, 8)
                    if back[1] is None:
                        return _truth(self.reg(state, "al"))
                    if type(back[1]) is tuple:
                        return self.returned(back[1], state)
                    address, state.calls = back[1], state.calls[:-1]
                    continue
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
                if type(state.calls[-1]) is tuple:
                    return self.returned(state.calls[-1], state)
                address, state.calls = state.calls[-1], state.calls[:-1]
                continue
            if mnemonic in ("adc", "sbb"):
                result = self.carry(ins, state, following)
                if result is not None:
                    return result
                address = following
                continue
            if mnemonic == "call" and ops[0].type == X86_OP_MEM:
                self.virtual(ins, state)
                address = following
                continue
            if mnemonic == "call" or (mnemonic == "jmp" and ops[0].type == X86_OP_IMM):
                if ops[0].type != X86_OP_IMM:
                    raise Unsupported("间接调用或跳转")
                target = ops[0].imm
                if mnemonic == "jmp":
                    if not self.inside(target):
                        # A tail jump into another function: record it too.
                        self.function(target)
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
                # A jump-table entry that the argument already made constant.
                target = self.read(ins, ops[0], state)
                if target[0] == "gaddr" or (
                    target[0] == "const" and type(target[1]) is int
                ):
                    address = target[1]
                    continue
                raise Unsupported("间接跳转")
            try:
                self.step(ins, state)
            except NullAccess:
                return NULL_PATH
            except Concretize as fork:
                return self.concretize(address, state, fork)
            address = following

    def concretize(self, address, state, fork):
        """Re-run the instruction once per declared value of the argument.

        Resources serialize a declared value, so switches, tables and helpers
        keyed by the argument become concrete; ``instantiate`` later keeps the
        branch of the node's actual value. Any other value stays unknown.
        """
        mask = (1 << (fork.sym[1] * 8)) - 1
        tests, out = [], []
        for value in fork.values:
            test = ("cmp", "==", fork.sym, _const(value & mask))
            branch = state.copy()
            branch.visits[(address, state.calls)] -= 1
            branch.bound[fork.sym] = _const(value & mask)
            branch.facts = branch.facts | {test}
            tests.append(test)
            out.append(b_join("and", (test, self.run(address, branch))))
        other = tuple(b_not(test) for test in tests)
        out.append(b_join("and", other + (("unknown", "资源参数取值不在枚举声明中"),)))
        return b_join("or", tuple(out))

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
        return self.join(test, then, otherwise)

    def join(self, test, then, otherwise):
        """The two branches of ``test``; merge mode shares repeated continuations."""
        if then == otherwise:
            return then
        if self.merge:
            return _branch(test, then, otherwise)
        return b_join(
            "or", (b_join("and", (test, then)), b_join("and", (b_not(test), otherwise)))
        )

    def carry(self, ins, state, following):
        """``adc``/``sbb`` of constants: fork on CF (``cmp a, b`` sets a <u b).

        ``xor eax, eax; cmp x, 1; adc eax, 1`` gives 2 when x is 0, else 1.
        ``sbb r, r`` is -CF whatever r holds. Other operands are opaque.
        Returns a formula when the paths were forked, else None.
        """
        ops = ins.operands
        bits = ops[0].size * 8
        if ops[0].type == ops[1].type == X86_OP_REG and ops[0].reg == ops[1].reg:
            a = b = _const(0) if ins.mnemonic == "sbb" else None
        else:
            a, b = self.read(ins, ops[0], state), self.read(ins, ops[1], state)
        if (
            a is None
            or state.flags is None
            or not all(v[0] == "const" and type(v[1]) is int for v in (a, b))
        ):
            self.write(ins, ops[0], ("opaque",), state)
            state.flags = None
            return None
        test = _fold(self.condition(state.flags, "b"))
        sign = 1 if ins.mnemonic == "adc" else -1

        def go(cf):
            branch = state.copy()
            if test[0] != "const":
                branch.facts = frozenset(branch.facts | {test if cf else b_not(test)})
            value = (a[1] + sign * (b[1] + cf)) & ((1 << bits) - 1)
            self.write(ins, ops[0], _const(value), branch)
            branch.flags = None
            return self.run(following, branch)

        if test in state.facts or test == ("const", True):
            return go(1)
        if b_not(test) in state.facts or test == ("const", False):
            return go(0)
        return self.join(test, go(1), go(0))

    def virtual(self, ins, state):
        """``call [header + slot]``: a virtual getter that every override answers
        with a constant (see ``virtual_method``) becomes the value ``("vcall",
        size, object, method, return type)``; any other indirect call is rejected.
        """
        mem = ins.operands[0].mem
        if mem.index or mem.segment or not mem.base or self.virtuals is None:
            raise Unsupported("间接调用或跳转")
        header = self.reg(state, ins.reg_name(mem.base))
        if header[0] != "load" or header[1] != 8 or header[3] != 0:
            raise Unsupported("间接调用或跳转")
        found = self.virtuals(header[2], mem.disp)
        if found is None:
            raise Unsupported("虚函数调用")
        value, overrides = found
        for start, end in overrides:
            # The verified bytes of each constant-returning override.
            self.functions.setdefault(start, end)
        state.regs["rax"] = value
        for name in ("rcx", "rdx", "r8", "r9", "r10", "r11"):
            state.regs[name] = ("opaque",)
        state.flags = None

    def throws(self, address):
        """The call at hand starts a straight run of calls ending in ``int3``.

        Exceptions are built by one helper and raised by the next, as in
        ``e = create(thread, klass, 0); raise(thread, e); int3``. The raise
        only stores the exception in the thread's pending slot and returns,
        so the compiler may omit the ``int3``; a call to that store (checked
        by its bytes, see ``sets_pending_exception``) also ends the run.
        """
        for _ in range(8):
            ins = self.instruction(address)
            if ins.mnemonic == "int3":
                return True
            if ins.mnemonic not in ("mov", "lea", "call", "xor"):
                return False
            if (
                ins.mnemonic == "call"
                and ins.operands[0].type == X86_OP_IMM
                and self.sets_pending_exception(ins.operands[0].imm)
            ):
                return True
            address = ins.address + ins.size
        return False

    def sets_pending_exception(self, target):
        """``mov rax, [rcx + holder]; mov [rax + slot], rdx; ret``: the store of
        an exception (rdx) into the thread's (rcx) pending-exception slot."""
        code = list(self.md.disasm(self.pe.read(target, 16), target, 3))
        if len(code) != 3 or [i.mnemonic for i in code] != ["mov", "mov", "ret"]:
            return False
        load, store = code[0].operands, code[1].operands
        if not (
            load[0].type == X86_OP_REG
            and code[0].reg_name(load[0].reg) == "rax"
            and load[1].type == X86_OP_MEM
            and code[0].reg_name(load[1].mem.base) == "rcx"
            and not load[1].mem.index
            and load[1].mem.disp == THREAD_EXCEPTION_HOLDER
            and store[0].type == X86_OP_MEM
            and code[1].reg_name(store[0].mem.base) == "rax"
            and not store[0].mem.index
            and store[0].mem.disp == PENDING_EXCEPTION
            and store[1].type == X86_OP_REG
            and code[1].reg_name(store[1].reg) == "rdx"
        ):
            return False
        # The conclusion rests on these bytes: verify them with the model.
        self.functions.setdefault(target, code[2].address + code[2].size)
        return True

    def reference(self, kind, state):
        """The named root returned by a reference lookup."""
        if kind == "squad":
            # findSquad(this = EnemyManager, group): r8 is the Group module.
            return ("ref_squad", self.reg(state, "r8"))
        # getEnemyManageInfo(&key, flag): the key is read through rdx.
        pointer, flag = self.reg(state, "rdx"), self.reg(state, "r8", 8)
        if flag[0] != "const" or type(flag[1]) is not int:
            raise Unsupported("引用查找的标志不是常量")
        key = self.load(pointer, 8, state)
        if key[0] == "global" and pointer[0] == "stack" and self.statics:
            # A local key still holding a proven static (TARGET_ACCESS_KEY.INVALID):
            # put the constant in place and run the lookup's own code instead.
            value = self.statics(TARGET_ACCESS_KEY, key, 8)
            if value is not None:
                state.stack[pointer[1]] = (8, _const(value))
                return None
        if key[0] != "load" or key[1] != 8:
            raise Unsupported("引用键不是字段")
        return ("ref_enemy", key, flag[1] & 1)

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
            # Inside a merged call it is kept apart from the callee's own
            # false result until evaluate settles it (see summary).
            if any(type(call) is tuple for call in state.calls):
                return HALT
            return _const(False)
        if len(state.calls) >= MAX_CALL_DEPTH:
            raise Unsupported("调用层数过深")
        self.function(target)
        if self.merge:
            return self.merged_call(target, state, following)
        rsp = _offset(self.reg(state, "rsp"), -8)
        state.regs["rsp"] = rsp
        state.stack[rsp[1]] = (8, ("retaddr", following))
        state.calls = state.calls + (following,)
        return None

    def merged_call(self, target, state, following):
        """Run the callee once, then the caller once per distinct return state.

        Inlining continues the caller separately on every callee path, which
        multiplies with each helper and argument fork. Here every return
        (``ret`` to the marker pushed instead of ``following``) is recorded;
        returns whose registers, caller frame, flags and bound arguments are
        identical share one continuation, and the callee formula's return
        markers are replaced by those continuations. The result is the same
        formula up to path facts, which only prune impossible combinations.
        """
        self.marks += 1
        marker = ("return", self.marks)
        caller = self.reg(state, "rsp")
        if caller[0] != "stack":
            raise Unsupported("栈指针未知")
        entry = state.copy()
        rsp = _offset(caller, -8)
        entry.regs["rsp"] = rsp
        entry.stack[rsp[1]] = (8, ("retaddr", marker))
        entry.calls = state.calls + (marker,)
        self.returns[marker] = []
        body = self.run(target, entry)
        finals = self.returns.pop(marker)
        summary = self.summary(body, marker, finals)
        if summary is not None:
            # Only the Boolean result differs: continue once with rax = F.
            branch = state.copy()
            branch.regs, branch.xmm = dict(finals[0].regs), dict(finals[0].xmm)
            branch.stack = {k: v for k, v in finals[0].stack.items() if k >= caller[1]}
            branch.flags, branch.bound = None, dict(finals[0].bound)
            branch.regs["rax"] = summary
            return self.run(following, branch)
        leaves, continuations = {}, {}
        for index, final in enumerate(finals):
            # Slots below the caller's stack pointer are dead after the return.
            frame = {k: v for k, v in final.stack.items() if k >= caller[1]}
            key = (
                tuple(sorted(final.regs.items())),
                tuple(sorted(final.xmm.items())),
                tuple(sorted(frame.items())),
                final.flags,
                tuple(sorted(final.bound.items())),
            )
            if key not in continuations:
                branch = state.copy()
                branch.regs, branch.xmm = dict(final.regs), dict(final.xmm)
                branch.stack, branch.flags = frame, final.flags
                branch.bound = dict(final.bound)
                continuations[key] = self.run(following, branch)
            leaves[("return", marker, index)] = continuations[key]
        return _substitute(body, leaves)

    def summary(self, body, marker, finals):
        """The callee's Boolean result F, when that is all its paths differ in.

        Every path must end in a return (no throw ``halt`` and no unknown
        terminal) and every return state must agree except for rax, whose
        low byte is a Boolean. F replaces each return by its ``al``.
        """
        if not finals or _has_terminal(body):
            return None
        first = finals[0]
        frame = lambda s: {
            k: v for k, v in s.stack.items() if k >= first.regs["rsp"][1]
        }
        others = lambda s: {k: v for k, v in s.regs.items() if k != "rax"}
        values = {}
        for index, final in enumerate(finals):
            if (
                others(final) != others(first)
                or final.xmm != first.xmm
                or frame(final) != frame(first)
                or final.bound != first.bound
            ):
                return None
            al = self.reg(final, "al")
            if not (_is_bool(al) or (al[0] == "const" and type(al[1]) is int)):
                return None
            values[("return", marker, index)] = _truth(al)
        return _substitute(body, values)

    def returned(self, marker, state):
        """A return to a merged call's marker: record the state, end the path.

        Volatile registers and flags are dead after a call (Windows x64
        convention), so they become opaque; a caller that read one would
        fail as unsupported, never get a wrong value. rax/xmm0 are results.
        """
        final = state.copy()
        for name in VOLATILE_REGISTERS:
            final.regs.pop(name, None)
        for name in VOLATILE_XMM:
            final.xmm.pop(name, None)
        final.flags = None
        found = self.returns[marker]
        found.append(final)
        return ("return", marker, len(found) - 1)

    def arithmetic(self, ins, state):
        """Integer results that are exact: constants, and fields +- 1."""
        mnemonic, ops = ins.mnemonic, ins.operands
        bits = ops[0].size * 8
        mask = (1 << bits) - 1
        values = [self.read(ins, op, state) for op in ops]
        a = values[0] if mnemonic != "imul" or len(ops) == 2 else values[1]
        if mnemonic in ("inc", "dec") and bits == 32 and a[0] in ("load", "off"):
            return _plus(a, 1 if mnemonic == "inc" else -1)
        operands = values if mnemonic != "imul" or len(ops) == 2 else values[1:]
        if not all(v[0] == "const" and type(v[1]) is int for v in operands):
            return ("opaque",)
        x = operands[0][1] & mask
        y = operands[1][1] & mask if len(operands) > 1 else None
        result = {
            "inc": lambda: x + 1,
            "dec": lambda: x - 1,
            "neg": lambda: -x,
            "not": lambda: ~x,
            "shl": lambda: x << (y & (bits - 1)),
            "shr": lambda: x >> (y & (bits - 1)),
            "sar": lambda: _to_signed(x, bits) >> (y & (bits - 1)),
            "imul": lambda: _to_signed(x, bits) * _to_signed(y, bits),
        }[mnemonic]()
        return _const(result & mask)

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
            if mnemonic != "movzx" and value[0] == "const" and type(value[1]) is int:
                # Constants stay bit patterns of the destination width.
                bits = ops[1].size * 8
                signed = _to_signed(value[1] & ((1 << bits) - 1), bits)
                value = _const(signed & ((1 << (ops[0].size * 8)) - 1))
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
            mem = ops[1].mem
            named = ins.reg_name(mem.base) if mem.base else "rip"
            base = self.reg(state, named) if named != "rip" else None
            index = self.reg(state, ins.reg_name(mem.index)) if mem.index else _const(0)
            if (
                base is not None
                and all(v[0] == "const" and type(v[1]) is int for v in (base, index))
                and base[1] != 0
            ):
                # Arithmetic on constants (lea ecx, [rax - 1] after a clamp);
                # a null base keeps the null-object handling of addresses.
                value = base[1] + index[1] * mem.scale + mem.disp
                self.write(
                    ins, ops[0], _const(value & ((1 << (ops[0].size * 8)) - 1)), state
                )
            else:
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
                elif bits == 32 and a[0] in ("load", "off"):
                    value = _plus(a, delta)
                else:
                    value = ("opaque",)
            elif (
                mnemonic == "add" and bits == 64 and {a[0], b[0]} == {"gaddr", "const"}
            ):
                # Jump-table base plus a constant entry.
                base, entry = (a, b) if a[0] == "gaddr" else (b, a)
                value = ("gaddr", base[1] + _signed64(entry[1]))
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
            elif mnemonic == "and" and {a[0], b[0]} == {"load", "const"}:
                field, mask = (a, b) if a[0] == "load" else (b, a)
                if type(mask[1]) is int and field[1] == ops[0].size:
                    mask = mask[1] & ((1 << (field[1] * 8)) - 1)
                    if mask == (1 << (field[1] * 8)) - 1:
                        value = field
                    elif mask:
                        # field & mask, tested by the following test/cmp.
                        value = ("masked", field, mask)
                    else:
                        value = _const(0)
                elif type(mask[1]) is int and mask[1] == (1 << (field[1] * 8)) - 1:
                    value = field
            elif (
                mnemonic == "and"
                and ops[0].size == 8
                and {a[0], b[0]} == {"stack", "const"}
                and (a if a[0] == "const" else b)[1] == (1 << 63) - 1
            ):
                # Clearing bit 63 of a pointer to a local, as btr reg, 63.
                value = a if a[0] == "stack" else b
            self.write(ins, ops[0], value, state)
            state.flags = ("test", value, value, ops[0].size * 8)
        elif mnemonic in ("shr", "sar"):
            a, b = self.read(ins, ops[0], state), self.read(ins, ops[1], state)
            if (
                a[0] == "load"
                and b[0] == "const"
                and b[1] % 8 == 0
                and b[1] // 8 < a[1]
            ):
                value = ("load", a[1] - b[1] // 8, a[2], a[3] + b[1] // 8)
            else:
                value = self.arithmetic(ins, state)
            self.write(ins, ops[0], value, state)
            state.flags = None
        elif mnemonic in ("shl", "imul", "inc", "dec", "neg", "not"):
            self.write(ins, ops[0], self.arithmetic(ins, state), state)
            state.flags = None
        elif mnemonic in ("bsr", "bsf"):
            self.write(ins, ops[0], ("opaque",), state)
            state.flags = None
        elif (
            mnemonic in ("btr", "bts")
            and ops[1].type == X86_OP_IMM
            and ops[1].imm == 63
            and ops[0].type == X86_OP_REG
            and self.read(ins, ops[0], state)[0] == "stack"
        ):
            # Clearing/setting bit 63 of a pointer to a local: on x64 Windows
            # user-mode addresses have it clear, so btr keeps the pointer.
            if mnemonic == "bts":
                self.write(ins, ops[0], ("opaque",), state)
            state.flags = None
        elif mnemonic == "bt":
            # CF = bit b of a; only constants (e.g. an argument-indexed mask).
            a, b = self.read(ins, ops[0], state), self.read(ins, ops[1], state)
            if not all(v[0] == "const" and type(v[1]) is int for v in (a, b)):
                raise Unsupported("指令 bt")
            bit = (a[1] >> (b[1] & (ops[0].size * 8 - 1))) & 1
            # Unsigned 0 < bit reproduces CF for jb/jae/setb/setae.
            state.flags = ("cmp", _const(0), _const(bit), 8)
        elif mnemonic in ("cdqe", "cwde"):
            # rax = sign-extend(eax), eax = sign-extend(ax) (upper rax cleared).
            source, wide = (32, 64) if mnemonic == "cdqe" else (16, 32)
            state.regs["rax"] = _sign_extend(
                self.reg(state, "rax", source), source, wide
            )
        elif mnemonic in ("cdq", "cqo"):
            state.regs["rdx"] = ("opaque",)
        else:
            raise Unsupported("指令 " + mnemonic)


def evaluate(
    pe,
    address,
    partial=False,
    domain=None,
    lookups=None,
    statics=None,
    virtuals=None,
    merge=None,
):
    """The formula over symbolic loads that the command at ``address`` returns.

    The third value lists why paths ended unknown (partial mode only).
    ``merge`` None inlines helpers and merges paths only when inlining
    exceeds MAX_STEPS; True or False forces one mode.
    """
    modes = (False, True) if merge is None else (merge,)
    for merge in modes:
        executor = Executor(pe, partial, domain)
        executor.entry = (address, pe.end(address))
        executor.lookups = lookups or {}
        executor.statics = statics
        executor.virtuals = virtuals
        executor.merge = merge
        state = State()
        for register, name in ENTRY_REGISTERS.items():
            state.regs[register] = ("param", name)
        state.regs["rsp"] = ("stack", 0)
        state.stack[0] = (8, ("retaddr", None))
        try:
            formula = executor.run(address, state)
        except Fatal as error:
            # Too many inlined paths: retry merging them at helper returns.
            if merge is modes[-1] or str(error) != TOO_MANY_PATHS:
                raise
            continue
        if merge:
            formula = _substitute(formula, {HALT: _const(False)})
        return formula, executor.functions, sorted(executor.unknown_paths)


# ------------------------------------------------------------- semantics


class NativeNamer(Namer):
    """Formula naming where a load at a struct field reads its first member.

    Machine code reads the members of a value-type field one by one; the
    pseudo-C recognizer never sees such reads, so only this namer descends.
    It also names what only the x64 recognizer produces: array elements at an
    index read from a field, constant-returning virtual getters and
    comparisons between two fields (``relations``).
    """

    # _expression names field-to-field comparisons only for this namer.
    relations = True

    def __init__(self, metadata, row, work, argument, pe=None):
        super().__init__(metadata, row, work, argument)
        # The PE, when given, names native fields by their trivial getters.
        self.pe = pe
        self.getters = []
        self._getter_cache = {}

    def getter_field(self, owner, offset):
        """(["Name"], type) of a native field that no metadata row describes.

        Native types (via.*) declare no fields, but a property getter whose
        whole body is ``mov reg, [rdx + offset]; ret`` (rdx is ``this``)
        returns exactly that field, so it is named after the property. The
        getter is kept in ``getters`` and its bytes verified as a helper.
        """
        if self.pe is None:
            return None
        cache = (owner, offset)
        if cache in self._getter_cache:
            return self._getter_cache[cache]
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True
        found, seen = None, set()
        while owner and owner not in seen and found is None:
            seen.add(owner)
            record = self.metadata.get(owner) or {}
            for method, info in (record.get("methods") or {}).items():
                returns = (info.get("returns") or {}).get("type")
                size = FIELD_SIZES.get(returns)
                if (
                    not method.startswith("get_")
                    or info.get("params")
                    or not int(info.get("function") or "0", 16)
                    or size is None
                ):
                    continue
                start = int(info["function"], 16)
                code = list(md.disasm(self.pe.read(start, 16), start, 2))
                if (
                    len(code) == 2
                    and code[0].mnemonic == "mov"
                    and code[1].mnemonic == "ret"
                    and not code[1].operands
                    and code[0].operands[0].type == X86_OP_REG
                    and code[0].operands[1].type == X86_OP_MEM
                    and code[0].operands[1].size == size
                    and code[0].reg_name(code[0].operands[1].mem.base) == "rdx"
                    and not code[0].operands[1].mem.index
                    and code[0].operands[1].mem.disp == offset
                ):
                    name = method.rstrip("0123456789")
                    found = [name[len("get_") :]], returns
                    getter = dict(
                        type=owner,
                        method=name,
                        address=hex(start),
                        end=hex(code[1].address + code[1].size),
                    )
                    if getter not in self.getters:
                        self.getters.append(getter)
                    break
            owner = record.get("parent")
        self._getter_cache[cache] = found
        return found

    def field(self, owner, offset):
        if owner.endswith("[]") and self.field_size(owner[:-2]) == "reference":
            # A constant index into an array of object references.
            index, rest = divmod(offset - ARRAY_DATA, 8)
            if offset < ARRAY_DATA or rest:
                return None
            return [f"[{index}]"], owner[:-2]
        found = super().field(owner, offset) or self.getter_field(owner, offset)
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

    def argument_domain(self, sym):
        """Declared values of the enum argument field read by ``sym``, or None."""
        base = sym[2] if sym[0] == "load" else None
        if not (
            base
            and sym[3] == EDIT_FIELD_VALUE
            and base[0] == "load"
            and base[2] == ("param", "param_4")
        ):
            return None
        named = self.argument_field(base[3])
        if named is None:
            return None
        field = self.metadata.fields(named[2]).get(named[1].split("|")[0], {})
        if field.get("type") == BOOL_EDIT_FIELD and sym[1] == 1:
            return [0, 1]
        values = self.metadata.enum(field.get("type"))[1]
        if not values or len(values) > MAX_ENUM_FORK:
            return None
        return sorted({v for v in values.values() if type(v) is int})

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

    def path(self, sym):
        if sym[0] in ("ref_enemy", "ref_squad"):
            root = self.reference_root(sym)
            if root is None:
                return None
            kind = "enemy" if sym[0] == "ref_enemy" else "squad"
            return (root, REFERENCE_LOOKUPS[kind][3], [])
        if sym[0] == "load" and sym[2][0] == "elem":
            found = self.element(sym)
            if found is None or self.field_size(found[1]) != "reference":
                return None
            return found
        return super().path(sym)

    def element(self, sym):
        """(root, element type, names) of an array element read at a field index.

        ``("load", size, ("elem", array, index, scale), offset)`` reads element
        ``index + (offset - 0x20) / scale``; the index is spelled by its field
        key, so the element is "_items[Schedule._CurrentIndex-1]".
        """
        _, size, (_, array, index, scale), offset = sym
        parent = self.path(array)
        if parent is None or not str(parent[1]).endswith("[]"):
            return None
        element = parent[1][:-2]
        width = self.field_size(element)
        width = 8 if width == "reference" else width
        if width != scale or size != width:
            return None
        delta, rest = divmod(offset - ARRAY_DATA, width)
        text = None if rest else self.index_text(index, delta)
        if text is None:
            return None
        return (parent[0], element, parent[2] + [f"[{text}]"])

    def index_text(self, index, delta):
        """The index field's key (without "context:") plus a constant."""
        if index[0] == "off":
            index, delta = index[1], delta + index[2]
        named = self.leaf(index) if index[0] == "load" else None
        if not named or named[0] != "key" or self.field_size(named[2]) != index[1]:
            return None
        text = named[1].removeprefix("context:")
        return text + (f"{delta:+d}" if delta else "")

    def key(self, found):
        """Runtime key of a resolved (root, type, names) field."""
        root, _, names = found
        if root.startswith(REFERENCE_PREFIXES):
            return root + "/" + _join(names)
        if root == "context":
            path = self.indexed(_join(names))
            return CONTEXT_KEY_ALIASES.get(path, "context:" + path)
        if root != "extend" or len(names) < 2:
            return None
        return f"extend:{names[0]}." + _join(names[1:])

    def relation(self, a, b):
        """(left key, right key, d, references) for "a OP b + d", or None.

        Both sides must be named fields read at their own width (or a narrow
        field plus a constant, or a constant-returning virtual getter).
        """
        sides = []
        for value in (a, b):
            delta = 0
            if value[0] == "off":
                value, delta = value[1], value[2]
            if value[0] not in ("load", "vcall"):
                return None
            named = self.leaf(value)
            if named is None or named[0] != "key":
                return None
            size = self.field_size(named[2])
            if value[0] == "load" and size not in (value[1], "reference"):
                return None
            if size == "reference" and value[1] != 8:
                return None
            sides.append((named[1], delta, size == "reference"))
        (left, da, ra), (right, db, rb) = sides
        return left, right, db - da, ra or rb

    def reference_root(self, sym):
        """ "ref1:context:X.Key" or "squad:context:Group" for a lookup result."""
        if sym[0] == "ref_squad":
            group = sym[1]
            parent = super().path(group) if group[0] == "load" else None
            if parent is None or parent[1] != REFERENCE_LOOKUPS["squad"][2][0]:
                return None
            return "squad:" + self.root_name(parent)
        key = sym[1]
        parent = self.path(key[2])
        if parent is None:
            return None
        root, owner, names = parent
        owners = self.extends if root == "extend" and owner is None else [owner]
        for candidate in owners:
            found = Namer.field(self, candidate, key[3])
            if found and found[1] == TARGET_ACCESS_KEY:
                prefix = [candidate] if root == "extend" and owner is None else []
                return f"ref{sym[2]}:" + self.root_name(
                    (root, found[1], names + prefix + found[0])
                )
        return None

    def root_name(self, parent):
        root, _, names = parent
        if root == "context":
            return "context:" + _join(names)
        if root == "extend":
            return f"extend:{names[0]}." + _join(names[1:])
        return root + ("." + _join(names) if names else "")

    def leaf(self, sym):
        if sym[0] == "vcall":
            # A constant-returning virtual getter, named after its object.
            _, _, obj, method, returns = sym
            parent = self.path(obj)
            if parent is None:
                return None
            key = self.key((parent[0], returns, parent[2] + [method + "()"]))
            return None if key is None else ("key", key, returns)
        if sym[0] == "load" and sym[2][0] == "elem":
            found = self.element(sym)
            if found is None or self.field_size(found[1]) == "reference":
                return None
            key = self.key(found)
            return None if key is None else ("key", key, found[1])
        if sym[0] == "load" and sym[2][0] in ("ref_enemy", "ref_squad", "load"):
            parent = self.path(sym[2])
            if parent and parent[0].startswith(REFERENCE_PREFIXES):
                found = self.resolve(parent, sym[3])
                if found is None:
                    return None
                root, kind, names = found
                return ("key", root + "/" + _join(names), kind)
        return super().leaf(sym)

    def exists(self, sym):
        if sym[0] in ("ref_enemy", "ref_squad"):
            root = self.reference_root(sym)
            return None if root is None else root + EXISTS_SUFFIX
        return self._exists(sym)

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

    def _exists(self, sym):
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


_LOOKUP_CACHE = {}


def static_value(metadata, pe, used):
    """Callback for the executor: a global proven by a straight-line .cctor."""

    def value(type_name, sym, size):
        found = static_constant(
            metadata, pe, type_name, int(sym[1][len("_DAT_") :], 16), size
        )
        if found is None:
            return None
        if found[1] not in used:
            used.append(found[1])
        return found[0]

    return value


def constant_return(pe, address):
    """(value, length) of a body that is only ``mov eax, imm`` (or ``xor eax,
    eax``) and ``ret``; None for anything else."""
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    code = list(md.disasm(pe.read(address, 16), address, 2))
    if len(code) != 2 or code[1].mnemonic != "ret" or code[1].operands:
        return None
    first, ops = code[0], code[0].operands
    if (
        first.mnemonic == "mov"
        and ops[0].type == X86_OP_REG
        and first.reg_name(ops[0].reg) == "eax"
        and ops[1].type == X86_OP_IMM
    ):
        value = ops[1].imm & 0xFFFFFFFF
    elif (
        first.mnemonic == "xor"
        and ops[0].type == ops[1].type == X86_OP_REG
        and first.reg_name(ops[0].reg) == first.reg_name(ops[1].reg) == "eax"
    ):
        value = 0
    else:
        return None
    return _to_signed(value, 32), code[1].address + code[1].size - address


def virtual_method(metadata, pe, namer, used):
    """Callback for the executor: a virtual getter answered by constants.

    The object's declared type comes from its metadata path; the slot gives
    the method by ``vtable_index`` (``VTABLE_METHODS_OFFSET``). Every
    implementation in the type, its ancestors and all subclasses must be
    ``mov eax, imm; ret``, so the call returns a value fixed by the object's
    runtime class. Anything else leaves the call unsupported.
    """

    def value(obj, slot):
        index, rest = divmod(slot - VTABLE_METHODS_OFFSET, 8)
        parent = namer.path(obj) if index >= 0 and not rest else None
        declared = parent[1] if parent else None
        if not declared:
            return None
        chain, name = [], None
        while declared and declared not in chain:
            chain.append(declared)
            declared = (metadata.get(declared) or {}).get("parent")
        found = []
        for owner in chain + metadata.subclasses(chain[0]):
            for method, info in (
                (metadata.get(owner) or {}).get("methods") or {}
            ).items():
                if info.get("vtable_index") != index:
                    continue
                if name not in (None, method.rstrip("0123456789")):
                    return None
                name = method.rstrip("0123456789")
                returns = info.get("returns", {}).get("type")
                if info.get("function") and int(info["function"], 16):
                    found.append((owner, int(info["function"], 16)))
        size = namer.field_size(returns) if name else None
        if not found or type(size) is not int or size > 4:
            return None
        implementations = []
        for owner, address in found:
            answer = constant_return(pe, address)
            if answer is None:
                return None
            implementations.append(
                dict(
                    type=owner,
                    address=hex(address),
                    end=hex(address + answer[1]),
                    value=answer[0],
                )
            )
        record = dict(declaredType=chain[0], method=name, slot=hex(slot))
        record["implementations"] = implementations
        if record not in used:
            used.append(record)
        overrides = [
            (int(i["address"], 16), int(i["end"], 16)) for i in implementations
        ]
        return ("vcall", size, obj, name, returns), overrides

    return value


def reference_lookups(metadata):
    """Address -> kind of each REFERENCE_LOOKUPS method in this build."""
    key = id(metadata)
    if key not in _LOOKUP_CACHE:
        found = {}
        for kind, (owner, name, params, returns) in REFERENCE_LOOKUPS.items():
            for method, info in (
                (metadata.get(owner) or {}).get("methods") or {}
            ).items():
                if (
                    method.rstrip("0123456789") == name
                    and tuple(p["type"] for p in info.get("params", [])) == params
                    and info.get("returns", {}).get("type") == returns
                    and info.get("function")
                ):
                    found[int(info["function"], 16)] = kind
        _LOOKUP_CACHE[key] = found
    return _LOOKUP_CACHE[key]


def unknown_unnamed(sym, namer):
    """Partial mode: a single comparison that cannot be named becomes unknown.

    The other atoms keep their names; the formula still says which part of
    the decision is not verified instead of dropping the whole command.
    """
    kind = sym[0]
    if kind in ("and", "or"):
        return b_join(kind, tuple(unknown_unnamed(x, namer) for x in sym[1]))
    if kind == "not":
        return b_not(unknown_unnamed(sym[1], namer))
    if kind in ("cmp", "isa", "bool_bit", "bits"):
        try:
            _expression(sym, namer)
        except Unsupported as error:
            return ("unknown", f"比较对象无法按元数据命名（{error}），结果未核实")
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
        namer = NativeNamer(
            metadata, row, ("param", "param_3"), ("param", "param_4"), pe
        )
        statics, virtuals = [], []
        formula, helpers, unknown_paths = evaluate(
            pe,
            int(row["address"], 16),
            partial,
            namer.argument_domain,
            reference_lookups(metadata),
            static_value(metadata, pe, statics),
            virtual_method(metadata, pe, namer, virtuals),
        )
        formula = resolve_statics(formula, namer, metadata, pe, statics)
        formula = split_wide(formula, namer)
        if partial:
            formula = unknown_unnamed(formula, namer)
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
    # Getters that name native fields; their bytes are verified like helpers.
    inlined += [g for g in namer.getters if g not in inlined]
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
        virtualMethods=virtuals,
        unknownPaths=unknown_paths,
        semanticStatus=(
            "native_x64_field_formula_partial"
            if unknown_paths or expression_unknown(expression)
            else "native_x64_field_formula_recovered"
        ),
    )
