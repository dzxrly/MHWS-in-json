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
from ..config import (
    ACCESSOR_TARGET_CONTEXT,
    CLASS_HIERARCHY_CHECK_LABELS,
    COMMAND_WORK_ACCESSOR,
    EDIT_FIELD_VALUE,
    ENEMY_CONTEXT_TYPE,
    EXTEND_ACCESSOR_FIELD,
    EXTEND_BASE_TYPE,
    EXTEND_HOLDER,
    EXTEND_UNIQUE_STATE_FIELD,
    FN_UNIQUE_LEVEL,
    TARGET_CONTEXT_ENEMY,
    UNIQUE_LEVEL_LABELS,
    UNIQUE_LEVELED_MODULE_FIELD,
    extend_types,
)

# Ghidra pseudo-C spellings of the self-Extend holder chain and edit fields.
ACCESSOR_FIELD = f"{COMMAND_WORK_ACCESSOR:#x}"
HOLDER_FIELD = f"{EXTEND_HOLDER:#x}"
VALUE_FIELD = rf"{EDIT_FIELD_VALUE:#x}\)"


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
EDIT_FIELD = (
    r"\*\((?:int|uint|char|undefined[148]) \*\)\(\*\(longlong \*\)\(param_4 \+ (?P<argumentoffset>0x[0-9a-f]+)\) \+ "
    + VALUE_FIELD
)


def recover_writes(row, code, metadata):
    owner = re.match(r"app\.(?:btable\.)?(Em\d{4}_\d{2})BTableCommand\.", row["type"])
    if owner is None:
        return []
    text = re.sub(r"\s+", " ", code.replace("\r", ""))
    holder = re.search(
        r"(puVar\d+) = \*\(undefined8 \*\*\)\(\*\(longlong \*\)\(\*\(longlong \*\)\(param_3 \+ "
        + ACCESSOR_FIELD
        + r"\) \+ "
        + HOLDER_FIELD
        + r"\) \+ "
        + VALUE_FIELD,
        text,
    )
    if holder is None:
        holder = re.search(
            r"(puVar\d+) = \*\(undefined8 \*\*\)\(\*\(longlong \*\)\(param_3\[5\] \+ "
            + HOLDER_FIELD
            + r"\) \+ "
            + VALUE_FIELD,
            text,
        )
    if holder is None:
        return []
    layouts = []
    for name in extend_types(owner[1]):
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
                    key: row[key] for key in ("type", "method", "address", "end")
                },
                semanticStatus="individual_native_field_write_recovered",
                guard="执行到原生实现的该写入分支；对象有效性、类型检查、其他条件与副作用保留在实现中",
            )
        )
    return effects


FIELD = r"\*\((?:int|uint|char) \*\)\((?P<bytecast>\(longlong\))?(?P<object>puVar\d+) \+ (?P<offset>0x[0-9a-f]+|\d+)\)"
MIRRORED = {"==": "==", "!=": "!=", "<=": ">=", ">=": "<=", "<": ">", ">": "<"}
ARGUMENT = (
    r"\*\((?:int|uint) \*\)\(\*\(longlong \*\)\(param_4 \+ (?P<argoffset>0x[0-9a-f]+)\) \+ "
    + VALUE_FIELD
)


CLASS_CHECK = (
    r"\b(?:"
    + "|".join(CLASS_HIERARCHY_CHECK_LABELS)
    + r")\(\*\(undefined8 \*\)\*(puVar\d+),_DAT_[0-9a-f]+\)"
)
CONSTANT = r"-?(?:0x[0-9a-f]+|\d+)"
CALL = r"\b(?:FUN_|func_0x|mhws_)[a-z0-9]+\s*\("


