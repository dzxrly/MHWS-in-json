"""Recover commands that only combine plain field reads into one formula.

Many command ``onExecute`` bodies read a few fields of cEnemyContext modules,
the monster's own Extend or the resource argument, compare them with
constants or the argument, and return the combination. This module evaluates
the Ghidra pseudo-C of such a body symbolically:

- statements: declarations, assignments, ``if``/``else`` blocks and ``return``;
- expressions: pointer arithmetic, typed loads, comparisons, ``&&``, ``||``,
  ``!``, casts and ``CONCATxy`` (whose low part carries the returned bool).

Anything else (a call, loop, goto, switch, array index by a variable or a
comparison with a non-type global) rejects the whole command, which then stays
unknown. Every path's condition is kept, so the result is exact for the
recognised subset; loads are side-effect free, so assignments made inside
short-circuit operands are safe to keep.

Loads are named by the matched IL2CPP metadata: the command work's accessor
(+0x28) leads to the target context holder (+0x68) and cEnemyContext (+0x40),
or to the self Extend holder (+0x78) and its value (+0x10); the argument's edit
fields are ``*(param_4 + field) + 0x10``.
"""

from dataclasses import dataclass
import re

from ..config import (
    ACCESSOR_TARGET_CONTEXT,
    COMMAND_WORK_ACCESSOR,
    CONTEXT_ARRAY_INDEX_ENUMS,
    CONTEXT_KEY_ALIASES,
    EDIT_FIELD_VALUE,
    ENEMY_CONTEXT_TYPE,
    EXTEND_HOLDER,
    FN_STACK_COOKIE_CHECK,
    TARGET_CONTEXT_ENEMY,
    extend_types,
)
from ..native.evidence import evidence

EXTEND_VALUE = 0x10
# IL2CPP array header before element 0, and primitive element sizes.
ARRAY_DATA = 0x20
ARRAY_ELEMENT_SIZES = {
    "System.Boolean": 1,
    "System.Byte": 1,
    "System.SByte": 1,
    "System.Int16": 2,
    "System.UInt16": 2,
    "System.Int32": 4,
    "System.UInt32": 4,
    "System.Single": 4,
}
TYPE_SIZES = {
    "undefined": 1,
    "undefined1": 1,
    "char": 1,
    "uchar": 1,
    "byte": 1,
    "bool": 1,
    "undefined2": 2,
    "short": 2,
    "ushort": 2,
    "undefined4": 4,
    "int": 4,
    "uint": 4,
    "float": 4,
    "undefined8": 8,
    "longlong": 8,
    "ulonglong": 8,
    "double": 8,
    "code": 8,
}
TYPE_WORD = re.compile(
    r"(?:undefined\d?|u?longlong|u?int\d?|u?char|byte|bool|float|double|u?short|code|void)$"
)
TOKEN = re.compile(
    r"\s+|/\*.*?\*/|'(?:\\.|[^'])'|0x[0-9a-fA-F]+|\d+\.\d+(?:[eE][-+]?\d+)?|\d+"
    r"|[A-Za-z_]\w*|==|!=|<=|>=|&&|\|\||<<|>>|[-+*/%&|^!~<>=(){}\[\];,?:]",
    re.S,
)


class Unsupported(Exception):
    """The body leaves the recognised subset."""


@dataclass(frozen=True)
class Val:
    """A symbolic value; ``scale`` is the element size when it is a pointer."""

    sym: tuple
    scale: int = 0


def const(value):
    return Val(("const", value))


def _tokens(text):
    out, at = [], 0
    while at < len(text):
        match = TOKEN.match(text, at)
        if match is None:
            raise Unsupported("无法识别的记号：" + text[at : at + 20])
        at = match.end()
        token = match[0]
        if not token.isspace() and not token.startswith("/*"):
            out.append(token)
    return out


# ------------------------------------------------------------ boolean algebra


