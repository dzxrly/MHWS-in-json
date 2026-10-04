"""Recover individual self-Extend writes; do not assert complete command effects."""

import re

OBJECT_FIELD = r"\*\((?:int|uint|char|undefined[148]) \*\)\((?P<{prefix}cast>\(longlong\))?(?P<{prefix}object>puVar\d+) \+ (?P<{prefix}offset>0x[0-9a-f]+)\)"
EDIT_FIELD = r"\*\((?:int|uint|char|undefined[148]) \*\)\(\*\(longlong \*\)\(param_4 \+ (?P<argumentoffset>0x[0-9a-f]+)\) \+ 0x10\)"


def recover_writes(row, code, metadata):
    owner = re.match(r"app\.(?:btable\.)?(Em\d{4}_\d{2})BTableCommand\.", row["type"])
    if owner is None:
        return []
    text = re.sub(r"\s+", " ", code.replace("\r", ""))
    holder = re.search(
        r"(puVar\d+) = \*\(undefined8 \*\*\)\(\*\(longlong \*\)\(\*\(longlong \*\)\(param_3 \+ 0x28\) \+ 0x78\) \+ 0x10\)",
        text,
    )
    if holder is None:
        holder = re.search(
            r"(puVar\d+) = \*\(undefined8 \*\*\)\(\*\(longlong \*\)\(param_3\[5\] \+ 0x78\) \+ 0x10\)",
            text,
        )
    if holder is None:
        return []
    layouts = []
    for name in [f"app.c{owner[1]}Extend", f"app.c{owner[1].split('_')[0]}Extend"]:
        for field, definition in metadata.fields(name).items():
            if (
                definition.get("offset_from_base")
                and "default" not in definition
                and field != "Null"
            ):
                layouts.append((name, field, definition))

    def field_at(offset):
        choices = [
            dict(
                contextType=name,
                field=field,
                fieldType=definition["type"],
                offset=hex(offset),
            )
            for name, field, definition in layouts
            if int(definition["offset_from_base"], 16) == offset
        ]
        return choices[0] if len(choices) == 1 else None

    destination = OBJECT_FIELD.format(prefix="destination")
    source = OBJECT_FIELD.format(prefix="source")
    pattern = (
        destination
        + r" = (?P<value>"
        + source
        + "|"
        + EDIT_FIELD
        + r"|(?:0x[0-9a-f]+|\d+)|'\\0');"
    )
    effects = []
    for match in re.finditer(pattern, text):
        if match["destinationobject"] != holder[1]:
            continue
        offset = int(match["destinationoffset"], 16) * (
            1 if match["destinationcast"] else 8
        )
        destination_field = field_at(offset)
        if destination_field is None:
            continue
        if match["sourceobject"]:
            if match["sourceobject"] != holder[1]:
                continue
            source_field = field_at(
                int(match["sourceoffset"], 16) * (1 if match["sourcecast"] else 8)
            )
            if (
                source_field is None
                or source_field["fieldType"] != destination_field["fieldType"]
            ):
                continue
            value = dict(kind="self_extend_field", **source_field)
        elif match["argumentoffset"]:
            parameters = row.get("parameters") or []
            if len(parameters) < 2:
                continue
            argument_type = parameters[-1]["type"]
            fields = [
                field
                for field, definition in metadata.fields(argument_type).items()
                if field != "Null"
                and "default" not in definition
                and definition.get("offset_from_base") == match["argumentoffset"]
            ]
            if len(fields) != 1:
                continue
            value = dict(
                kind="resource_argument_field",
                argumentType=argument_type,
                field=fields[0],
            )
        else:
            value = dict(
                kind="constant",
                value=0 if match["value"] == "'\\0'" else int(match["value"], 0),
            )
        effects.append(
            dict(
                destination=destination_field,
                value=value,
                nativeExpression=match[0],
                evidence={
                    key: row[key]
                    for key in ("type", "method", "address", "end", "nativeSha256")
                },
                semanticStatus="individual_native_field_write_recovered",
                guard="执行到原生实现的该写入分支；对象有效性、类型检查、其他条件与副作用保留在实现中",
            )
        )
    return effects