def _int32(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def _holder(body):
    """The self-Extend holder variable and its type-checked alias, if any.

    ``if (*(longlong *)*holder == _DAT_x) { alias = holder; }`` leaves a null
    alias when the exact type check fails; the guard requires it to pass.
    """
    if HOLDER_FIELD not in body or (
        "param_3[5]" not in body and "param_3 + " + ACCESSOR_FIELD not in body
    ):
        return None
    holder = re.search(
        r"(puVar\d+) = \*\(undefined8 \*\*\)\([^;]{0,220}?"
        + HOLDER_FIELD
        + r"[^;]{0,50}?"
        + VALUE_FIELD,
        body,
    )
    if holder is None:
        return None
    names = {holder[1]}
    alias = re.search(
        r"if \(\*\(longlong \*\)\*"
        + holder[1]
        + r" == _DAT_[0-9a-f]+\) \{ (puVar\d+) = "
        + holder[1]
        + r"; \}",
        body,
    )
    if alias:
        names.add(alias[1])
    return holder[1], names


def recover_leaf(row, code, metadata, pe=None):
    owner = re.match(r"app\.(?:btable\.)?(Em\d{4}_\d{2})BTableCommand\.", row["type"])
    if owner is None:
        return None
    text = re.sub(r"\s+", " ", code.replace("\r", ""))
    body = text[text.find("{") :]
    # The class-hierarchy test is the runtime cast check of the holder.
    checked = [match[1] for match in re.finditer(CLASS_CHECK, body)]
    body = re.sub(CLASS_CHECK, r"CLASS_CHECK(\1)", body)
    found = _holder(body)
    if found is not None and any(name not in found[1] for name in checked):
        return None
    names = found[1] if found else set()
    special = recover_unique_level_leaf(row, body, metadata, owner[1], names, pe)
    if special is None and found is not None:
        special = recover_unique_state_leaf(row, body, metadata, names)
    if special is not None:
        return special
    if found is None or re.search(CALL, body) or "switch" in body or "else" in body:
        return None
    match = re.search(
        FIELD
        + r" (?P<operator>==|!=|<=|>=|<|>) (?P<right>"
        + ARGUMENT
        + r"|(?P<constant>"
        + CONSTANT
        + r")|'\\0')\)?;",
        body,
    )
    operator = match["operator"] if match else None
    if match is None:
        # Ghidra may print "argument OP field"; mirror the operator so the
        # recovered rule always reads "field OP argument".
        match = re.search(
            ARGUMENT + r" (?P<operator>==|!=|<=|>=|<|>) " + FIELD + r"\);", body
        )
        operator = match and MIRRORED[match["operator"]]
    if match is None or match["object"] not in names:
        return None
    # Reject additional comparisons on the same data field object, except the
    # repeated value in CONCAT's unused upper bits.
    comparisons = list(re.finditer(FIELD + r" (?:==|!=|<=|>=|<|>) ", body)) + list(
        re.finditer(r" (?:==|!=|<=|>=|<|>) " + FIELD, body)
    )
    # The boolean is returned through CONCAT's low byte or directly.
    if len(comparisons) != 1 or not (
        re.search(r"return CONCAT(?:31|71)\([^;]+", body[: match.end()])
        or body[: match.start()].endswith("return ")
    ):
        return None
    offset = int(match["offset"], 0) * (1 if match["bytecast"] else 8)
    types = extend_types(owner[1])
    choices = []
    for name in types:
        for field, definition in metadata.fields(name).items():
            if (
                definition.get("offset_from_base") == hex(offset)
                and "default" not in definition
                and field != "Null"
            ):
                choices.append((name, field, definition))
    # A subspecies Extend inherits the species fields; one field id is one field.
    choices = list(
        {
            definition.get("id", (n, f)): (n, f, definition)
            for n, f, definition in reversed(choices)
        }.values()
    )
    if len(choices) > 1:
        # The dump gives static fields offsets in their own storage, which can
        # coincide with instance fields; statics are UPPER_SNAKE constants.
        choices = [c for c in choices if not re.fullmatch(r"[A-Z][A-Z0-9_]*", c[1])]
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
        operator=operator,
        argumentField=arg_field,
        constant=(
            None
            if arg_field
            else int(match["constant"], 0) if match.groupdict().get("constant") else 0
        ),
        guard="原生工作与自身 Extend 对象有效，且通过原生类型检查",
        evidence=evidence(row),
        nativeExpression=re.sub(r"\)?;$", "", match[0]),
        semanticStatus="native_leaf_comparison_recovered",
    )


CONTEXT_ROOT = (
    r"\*\(longlong \*\)\(\*\(longlong \*\)\(param_3\[5\] \+ "
    + f"{ACCESSOR_TARGET_CONTEXT:#x}"
    + r"\) \+ "
    + f"{TARGET_CONTEXT_ENEMY:#x}"
    + r"\)"
)
CONTEXT_READ = (
    r"\*\((?P<cast>int|uint|char) \*\)\((?P<path>(?:\*\(longlong \*\)\()*"
    + CONTEXT_ROOT
    + r"(?: \+ (?:0x[0-9a-f]+|\d+)\))*) \+ (?P<last>0x[0-9a-f]+|\d+)\)"
)