def b_not(x):
    if x[0] == "const":
        return ("const", not x[1])
    if x[0] == "not":
        return x[1]
    if x[0] == "cmp":
        flip = {"==": "!=", "!=": "==", "<": ">=", ">=": "<", ">": "<=", "<=": ">"}
        return ("cmp", flip[x[1]], x[2], x[3])
    return ("not", x)


def b_join(kind, items):
    joined = _join_items(kind, items)
    if joined[0] != kind:
        return joined
    parts = list(joined[1])
    # Common factor: (a & x) | (b & x) -> x & (a | b), and dually.
    other = "or" if kind == "and" else "and"
    groups = [p[1] if p[0] == other else (p,) for p in parts]
    common = [x for x in groups[0] if all(x in g for g in groups[1:])]
    if common:
        rests = [
            _join_items(other, tuple(x for x in g if x not in common)) for g in groups
        ]
        return b_join(other, (*common, b_join(kind, rests)))
    # Absorption: in a | (!a & b) the !a is implied, likewise a & (!a | b).
    changed = False
    for index, part in enumerate(parts):
        if part[0] != other:
            continue
        kept = tuple(x for x in part[1] if b_not(x) not in parts)
        if len(kept) != len(part[1]):
            parts[index] = _join_items(other, kept)
            changed = True
    return _join_items(kind, parts) if changed else joined


def _join_items(kind, items):
    unit, zero = (True, False) if kind == "and" else (False, True)
    out = []
    for item in items:
        if item[0] == "const":
            if bool(item[1]) == zero:
                return ("const", zero)
            continue
        for part in item[1] if item[0] == kind else (item,):
            if part not in out:
                out.append(part)
    if not out:
        return ("const", unit)
    return out[0] if len(out) == 1 else (kind, tuple(out))


def truthy(v):
    s = v.sym
    if s[0] in ("cmp", "and", "or", "not"):
        return s
    if s[0] == "const":
        return ("const", bool(s[1]))
    return ("cmp", "!=", s, ("const", 0))


# ------------------------------------------------------------------- parser


