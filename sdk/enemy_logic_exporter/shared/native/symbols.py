"""Resolve version-independent native identities to one build's addresses.

A symbol is declared once in ``config.SYMBOL_SPECS`` and resolved per game
version into ``data/profiles/<version>.json``:

* ``Method`` - an IL2CPP method found by type, name without its numeric
  suffix and, when overloaded, parameter types.
* ``Helper`` - an unnamed function found by its relocation-masked opening
  bytes, optionally restricted to direct callees of named anchor symbols.
* ``Reviewed`` - a global or constant carried from the previous profile and
  flagged for manual review whenever the build changes.

Every function also gets a relocation-insensitive ``normalizedSha256`` over
its whole body: internal branch targets become offsets, external call/jump
targets become stable identities (a named method's type, suffix-free name and
parameter types; otherwise the callee's own one-level digest), and RIP-relative
displacements become ``REL``. Equal digests mean the same code and the same
callees modulo layout, which lets evidence rows move to a new build. Static
data and jump-table contents behind ``REL`` are not covered.
"""

from dataclasses import dataclass
import hashlib
import re


@dataclass(frozen=True)
class Method:
    type: str
    name: str
    params: tuple = None


@dataclass(frozen=True)
class Helper:
    anchors: tuple = ()
    exclude: tuple = ()


@dataclass(frozen=True)
class Reviewed:
    note: str


PATTERN_LENGTHS = (24, 40, 64, 96, 128)
# Version of the normalized-digest rules; digests of different schemes never
# compare equal, so profiles from an older scheme must be regenerated.
DIGEST_SCHEME = 2
RIP_RELATIVE = re.compile(r"rip ([+-]) 0x[0-9a-f]+")


def method_stem(name):
    return re.sub(r"\d+$", "", name)


def _decoder():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    return decoder


def instructions(pe, start, end=None):
    end = end or pe.end(start)
    return list(_decoder().disasm(pe.read(start, end - start), start)), end


def _branch_target(ins):
    from capstone import CS_GRP_CALL, CS_GRP_JUMP, CS_OP_IMM

    if (ins.group(CS_GRP_CALL) or ins.group(CS_GRP_JUMP)) and ins.operands:
        operand = ins.operands[0]
        if operand.type == CS_OP_IMM:
            return operand.imm
    return None


def direct_callees(pe, start):
    body, end = instructions(pe, start)
    return {
        target
        for ins in body
        if (target := _branch_target(ins)) is not None
        and not start <= target < end
    }


class CallNames:
    """Stable, version-independent identities of external call targets."""

    def __init__(self, pe, metadata, catalog):
        self.pe, self.metadata, self.catalog = pe, metadata, catalog
        self.cache = {}

    def __call__(self, address):
        if address not in self.cache:
            aliases = self.catalog.get(address)
            if aliases:
                names = []
                for owner, method in aliases:
                    details = (self.metadata.get(owner) or {}).get("methods", {}).get(method, {})
                    params = ",".join(p.get("type", "") for p in details.get("params", []))
                    names.append(f"{owner}.{method_stem(method)}({params})")
                self.cache[address] = "M:" + "|".join(sorted(set(names)))
            else:
                # An unnamed callee is identified by its own body, one level deep.
                self.cache[address] = "H:" + normalized_digest(self.pe, address)[:16]
        return self.cache[address]