def _context_path(metadata, path, last):
    """Resolve cEnemyContext -> module ... -> field by metadata offsets."""
    offsets = [int(v, 0) for v in re.findall(r"\+ (0x[0-9a-f]+|\d+)\)", path)][2:]
    owner, names = ENEMY_CONTEXT_TYPE, []
    for offset in offsets + [int(last, 0)]:
        fields = [
            (name, definition)
            for name, definition in metadata.fields(owner).items()
            if name != "Null"
            and "default" not in definition
            and definition.get("offset_from_base") == hex(offset)
        ]
        if len(fields) != 1:
            return None
        name, definition = fields[0]
        names.append(name)
        owner = definition["type"]
    return names, owner


def recover_context_leaf(row, code, metadata):
    """A command that only compares one cEnemyContext module field.

    The read follows Accessor -> target context -> cEnemyContext and then
    pointer fields resolved by the matched metadata; the comparison is with
    one resource argument field or a constant, with no helper calls.
    """
    # Ghidra wraps long expressions; drop spaces it leaves around parentheses.
    text = re.sub(r"\s+", " ", code.replace("\r", ""))
    text = re.sub(r"\*\) \(", "*)(", re.sub(r"\s+\)", ")", text))
    body = text[text.find("{") :]
    if re.search(CALL, body) or "switch" in body or "else" in body:
        return None
    reads = list(re.finditer(CONTEXT_READ, body))
    if len(reads) != 1:
        return None
    read = reads[0]
    right = r"(?P<right>" + ARGUMENT + r"|(?P<constant>" + CONSTANT + r"))"
    match = None
    assigned = re.search(
        r"(iVar\d+|uVar\d+|cVar\d+) = " + re.escape(read[0]) + ";", body
    )
    if assigned:
        match = re.search(
            r"return CONCAT[37]1\([^;]*?,\s*"
            + assigned[1]
            + r" (?P<operator>==|!=|<=|>=|<|>) "
            + right
            + r"\);",
            body,
        )
    else:
        match = re.search(
            r"return (?:CONCAT[37]1\([^;]*?,\s*)?"
            + re.escape(read[0])
            + r" (?P<operator>==|!=|<=|>=|<|>) "
            + right
            + r"\)?;",
            body,
        )
    if match is None:
        return None
    resolved = _context_path(metadata, read["path"], read["last"])
    if resolved is None:
        return None
    names, field_type = resolved
    argument_type = argument_field = None
    if match["argoffset"]:
        argument_type, argument_field = _argument_field(
            metadata, row, match["argoffset"]
        )
        if argument_field is None:
            return None
    return dict(
        kind="context_field",
        commandType=row["type"],
        argumentType=argument_type,
        contextType=ENEMY_CONTEXT_TYPE,
        contextField=".".join(names),
        contextFieldType=field_type,
        contextOffset=None,
        operator=match["operator"],
        argumentField=argument_field,
        constant=None if argument_field else int(match["constant"], 0),
        guard="原生工作有效，且通过命令工作类型检查",
        evidence=evidence(row),
        nativeExpression=match[0],
        semanticStatus="native_context_field_comparison_recovered",
    )


def _field_offset(metadata, owner, field):
    return int(metadata.fields(owner)[field]["offset_from_base"], 16)


def _argument_field(metadata, row, offset):
    argument_type = row["parameters"][-1]["type"] if row.get("parameters") else None
    if not argument_type:
        return None, None
    fields = [
        k
        for k, v in metadata.fields(argument_type).items()
        if k != "Null" and v.get("offset_from_base") == offset and "default" not in v
    ]
    return (argument_type, fields[0]) if len(fields) == 1 else (None, None)


def recover_unique_state_leaf(row, body, metadata, names):
    """``Extend._UniqueStateFixedID`` has a value equal to one constant.

    The Nullable<int> is read as one 8-byte value: the low byte is HasValue and
    the high dword is the UNIQUE_STATE_Fixed value.
    """
    if ">> 0x20) ==" not in body or re.search(CALL, body):
        return None
    unique = _field_offset(metadata, EXTEND_BASE_TYPE, EXTEND_UNIQUE_STATE_FIELD)
    container = metadata.fields(EXTEND_BASE_TYPE)[EXTEND_UNIQUE_STATE_FIELD]["type"]
    holder = metadata.fields(container)["_Value"]
    value = int(metadata.fields(holder["type"])["_Value"]["offset_from_base"], 16)
    if unique % 8 or re.search(CALL, body):
        return None
    match = re.search(
        r"(uVar\d+) = \*\(undefined8 \*\)\(\*\(longlong \*\)\((?:"
        + "|".join(sorted(names))
        + rf")\[{unique // 8}\] \+ {int(holder['offset_from_base'], 16):#x}\) \+ {value:#x}\); "
        + r"return CONCAT71\([^;]*?,\s*\(int\)\(\(ulonglong\)\1 >> 0x20\) == (?P<value>"
        + CONSTANT
        + r") && \(char\)\1 != '\\0'\);",
        body,
    )
    if match is None:
        return None
    return dict(
        kind="unique_state",
        commandType=row["type"],
        argumentType=None,
        contextType=EXTEND_BASE_TYPE,
        contextField=EXTEND_UNIQUE_STATE_FIELD,
        contextFieldType=container,
        contextOffset=hex(unique),
        operator="==",
        argumentField=None,
        constant=_int32(int(match["value"], 0)),
        guard="原生工作与自身 Extend 对象有效，且通过原生类型检查；HasValue 为真",
        evidence=evidence(row),
        nativeExpression=match[0],
        semanticStatus="native_unique_state_comparison_recovered",
    )