class Body:
    def __init__(self, code):
        text = code.replace("\r", "")
        start = text.find("{")
        header = text[:start]
        self.params = {}
        for kind, stars, name in re.findall(r"(\w+)\s*(\**)\s*(param_\d+)\b", header):
            scale = TYPE_SIZES.get(kind, 8) if stars else 0
            self.params[name] = Val(("param", name), scale)
        self.tokens = _tokens(text[start:])
        self.at = 0
        self.types = {}
        # Stack-cookie buffers: opaque values that only feed the cookie check.
        self.arrays = set()
        # label -> the rest of its block after the label.
        self.labels = {}
        self.cookie_check = f"FUN_{FN_STACK_COOKIE_CHECK:x}"

    # token helpers
    def peek(self, offset=0):
        index = self.at + offset
        return self.tokens[index] if index < len(self.tokens) else None

    def take(self, expected=None):
        token = self.peek()
        if token is None or (expected is not None and token != expected):
            raise Unsupported(f"期望 {expected}，实际 {token}")
        self.at += 1
        return token

    def type_at(self, index):
        """Length and scale of a type spelled from token ``index``, or None."""
        token = self.tokens[index] if index < len(self.tokens) else None
        if token is None or not TYPE_WORD.match(token):
            return None
        stars, j = 0, index + 1
        while j < len(self.tokens) and self.tokens[j] == "*":
            stars, j = stars + 1, j + 1
        return j - index, token, stars

    # statements
    def block(self):
        self.take("{")
        statements, labels = [], []
        while self.peek() != "}":
            statement = self.statement()
            if statement is None:
                continue
            if statement[0] == "call":
                # A call is allowed only right before Ghidra's int3 trap: it
                # does not return (e.g. a null-reference throw).
                if not self.trap_follows():
                    raise Unsupported("函数调用：" + statement[1])
                statement = ("trap",)
            if statement[0] == "label":
                labels.append((statement[1], len(statements)))
                continue
            statements.append(statement)
        self.take("}")
        for name, index in labels:
            self.labels[name] = statements[index:]
        return statements

    def trap_follows(self):
        """Consume ``x = (code *)swi(3); [y = (*x)();] return y;`` if present."""
        tokens = self.tokens[self.at : self.at + 9]
        if len(tokens) < 9 or tokens[1:8] != ["=", "(", "code", "*", ")", "swi", "("]:
            return False
        if tokens[8] != "3":
            return False
        depth = 0
        while self.peek() is not None:
            token = self.take()
            if token == "{":
                depth += 1
            elif token == "}":
                if depth == 0:
                    self.at -= 1
                    return True
                depth -= 1
            elif token == "return" and depth == 0:
                while self.take() != ";":
                    pass
                return True
        return False

    def statement(self):
        token = self.peek()
        if token == "{":
            return ("block", self.block())
        if token == "if":
            self.take()
            self.take("(")
            condition = self.expression()
            self.take(")")
            then = self.statement()
            otherwise = None
            if self.peek() == "else":
                self.take()
                otherwise = self.statement()
            return ("if", condition, then, otherwise)
        if token == "return":
            self.take()
            value = self.expression()
            self.take(";")
            return ("return", value)
        if token == "goto":
            self.take()
            name = self.take()
            self.take(";")
            return ("goto", name)
        if re.match(r"[A-Za-z_]\w*$", token or "") and self.peek(1) == ":":
            self.at += 2
            return ("label", token)
        if re.match(r"[A-Za-z_]\w*$", token or "") and self.peek(1) == "(":
            name = self.take()
            depth = 0
            while True:
                part = self.take()
                depth += part == "("
                depth -= part == ")"
                if depth == 0:
                    break
            self.take(";")
            return None if name == self.cookie_check else ("call", name)
        declared = self.type_at(self.at)
        if declared and re.match(r"[A-Za-z_]\w*$", self.peek(declared[0]) or ""):
            length, kind, stars = declared
            name = self.tokens[self.at + length]
            self.at += length + 1
            if self.peek() == "[":
                self.take("[")
                self.take()
                self.take("]")
                self.arrays.add(name)
            self.take(";")
            self.types[name] = TYPE_SIZES.get(kind, 8) if stars else 0
            return None
        if re.match(r"[A-Za-z_]\w*$", token or "") and self.peek(1) == "=":
            name = self.take()
            self.take("=")
            value = self.expression()
            self.take(";")
            return ("assign", name, value)
        raise Unsupported("不支持的语句：" + str(token))

    # expressions (as trees evaluated later)
    BINARY = [
        ("||",),
        ("&&",),
        ("|",),
        ("^",),
        ("&",),
        ("==", "!="),
        ("<", "<=", ">", ">="),
        ("<<", ">>"),
        ("+", "-"),
        ("*", "/", "%"),
    ]

    def expression(self):
        items = [self.assignment()]
        while self.peek() == ",":
            self.take()
            items.append(self.assignment())
        return items[0] if len(items) == 1 else ("comma", items)

    def assignment(self):
        if re.match(r"[A-Za-z_]\w*$", self.peek() or "") and self.peek(1) == "=":
            name = self.take()
            self.take("=")
            return ("assign", name, self.assignment())
        return self.binary(0)

    def binary(self, level):
        if level == len(self.BINARY):
            return self.unary()
        left = self.binary(level + 1)
        while self.peek() in self.BINARY[level]:
            operator = self.take()
            left = ("bin", operator, left, self.binary(level + 1))
        return left

    def unary(self):
        token = self.peek()
        if token in ("!", "-", "~", "*"):
            self.take()
            return ("unary", token, self.unary())
        if token == "&":
            raise Unsupported("取地址")
        if token == "(":
            declared = self.type_at(self.at + 1)
            if declared and self.peek(declared[0] + 1) == ")":
                length, kind, stars = declared
                self.at += length + 2
                return ("cast", kind, stars, self.unary())
        return self.postfix()

    def postfix(self):
        node = self.primary()
        while self.peek() in ("[", "("):
            if self.take() == "[":
                index = self.expression()
                self.take("]")
                node = ("index", node, index)
            else:
                if node[0] != "name" or not re.match(r"CONCAT\d\d$", node[1]):
                    raise Unsupported("函数调用")
                args = [self.assignment()]
                while self.peek() == ",":
                    self.take()
                    args.append(self.assignment())
                self.take(")")
                if len(args) != 2:
                    raise Unsupported("CONCAT 参数")
                node = ("concat", args[1])
        return node

    def primary(self):
        token = self.take()
        if token == "(":
            node = self.expression()
            self.take(")")
            return node
        if token.startswith("'"):
            body = token[1:-1]
            if body == "\\0":
                return ("num", 0)
            if len(body) == 1:
                return ("num", ord(body))
            raise Unsupported("字符常量")
        if re.match(r"0x[0-9a-fA-F]+$|\d+$", token):
            return ("num", int(token, 0))
        if re.match(r"\d+\.\d+", token):
            return ("num", float(token))
        if token in ("true", "false"):
            return ("num", token == "true")
        if re.match(r"[A-Za-z_]\w*$", token):
            return ("name", token)
        raise Unsupported("表达式：" + token)


