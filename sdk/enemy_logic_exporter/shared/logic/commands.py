"""Recover narrow command comparisons and writes, and bind their annotations.

Unknown guards and additional effects remain explicit in the native evidence."""

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
from ..config import ROOT
import re
from ..native.evidence import evidence


def annotate_effects(annotation, catalog):
    if annotation["kind"] != "command":
        return
    name = (
        catalog.get("inheritedCommands", {})
        .get(annotation["commandType"], {})
        .get("implementationType", annotation["commandType"])
    )
    effects = []
    for record in catalog.get("commands", {}).get(name, []):
        for effect in record.get("recoveredWrites", []):
            effect = copy.deepcopy(effect)
            value = effect["value"]
            if value["kind"] == "resource_argument_field":
                if value["argumentType"] != annotation.get("argumentType") or value[
                    "field"
                ] not in annotation.get("argument", {}):
                    continue
                value["resourceValue"] = annotation["argument"][value["field"]]
            effects.append(effect)
    annotation["partialImplementationEffects"] = effects
    annotation["commandEffectsComplete"] = False
    if effects and not annotation.get("effectSummaryAdded"):
        summaries = []
        for effect in effects:
            value = effect["value"]
            source = (
                value["field"]
                if value["kind"] == "self_extend_field"
                else json.dumps(
                    (
                        value["resourceValue"]
                        if value["kind"] == "resource_argument_field"
                        else value["value"]
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            summaries.append(effect["destination"]["field"] + " ← " + source)
        annotation["summary"] += (
            "；执行到写入分支时：" + "；".join(summaries) + "（其他条件和副作用见实现）"
        )
        annotation["effectSummaryAdded"] = True


def enrich_existing(annotations, catalog_path):
    """Update only command effects; retain all native blocks and field bindings."""
    path = Path(annotations).resolve()
    root = ROOT
    if not path.is_relative_to(root / ".agents"):
        raise ValueError("注释更新只能写入 .agents")
    index = json.loads(path.read_text(encoding="utf8"))
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf8"))
    if index["profile"] != catalog["profile"]:
        raise ValueError("命令与注释来源不匹配")
    updated = Counter()
    for source, reference in index["resources"].items():
        resource_path = path.parent / reference["path"]
        raw = resource_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("注释摘要变化")
        resource = json.loads(raw)
        sites = 0
        for method in resource["methods"]:
            for annotation in method["annotations"]:
                annotate_effects(annotation, catalog)
                if annotation.get("partialImplementationEffects"):
                    sites += 1
        resource["counts"]["partial_field_write_command"] = sites
        resource_path.write_text(
            json.dumps(resource, ensure_ascii=False, separators=(",", ":")),
            encoding="utf8",
        )
        reference["sha256"] = hashlib.sha256(resource_path.read_bytes()).hexdigest()
        reference["counts"] = resource["counts"]
        updated.update(resource["counts"])
    index["counts"] = dict(updated)
    for monster in index["monsters"]:
        counts = Counter()
        for source in monster["resources"]:
            counts.update(index["resources"][source]["counts"])
        monster["counts"] = dict(counts)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf8")
    return index


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
        evidence=evidence(row),
        nativeExpression=match[0][:-2],
        semanticStatus="native_leaf_comparison_recovered",
    )