def _unique_level_getter(pe, address, metadata):
    """Category of an Extend method whose body returns getLevel(category).Value.

    Accepted only when the module comes from Extend._Accessor -> target context
    -> cEnemyContext.UniqueLeveledValue, the category is an immediate and the
    Nullable result is tested for HasValue before its value dword is used.
    """
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM, CS_OP_REG

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    chain = (
        _field_offset(metadata, EXTEND_BASE_TYPE, EXTEND_ACCESSOR_FIELD),
        ACCESSOR_TARGET_CONTEXT,
        TARGET_CONTEXT_ENEMY,
        _field_offset(metadata, ENEMY_CONTEXT_TYPE, UNIQUE_LEVELED_MODULE_FIELD),
    )
    end = pe.end(address)
    instructions = list(decoder.disasm(pe.read(address, end - address), address))
    values, category, result = {"rdx": ()}, None, None
    for number, ins in enumerate(instructions):
        op = ins.operands
        if ins.mnemonic == "call":
            if op[0].type == CS_OP_IMM and op[0].imm == FN_UNIQUE_LEVEL:
                after = instructions[number + 1 : number + 5]
                if (
                    result is not None
                    or values.get("r8") != chain
                    or category is None
                    or values.get("rcx") != ("stack",)
                    or [i.mnemonic for i in after] != ["mov", "test", "je", "shr"]
                ):
                    return None
                result = category
            for name in ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11"):
                values.pop(name, None)
            continue
        if ins.mnemonic == "mov" and len(op) == 2 and op[0].type == CS_OP_REG:
            name = ins.reg_name(op[0].reg)
            if op[1].type == CS_OP_MEM and not op[1].mem.index:
                base = values.get(ins.reg_name(op[1].mem.base))
                values[name] = (
                    base + (op[1].mem.disp,) if isinstance(base, tuple) else None
                )
            elif op[1].type == CS_OP_IMM:
                values[name] = None
                if name == "r9d":
                    category = op[1].imm & 0xFFFFFFFF
            elif op[1].type == CS_OP_REG:
                values[name] = values.get(ins.reg_name(op[1].reg))
        elif ins.mnemonic == "lea" and op[0].type == CS_OP_REG:
            values[ins.reg_name(op[0].reg)] = (
                ("stack",) if ins.reg_name(op[1].mem.base) == "rsp" else None
            )
    return result