# --------------------------------------------------------------- evaluation


class Evaluator:
    def __init__(self, body):
        self.body = body
        self.jumps = 0
        self.steps = 0

    def value(self, node, env):
        kind = node[0]
        if kind == "num":
            return const(node[1])
        if kind == "name":
            name = node[1]
            if name in env:
                return env[name]
            if name in self.body.params:
                return self.body.params[name]
            if name in self.body.arrays:
                return Val(("opaque",))
            if name.startswith(("_DAT_", "DAT_")):
                return Val(("global", name))
            raise Unsupported("未赋值的变量：" + name)
        if kind == "comma":
            result = None
            for item in node[1]:
                result = self.value(item, env)
            return result
        if kind == "assign":
            value = self.value(node[2], env)
            scale = self.body.types.get(node[1])
            env[node[1]] = value if scale is None else Val(value.sym, scale)
            return env[node[1]]
        if kind == "concat":
            return self.value(node[1], env)
        if kind == "cast":
            inner = self.value(node[3], env)
            if node[2]:
                return Val(inner.sym, TYPE_SIZES.get(node[1], 8))
            return Val(inner.sym, 0)
        if kind == "index":
            base = self.value(node[1], env)
            index = self.value(node[2], env)
            if index.sym[0] != "const" or not base.scale:
                raise Unsupported("变量索引")
            return self.load(base.scale, self.offset(base, index.sym[1] * base.scale))
        if kind == "unary":
            operator, inner = node[1], node[2]
            if operator == "*":
                if inner[0] == "cast" and inner[2]:
                    address = self.value(inner[3], env)
                    size = TYPE_SIZES.get(inner[1], 8) if inner[2] == 1 else 8
                    loaded = self.load(size, self.offset(Val(address.sym, 0), 0))
                    scale = TYPE_SIZES.get(inner[1], 8) if inner[2] > 1 else 0
                    return Val(loaded.sym, scale)
                pointer = self.value(inner, env)
                if not pointer.scale:
                    raise Unsupported("解引用非指针")
                return self.load(pointer.scale, self.offset(pointer, 0))
            value = self.value(inner, env)
            if operator == "!":
                return Val(b_not(truthy(value)))
            if operator == "-" and value.sym[0] == "const":
                return const(-value.sym[1])
            raise Unsupported("一元运算 " + operator)
        if kind == "bin":
            operator, left, right = node[1], node[2], node[3]
            if operator in ("&&", "||"):
                a = truthy(self.value(left, env))
                local = dict(env)
                b = truthy(self.value(right, local))
                # The right operand may not run: what it assigns is unusable.
                for name, value in local.items():
                    if env.get(name) != value:
                        env[name] = Val(("opaque",))
                return Val(b_join("and" if operator == "&&" else "or", (a, b)))
            a, b = self.value(left, env), self.value(right, env)
            if operator in ("==", "!=", "<", "<=", ">", ">="):
                return Val(("cmp", operator, a.sym, b.sym))
            if operator == "+" and b.sym[0] == "const" and type(b.sym[1]) is int:
                return self.offset(a, b.sym[1] * (a.scale or 1))
            if operator == "-" and b.sym[0] == "const" and type(b.sym[1]) is int:
                return self.offset(a, -b.sym[1] * (a.scale or 1))
            if (
                operator == "&"
                and b.sym[0] == "const"
                and type(b.sym[1]) is int
                and b.sym[1] >= 0xFF
                and a.sym[0] in ("cmp", "and", "or", "not", "const")
            ):
                return a
            # Other arithmetic only feeds CONCAT's unused high part; it fails
            # later if a comparison or a returned bool actually uses it.
            return Val(("opaque",))
        raise Unsupported("表达式种类 " + kind)

    @staticmethod
    def offset(value, delta):
        sym = value.sym
        if sym[0] == "addr":
            return Val(("addr", sym[1], sym[2] + delta), value.scale)
        if sym[0] == "const":
            raise Unsupported("常量地址")
        return Val(("addr", sym, delta), value.scale)

    @staticmethod
    def load(size, address):
        sym = address.sym
        base, off = (sym[1], sym[2]) if sym[0] == "addr" else (sym, 0)
        return Val(("load", size, base, off))

    def branch(self, node, env, yes, no):
        """Formula of a test with C short-circuit order.

        ``yes``/``no`` continue with the variables as they are after the
        operands that actually ran, so an assignment inside a skipped operand
        never reaches the other path.
        """
        self.steps += 1
        if self.steps > 4000:
            raise Unsupported("分支过多")
        kind = node[0]
        if kind == "bin" and node[1] == "&&":
            return self.branch(
                node[2], env, lambda e: self.branch(node[3], e, yes, no), no
            )
        if kind == "bin" and node[1] == "||":
            return self.branch(
                node[2], env, yes, lambda e: self.branch(node[3], e, yes, no)
            )
        if kind == "unary" and node[1] == "!":
            return self.branch(node[2], env, no, yes)
        if kind in ("concat",):
            return self.branch(node[1], env, yes, no)
        if kind == "cast":
            return self.branch(node[3], env, yes, no)
        if kind == "comma":
            local = dict(env)
            for item in node[1][:-1]:
                self.value(item, local)
            return self.branch(node[1][-1], local, yes, no)
        if (
            kind == "bin"
            and node[1] == "&"
            and node[3][0] == "num"
            and node[3][1] >= 0xFF
        ):
            # Masking a returned bool to its register width keeps its truth.
            return self.branch(node[2], env, yes, no)
        local = dict(env)
        test = truthy(self.value(node, local))
        then, otherwise = yes(dict(local)), no(dict(local))
        if then == otherwise:
            return then
        return b_join(
            "or",
            (b_join("and", (test, then)), b_join("and", (b_not(test), otherwise))),
        )

    def run(self, statements, env):
        """The formula that the statements return true."""
        for index, statement in enumerate(statements):
            kind = statement[0]
            if kind == "assign":
                self.value(("assign", statement[1], statement[2]), env)
            elif kind == "block":
                return self.run(statement[1] + statements[index + 1 :], env)
            elif kind == "return":
                return self.branch(
                    statement[1],
                    env,
                    lambda e: ("const", True),
                    lambda e: ("const", False),
                )
            elif kind == "trap":
                return ("const", False)
            elif kind == "goto":
                if statement[1] not in self.body.labels or self.jumps > 16:
                    raise Unsupported("跳转")
                self.jumps += 1
                return self.run(self.body.labels[statement[1]], env)
            elif kind == "if":
                rest = statements[index + 1 :]
                otherwise = [statement[3]] if statement[3] else []
                return self.branch(
                    statement[1],
                    env,
                    lambda e: self.run([statement[2]] + rest, e),
                    lambda e: self.run(otherwise + rest, e),
                )
        raise Unsupported("路径没有返回值")