def normalized_digest(pe, start, end=None, names=None):
    """``names`` maps external targets to identities; without it they read EXT."""
    body, end = instructions(pe, start, end)
    lines = []
    for ins in body:
        target = _branch_target(ins)
        if target is not None:
            if start <= target < end:
                operand = f"+{target - start:#x}"
            else:
                operand = names(target) if names is not None else "EXT"
        else:
            operand = RIP_RELATIVE.sub(r"rip \1 REL", ins.op_str)
        lines.append(f"{ins.mnemonic} {operand}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def native_digest(pe, start, end):
    return hashlib.sha256(pe.read(start, end - start)).hexdigest()


def masked_pattern(pe, start, length):
    """Opening bytes with branch targets and RIP-relative displacements masked."""
    from capstone import CS_OP_MEM

    body, _ = instructions(pe, start)
    result = []
    for ins in body:
        raw = list(ins.bytes)
        if _branch_target(ins) is not None and ins.imm_size:
            for k in range(ins.imm_offset, ins.imm_offset + ins.imm_size):
                raw[k] = None
        if ins.disp_size and any(
            o.type == CS_OP_MEM and ins.reg_name(o.mem.base) == "rip"
            for o in ins.operands
        ):
            for k in range(ins.disp_offset, ins.disp_offset + ins.disp_size):
                raw[k] = None
        result.extend(raw)
        if len(result) >= length:
            break
    return "".join("??" if b is None else f"{b:02x}" for b in result)


def scan_pattern(pe, pattern):
    expression = re.compile(
        b"".join(
            b"." if pattern[i : i + 2] == "??" else re.escape(bytes.fromhex(pattern[i : i + 2]))
            for i in range(0, len(pattern), 2)
        ),
        re.S,
    )
    hits = []
    for virtual_size, virtual_address, raw_size, raw in pe.sections:
        for match in expression.finditer(pe.data, raw, raw + raw_size):
            hits.append(pe.base + virtual_address + match.start() - raw)
    return hits


def find_method(metadata, spec):
    record = metadata.get(spec.type) or {}
    matches = [
        (name, details)
        for name, details in record.get("methods", {}).items()
        if method_stem(name) == spec.name
        and (
            spec.params is None
            or tuple(p.get("type") for p in details.get("params", [])) == spec.params
        )
    ]
    if len(matches) != 1:
        raise ValueError(f"方法符号无法唯一定位：{spec.type}.{spec.name}（{len(matches)}）")
    name, details = matches[0]
    return name, int(details["function"], 16)


def _function_record(pe, address, names=None, **extra):
    end = pe.end(address)
    return dict(
        address=hex(address),
        end=hex(end),
        normalizedSha256=normalized_digest(pe, address, end, names),
        **extra,
    )


def _helper_candidates(pe, spec, pattern, resolved):
    hits = set(scan_pattern(pe, pattern)) if pattern else None
    for anchor in spec.anchors:
        callees = direct_callees(pe, int(resolved[anchor]["address"], 16))
        hits = callees if hits is None else hits & callees
    for name in spec.exclude:
        hits.discard(int(resolved[name]["address"], 16))
    return sorted(hits or ())


def _unique_pattern(pe, address, spec, resolved):
    for length in PATTERN_LENGTHS:
        pattern = masked_pattern(pe, address, length)
        if _helper_candidates(pe, spec, pattern, resolved) == [address]:
            return pattern
    raise ValueError(f"无法为辅助函数生成唯一特征：{address:#x}")


def resolve_symbols(specs, metadata, pe, previous, profile, names=None):
    """Resolve all specs; ``previous`` is the last reviewed profile document."""
    old = previous.get("symbols", {})
    resolved, report = {}, dict(moved=[], changed=[], review=[])
    order = sorted(specs, key=lambda n: {Method: 0, Helper: 1, Reviewed: 2}[type(specs[n])])
    for name in order:
        spec = specs[name]
        before = old.get(name, {})
        if isinstance(spec, Method):
            method, address = find_method(metadata, spec)
            record = _function_record(pe, address, names, type=spec.type, method=method)
        elif isinstance(spec, Helper):
            candidates = _helper_candidates(pe, spec, before.get("pattern"), resolved)
            if len(candidates) != 1:
                raise ValueError(f"辅助函数特征不唯一或失效：{name}（{len(candidates)}）")
            address = candidates[0]
            record = _function_record(
                pe, address, names, pattern=_unique_pattern(pe, address, spec, resolved)
            )
        else:
            if "value" not in before:
                raise ValueError(f"人工核对常量缺少上一版本取值：{name}")
            record = dict(value=before["value"], note=spec.note)
            if previous.get("profile", {}).get("exeSha256") != profile["exeSha256"]:
                report["review"].append(name)
        if before.get("address") not in (None, record.get("address")):
            report["moved"].append(name)
        if previous.get("digestScheme") == DIGEST_SCHEME and before.get(
            "normalizedSha256"
        ) not in (None, record.get("normalizedSha256")):
            report["changed"].append(name)
        resolved[name] = record
    return resolved, report


def evidence_rows(value, found=None):
    """Every native evidence row nested anywhere in a JSON document."""
    found = [] if found is None else found
    if isinstance(value, dict):
        if {"type", "method", "address", "end"} <= set(value):
            found.append(value)
        for item in value.values():
            evidence_rows(item, found)
    elif isinstance(value, list):
        for item in value:
            evidence_rows(item, found)
    return found


def evidence_key(row):
    return row["type"] + "::" + method_stem(row["method"])
