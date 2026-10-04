"""Recover a deliberately small class of direct Extend field comparisons.

Calls, additional field conditions, switches and arithmetic are not accepted.
The native context/type guards remain part of the contract.
"""

import re

FIELD = r"\*\((?:int|uint|char) \*\)\((?P<bytecast>\(longlong\))?(?P<object>puVar\d+) \+ (?P<offset>0x[0-9a-f]+)\)"
ARGUMENT = r"\*\((?:int|uint) \*\)\(\*\(longlong \*\)\(param_4 \+ (?P<argoffset>0x[0-9a-f]+)\) \+ 0x10\)"


def recover_leaf(row, code, metadata):
    owner = re.match(r"app\.(?:btable\.)?(Em\d{4}_\d{2})BTableCommand\.", row["type"])
    if owner is None:
        return None
    text = re.sub(r"\s+", " ", code.replace("\r", ""))
    body = text[text.find("{") :]
    if (
        re.search(r"\b(?:FUN_|func_0x|mhws_)[a-z0-9]+\s*\(", body)
        or "switch" in body
        or "else" in body
    ):
        return None
    # Only the standard self-Extend holder chain is admitted.
    if "0x78" not in body or (
        "param_3[5]" not in body and "param_3 + 0x28" not in body
    ):
        return None
    holder = re.search(
        r"(puVar\d+) = \*\(undefined8 \*\*\)\([^;]{0,220}?0x78[^;]{0,50}?0x10\)", body
    )
    if holder is None:
        return None
    match = re.search(
        FIELD
        + r" (?P<operator>==|!=|<=|>=|<|>) (?P<right>"
        + ARGUMENT
        + r"|0|'\\0')\);",
        body,
    )
    if match is None or match["object"] != holder[1]:
        return None
    # Reject additional comparisons on the same data field object, except the
    # repeated value in CONCAT's unused upper bits.
    comparisons = list(re.finditer(FIELD + r" (?:==|!=|<=|>=|<|>) ", body))
    if len(comparisons) != 1 or not re.search(
        r"return CONCAT(?:31|71)\([^;]+", body[: match.end()]
    ):
        return None
    offset = int(match["offset"], 16) * (1 if match["bytecast"] else 8)
    types = [f"app.c{owner[1]}Extend", f"app.c{owner[1].split('_')[0]}Extend"]
    choices = []
    for name in types:
        for field, definition in metadata.fields(name).items():
            if (
                definition.get("offset_from_base") == hex(offset)
                and "default" not in definition
                and field != "Null"
            ):
                choices.append((name, field, definition))
    if len(choices) != 1:
        return None
    context_type, field, definition = choices[0]
    arg_type = (
        row.get("parameters", [])[-1]["type"]
        if match["argoffset"] and row.get("parameters")
        else None
    )
    arg_field = None
    if arg_type:
        matches = [
            k
            for k, v in metadata.fields(arg_type).items()
            if k != "Null"
            and v.get("offset_from_base") == match["argoffset"]
            and "default" not in v
        ]
        if len(matches) != 1:
            return None
        arg_field = matches[0]
    return dict(
        commandType=row["type"],
        argumentType=arg_type,
        contextType=context_type,
        contextField=field,
        contextFieldType=definition["type"],
        contextOffset=hex(offset),
        operator=match["operator"],
        argumentField=arg_field,
        constant=0 if not arg_field else None,
        guard="原生工作与自身 Extend 对象有效，且通过原生类型检查",
        evidence={
            k: row[k] for k in ("type", "method", "address", "end", "nativeSha256")
        },
        nativeExpression=match[0][:-2],
        semanticStatus="native_leaf_comparison_recovered",
    )