def evaluate(code):
    """The boolean formula over symbolic loads returned by ``code``."""
    body = Body(code)
    statements = body.block()
    if body.peek() is not None:
        raise Unsupported("函数体之后还有内容")
    return Evaluator(body).run(statements, {}), body.params


# -------------------------------------------------------------- semantics


class Namer:
    """Name symbolic loads by metadata, rooted at the command work."""

    def __init__(self, metadata, row, work, argument):
        self.metadata = metadata
        self.row = row
        self.work = work
        self.argument = argument
        owner = re.match(
            r"app\.(?:btable\.)?(Em\d{4}_\d{2})BTableCommand\.", row["type"]
        )
        self.extends = extend_types(owner[1]) if owner else []
        self.enums = {}
        self.argument_fields = []

    def accessor(self, sym):
        return sym == ("load", 8, self.work, COMMAND_WORK_ACCESSOR)

    def holder(self, sym):
        return (
            sym[0] == "load"
            and sym[3] == ACCESSOR_TARGET_CONTEXT
            and self.accessor(sym[2])
        )

    def context(self, sym):
        return (
            sym[0] == "load" and sym[3] == TARGET_CONTEXT_ENEMY and self.holder(sym[2])
        )

    def extend(self, sym):
        return (
            sym[0] == "load"
            and sym[3] == EXTEND_VALUE
            and sym[2][0] == "load"
            and sym[2][3] == EXTEND_HOLDER
            and self.accessor(sym[2][2])
        )

    def field(self, owner, offset):
        if owner.endswith("[]"):
            # A constant index into an array of one primitive element type.
            element = owner[:-2]
            size = ARRAY_ELEMENT_SIZES.get(element)
            index, rest = divmod(offset - ARRAY_DATA, size or 1)
            if size is None or offset < ARRAY_DATA or rest:
                return None
            return [f"[{index}]"], element
        rows = [
            (name, d)
            for name, d in self.metadata.fields(owner).items()
            if name != "Null"
            and "default" not in d
            and d.get("offset_from_base") == hex(offset)
        ]
        if len(rows) > 1:
            rows = [r for r in rows if not re.fullmatch(r"[A-Z][A-Z0-9_]*", r[0])]
        if len(rows) == 1:
            return [rows[0][0]], rows[0][1]["type"]
        # A field inside a value-type struct (object header 0x10 not stored).
        for name, d in self.metadata.fields(owner).items():
            if (
                name == "Null"
                or "default" in d
                or re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
            ):
                continue
            record = self.metadata.get(d["type"]) or {}
            start = int(d.get("offset_from_base", "0x0"), 16)
            size = int(record.get("size", "0"), 16) - 0x10
            if (
                record.get("parent") == "System.ValueType"
                and start < offset < start + size
            ):
                inner = self.field(d["type"], offset - start + 0x10)
                if inner:
                    return [name] + inner[0], inner[1]
        return None

    def path(self, sym):
        """(root, owner type, field names) of an object pointer, or None."""
        if self.context(sym):
            return ("context", ENEMY_CONTEXT_TYPE, [])
        if self.extend(sym):
            return ("extend", None, [])
        if sym[0] != "load" or sym[1] != 8:
            return None
        parent = self.path(sym[2])
        if parent is None:
            return None
        found = self.resolve(parent, sym[3])
        return found

    def resolve(self, parent, offset):
        root, owner, names = parent
        if root == "extend" and owner is None:
            for extend in self.extends:
                found = self.field(extend, offset)
                if found:
                    return ("extend", found[1], [extend] + found[0])
            return None
        found = self.field(owner, offset)
        return (root, found[1], names + found[0]) if found else None

    def leaf(self, sym):
        """("key", key, type) for a named field load or ("arg", field, type)."""
        if sym[0] != "load":
            return None
        base = sym[2]
        if (
            sym[3] == EDIT_FIELD_VALUE
            and base[0] == "load"
            and base[1] == 8
            and base[2] == self.argument
        ):
            return self.argument_field(base[3])
        parent = self.path(base)
        if parent is None:
            return None
        found = self.resolve(parent, sym[3])
        if found is None:
            return None
        root, kind, names = found
        if root == "context":
            path = self.indexed(_join(names))
            interrupt = re.fullmatch(
                r"AIStateManager\._ExistInterruptResult\[(\d+)\]", path
            )
            if interrupt:
                return ("key", f"ai_interrupt_exists:{interrupt[1]}", kind)
            return ("key", CONTEXT_KEY_ALIASES.get(path, "context:" + path), kind)
        return ("key", f"extend:{names[0]}." + _join(names[1:]), kind)

    def indexed(self, path):
        """Spell a constant index of a known enum-indexed array by its name."""

        def name(match):
            values = self.metadata.enum(CONTEXT_ARRAY_INDEX_ENUMS[match[1]])[1]
            found = [k for k, v in values.items() if v == int(match[2])]
            return f"{match[1]}[{found[0]}]" if len(found) == 1 else match[0]

        if not CONTEXT_ARRAY_INDEX_ENUMS:
            return path
        pattern = (
            "(" + "|".join(map(re.escape, CONTEXT_ARRAY_INDEX_ENUMS)) + r")\[(\d+)\]"
        )
        return re.sub(pattern, name, path)

    def argument_field(self, offset):
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
        if len(names) != 1:
            return None
        if names[0] not in self.argument_fields:
            self.argument_fields.append(names[0])
        return ("arg", names[0], argument_type)

    def guard(self, sym):
        """Runtime keys for native existence and exact-type checks."""
        if sym == self.work:
            return "enemy_command_work_valid"
        if self.extend(sym):
            return "self_extend_valid"
        if self.holder(sym):
            return "self_target_context_valid"
        return None