def recover_unique_level_leaf(row, body, metadata, species, names, pe):
    """``getLevel(category).Value`` compared with a constant or argument.

    The level comes from cEnemyContext.UniqueLeveledValue directly, or from one
    Extend getter whose body is that read; a missing level throws.
    """
    level = "(?:" + "|".join(UNIQUE_LEVEL_LABELS) + ")"
    getter_call = re.search(
        r"(?P<value>iVar\d+) = (?:FUN_|func_0x0*)(?P<getter>[0-9a-f]+)\(param_1,(?:"
        + "|".join(sorted(names) or ["$^"])
        + r")\);",
        body,
    )
    if not re.search(level + r"\(", body) and (getter_call is None or pe is None):
        return None
    context = (
        r"\*\(undefined8 \*\)\(\*\(longlong \*\)\(\*\(longlong \*\)\(param_3\[5\] \+ "
        + f"{ACCESSOR_TARGET_CONTEXT:#x}"
        + r"\) \+ "
        + f"{TARGET_CONTEXT_ENEMY:#x}"
        + r"\) \+ "
        + f"{_field_offset(metadata, ENEMY_CONTEXT_TYPE, UNIQUE_LEVELED_MODULE_FIELD):#x}"
        + r"\)"
    )
    right = r"(?P<right>" + ARGUMENT + r"|(?P<constant>" + CONSTANT + r"))"
    getter = None
    match = re.search(
        level
        + r"\((?P<out>\w+),param_1,\s*"
        + context
        + r",\s*(?P<category>0x[0-9a-f]+|\d+)\);"
        + r" if \((?P=out)\[0\] == '\\0'\) \{ (?P<value>iVar\d+) = 0;[^{}]*\} "
        + r"else \{ (?P=value) = (?P=out)\._4_4_; \} \w+ = CONCAT71\([^;]*?,\s*(?P=value) == "
        + right
        + r"\);",
        body,
    )
    if match is not None:
        category = int(match["category"], 0) & 0xFFFFFFFF
        if len(re.findall(CALL, body)) != 4:
            return None
    elif pe is not None and names:
        match = re.search(
            r"(?P<value>iVar\d+) = (?:FUN_|func_0x0*)(?P<getter>[0-9a-f]+)\(param_1,(?:"
            + "|".join(sorted(names))
            + r")\); \w+ = (?P=value) == "
            + right
            + r";",
            body,
        )
        if match is None or len(re.findall(CALL, body)) != 1:
            return None
        getter = int(match["getter"], 16)
        category = _unique_level_getter(pe, getter, metadata)
        if category is None:
            return None
    else:
        return None
    argument_type = argument_field = None
    if match["argoffset"]:
        argument_type, argument_field = _argument_field(
            metadata, row, match["argoffset"]
        )
        if argument_field is None:
            return None
    _, categories = metadata.enum(
        f"app.{species.split('_')[0]}Def.UniqueLeveledValueCategory_Fixed"
    )
    return dict(
        kind="unique_leveled_value",
        commandType=row["type"],
        argumentType=argument_type,
        contextType="app.cEmModuleUniqueLeveledValue",
        contextField=f"level:{category}",
        contextFieldType="System.UInt32",
        contextOffset=None,
        category=category,
        categoryName=next((n for n, v in categories.items() if v == category), None),
        getter=hex(getter) if getter else None,
        operator="==",
        argumentField=argument_field,
        constant=None if argument_field else int(match["constant"], 0),
        guard="原生工作有效；等级值存在（无值时原生代码抛出异常）",
        evidence=evidence(row),
        nativeExpression=match[0],
        semanticStatus="native_unique_level_comparison_recovered",
    )


LEAF_OPERATORS = {"==": "eq", "!=": "ne", "<=": "le", ">=": "ge", "<": "lt", ">": "gt"}


def leaf_expression(leaf, argument=None):
    """Condition over the monster's own Extend field from a recovered leaf rule."""
    from .expressions import combined, compare, runtime
    from .values import enum_number, scalar

    key = f"extend:{leaf['contextType']}.{leaf['contextField']}"
    source = (
        f"{leaf['contextType']}.{leaf['contextField']}（{leaf['contextOffset']}）"
    )
    guard = combined(
        "all",
        runtime("enemy_command_work_valid", "命令工作存在且原生类型检查通过"),
        runtime("self_extend_valid", "自身 Extend 对象存在且原生类型检查通过"),
    )
    if leaf.get("kind") == "unique_state":
        key = "self_unique_state_fixed_id"
        source = "cEnemyExtendBase._UniqueStateFixedID 有值时的 UNIQUE_STATE_Fixed 值"
    elif leaf.get("kind") == "unique_leveled_value":
        key = f"unique_level:{leaf['category']}"
        source = f"cEmModuleUniqueLeveledValue.getLevel({leaf['categoryName'] or leaf['category']})"
        if not leaf.get("getter"):
            guard = runtime(
                "enemy_command_work_valid", "命令工作存在且原生类型检查通过"
            )
    elif leaf.get("kind") == "context_field":
        key = f"context:{leaf['contextField']}"
        source = f"cEnemyContext.{leaf['contextField']}"
        guard = runtime("enemy_command_work_valid", "命令工作存在且原生类型检查通过")
    operator = LEAF_OPERATORS[leaf["operator"]]
    if leaf["argumentField"]:
        if argument is None or leaf["argumentField"] not in argument:
            return None
        raw = scalar(argument[leaf["argumentField"]])
        value = enum_number(raw) if isinstance(raw, str) else raw
        if type(value) not in (int, float, bool):
            return None
        test = compare(key, value, operator, source=source)
    elif leaf["contextFieldType"] == "System.Boolean" and operator in ("eq", "ne"):
        test = runtime(key, source)
        if operator == "eq":
            test = dict(kind="not", item=test)
    else:
        test = compare(key, leaf["constant"], operator, source=source)
    return combined("all", guard, test)