def _join(names):
    """Field path text; array indices attach to the array field."""
    text = ""
    for name in names:
        text += name if name.startswith("[") or not text else "." + name
    return text


def _signed(value, size):
    if type(value) is int and size == 4 and value & 0x80000000:
        return value - (1 << 32)
    return value


def _expression(sym, namer):
    from .expressions import combined, invert, runtime

    kind = sym[0]
    if kind == "const":
        return dict(kind="constant", value=bool(sym[1]))
    if kind in ("and", "or"):
        items = []
        for item in (_expression(x, namer) for x in sym[1]):
            if item not in items:
                items.append(item)
        return combined("all" if kind == "and" else "any", *items)
    if kind == "not":
        return invert(_expression(sym[1], namer))
    if kind != "cmp":
        raise Unsupported("非比较叶子")
    operator, left, right = sym[1], sym[2], sym[3]
    mirrored = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "==", "!=": "!="}
    # Exact type check of an object: *(object) == klass global.
    for a, b, op in ((left, right, operator), (right, left, mirrored[operator])):
        if (
            a[0] == "load"
            and a[1] == 8
            and a[3] == 0
            and b[0] == "global"
            and op in ("==", "!=")
        ):
            # ``*(longlong *)*object`` reads the class through the header.
            inner = a[2]
            key = None
            if inner[0] == "load" and inner[1] == 8 and inner[3] == 0:
                key = namer.guard(inner[2])
            key = key or namer.guard(inner)
            if key is None:
                raise Unsupported("未知对象的类型检查")
            test = runtime(key, "原生类型检查通过")
            return test if op == "==" else invert(test)
    for a, b, op in ((left, right, operator), (right, left, mirrored[operator])):
        if b == ("const", 0) and op in ("==", "!="):
            key = namer.guard(a)
            if key is not None:
                test = runtime(key, "对象存在")
                return test if op == "!=" else invert(test)
    for a, b, op in ((left, right, operator), (right, left, mirrored[operator])):
        named = namer.leaf(a)
        if named is None or named[0] != "key":
            continue
        key, field_type = named[1], named[2]
        size = a[1]
        names = namer.metadata.enum(field_type)[1]
        if names:
            namer.enums[key] = {
                n: _signed(v, size) for n, v in names.items() if n != "MAX"
            }
        if b[0] == "const":
            value = _signed(b[1], size)
            if field_type == "System.Boolean" and value == 0 and op in ("==", "!="):
                test = runtime(key, key.split(":", 1)[-1] + " 为真")
                return test if op == "!=" else invert(test)
            if type(value) not in (int, float):
                raise Unsupported("常量类型")
            return dict(
                kind="compare",
                operator=LEAF_OPS[op],
                left=runtime(key, key.split(":", 1)[-1]),
                right=dict(kind="constant", value=value),
            )
        other = namer.leaf(b)
        if other is not None and other[0] == "arg":
            return dict(
                kind="compare",
                operator=LEAF_OPS[op],
                left=runtime(key, key.split(":", 1)[-1]),
                right=dict(kind="argument", field=other[1]),
            )
        raise Unsupported("字段与非常量比较")
    raise Unsupported("无法命名的比较")


LEAF_OPS = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


def recover_formula_leaf(row, code, metadata):
    """A leaf rule ``kind=formula`` for a pure field-comparison command."""
    try:
        formula, params = evaluate(code)
        work = params.get("param_3")
        argument = params.get("param_4")
        if work is None:
            return None
        namer = Namer(metadata, row, work.sym, argument.sym if argument else None)
        expression = _expression(formula, namer)
    except Unsupported:
        return None
    if expression.get("kind") == "constant" or not _reads_state(expression):
        return None
    return dict(
        kind="formula",
        commandType=row["type"],
        argumentType=(
            (row.get("parameters") or [{}])[-1].get("type")
            if namer.argument_fields
            else None
        ),
        argumentField=namer.argument_fields[0] if namer.argument_fields else None,
        argumentFields=namer.argument_fields,
        contextFieldType=None,
        formula=expression,
        inputEnums=namer.enums,
        evidence=evidence(row),
        semanticStatus="native_field_formula_recovered",
    )


def _reads_state(expression):
    """True when the formula reads a field, not only existence/type guards."""
    kind = expression.get("kind")
    if kind in ("all", "any"):
        return any(_reads_state(x) for x in expression["items"])
    if kind == "not":
        return _reads_state(expression["item"])
    if kind == "compare":
        return True
    if kind == "runtime":
        return expression["key"].startswith(("context:", "extend:"))
    return False


def instantiate(formula, argument):
    """Replace argument references with this node's resource values."""
    from .values import enum_number, scalar

    if isinstance(formula, list):
        out = [instantiate(x, argument) for x in formula]
        return None if any(x is None for x in out) else out
    if not isinstance(formula, dict):
        return formula
    if formula.get("kind") == "argument":
        if argument is None or formula["field"] not in argument:
            return None
        raw = scalar(argument[formula["field"]])
        value = enum_number(raw) if isinstance(raw, str) else raw
        if type(value) not in (int, float, bool):
            return None
        return dict(kind="constant", value=value)
    out = {}
    for key, value in formula.items():
        item = instantiate(value, argument)
        if item is None and value is not None:
            return None
        out[key] = item
    return out
