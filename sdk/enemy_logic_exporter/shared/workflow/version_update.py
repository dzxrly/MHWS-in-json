"""Move the SDK to a new game build: re-resolve symbols, then migrate evidence.

Both steps only write what they can prove. A symbol or evidence row whose
relocation-insensitive digest changed is reported for manual review and is
never rewritten automatically. Evidence digests cover the whole function at
its current boundary and name every external callee, so a retargeted call, an
appended tail or a different function length all count as changes.
"""

import ast
from collections import Counter
import json
from pathlib import Path

from ..config import (
    ACTIVE_PROFILE_PATH,
    EVIDENCE_DIR,
    MONSTER_MODULE_DIR,
    ROOT,
    RULES_PATH,
    SYMBOL_SPECS,
)
from ..native.metadata import Il2cppMetadata
from ..native.pe import PE, address_catalog
from ..native.symbols import (
    DIGEST_SCHEME,
    PATTERN_LENGTHS,
    CallNames,
    evidence_rows,
    masked_pattern,
    method_stem,
    normalized_digest,
    resolve_symbols,
    scan_pattern,
)


def evidence_documents():
    return sorted(EVIDENCE_DIR.glob("*.json")) + [RULES_PATH]


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value, *, indent=2):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )


def _function_end(pe, address, row_length):
    """The function boundary, never shorter than the evidence row itself."""
    return max(pe.end(address), address + row_length)


def _unique_pattern(pe, address):
    for length in PATTERN_LENGTHS:
        pattern = masked_pattern(pe, address, length)
        if scan_pattern(pe, pattern) == [address]:
            return pattern
    return None


def _digest_variants(entry):
    """Legacy profiles authorize one range; newer entries may authorize several."""
    return entry.get("rowVariants", [entry])


def _merge_digest(result, key, entry):
    variants = list(_digest_variants(result[key])) if key in result else []
    for variant in _digest_variants(entry):
        if variant not in variants:
            variants.append(dict(variant))
    variants.sort(key=lambda row: (int(row["address"], 16), row["rowLength"]))
    result[key] = dict(variants[0])
    if len(variants) > 1:
        result[key]["rowVariants"] = variants


def evidence_digests(pe, metadata, names):
    """Whole-function digests of every evidence row at its current address."""
    result = {}
    for path in evidence_documents():
        for row in evidence_rows(_read(path)):
            start = int(row["address"], 16)
            row_length = int(row["end"], 16) - start
            end = _function_end(pe, start, row_length)
            entry = dict(
                address=row["address"],
                functionLength=end - start,
                rowLength=row_length,
                normalizedSha256=normalized_digest(pe, start, end, names),
            )
            if not metadata.get(row["type"]):
                # Unnamed helpers are found again by their masked opening bytes.
                entry["pattern"] = _unique_pattern(pe, start)
            _merge_digest(result, row["type"] + "::" + row["method"], entry)
    return dict(sorted(result.items()))


def resolve_profile(exe, metadata_path, previous_path, output=None):
    """Write the build's profile (data/profile.json by default); return the report.

    The build counts as unchanged when every symbol kept its address and its
    whole normalized code; only then are the evidence digests recomputed in
    place and the carried constants left without review.
    """
    previous = _read(previous_path)
    output = Path(output or ACTIVE_PROFILE_PATH)
    with PE(exe) as pe, Il2cppMetadata(metadata_path) as metadata:
        names = CallNames(pe, metadata, address_catalog(metadata))
        symbols, report = resolve_symbols(SYMBOL_SPECS, metadata, pe, previous, names)
        same_build = (
            previous.get("digestScheme") == DIGEST_SCHEME
            and not report["moved"]
            and not report["changed"]
        )
        # On a new build the rows still point at the old one until they migrate.
        digests = evidence_digests(pe, metadata, names) if same_build else {}
    report["review"] = [] if same_build else report["reviewed"]
    document = dict(
        schemaVersion=1,
        digestScheme=DIGEST_SCHEME,
        symbols=symbols,
        evidenceDigests=digests,
    )
    _write(output, document, indent=1)
    return dict(output=str(output), sameBuild=same_build, **report)


def _candidates(metadata, row):
    record = metadata.get(row["type"]) or {}
    stem = method_stem(row["method"])
    return [
        (name, int(details["function"], 16))
        for name, details in record.get("methods", {}).items()
        if method_stem(name) == stem and details.get("function")
    ]


def _same_function(pe, address, old, names):
    """The candidate keeps the old function length and whole normalized body."""
    end = _function_end(pe, address, old["rowLength"])
    return (
        end - address == old["functionLength"]
        and normalized_digest(pe, address, end, names) == old["normalizedSha256"]
    )


def _source_path(path):
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def _uncovered_json_dependencies(document, path):
    """Report address records outside the standard method-row shape."""
    result = []

    def visit(value, pointer=""):
        if isinstance(value, dict):
            kind = None
            if {"type", "method", "address", "end"} <= set(value):
                pass
            elif (
                "slot" in value
                and isinstance(value["slot"], str)
                and value["slot"].startswith("0x")
            ):
                kind = "class_symbol_slot"
            elif isinstance(value.get("address"), str) and value["address"].startswith(
                "0x"
            ):
                kind = (
                    "constant_address"
                    if "constants" in pointer.split("/")
                    else "native_fragment" if "end" in value else "address_reference"
                )
            if kind:
                result.append(
                    dict(
                        file=_source_path(path),
                        path=pointer or "/",
                        kind=kind,
                        dependency={
                            key: value[key]
                            for key in ("type", "method", "address", "end", "slot")
                            if key in value
                        },
                        reason="缺少标准方法身份或独立定位配方；本工具只报告，不自动改写",
                    )
                )
            for key, item in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                visit(item, pointer + "/" + escaped)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, pointer + "/" + str(index))

    visit(document)
    return result


def _uncovered_python_dependencies():
    """Inspect monster literals with AST only; never import those modules."""
    result = []
    missing = object()
    for path in sorted(MONSTER_MODULE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        values = {}

        def literal(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                return values.get(node.id, missing)
            return missing

        for statement in tree.body:
            if isinstance(statement, ast.Assign):
                value = literal(statement.value)
                for target in statement.targets:
                    if isinstance(target, ast.Name) and value is not missing:
                        values[target.id] = value
        for node in ast.walk(tree):
            items = []
            if isinstance(node, ast.Dict):
                items = [
                    (literal(key), literal(value))
                    for key, value in zip(node.keys, node.values)
                    if key is not None
                ]
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "dict"
            ):
                items = [
                    (keyword.arg, literal(keyword.value))
                    for keyword in node.keywords
                    if keyword.arg is not None
                ]
            row = {
                key: value
                for key, value in items
                if isinstance(key, str) and value is not missing
            }
            if isinstance(row.get("address"), str) and isinstance(row.get("end"), str):
                complete = {"type", "method", "address", "end"} <= set(row)
                result.append(
                    dict(
                        file=_source_path(path),
                        line=node.lineno,
                        kind=(
                            "python_method_range" if complete else "python_native_range"
                        ),
                        dependency={
                            key: row[key]
                            for key in ("type", "method", "address", "end")
                            if key in row
                        },
                        reason="Python 内嵌证据不会由 JSON 迁移器改写；需人工同步或迁入标准证据文档",
                    )
                )
            elif isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) == 2:
                owner, method = (literal(item) for item in node.elts)
                if (
                    isinstance(owner, str)
                    and "." in owner
                    and isinstance(method, str)
                    and method_stem(method) != method
                ):
                    result.append(
                        dict(
                            file=_source_path(path),
                            line=node.lineno,
                            kind="python_method_name",
                            dependency=dict(type=owner, method=method),
                            reason="Python 方法名白名单保留数字后缀，不随 JSON 证据迁移",
                        )
                    )
    return result


def migrate_evidence(exe, metadata_path, previous_path, profile_path, *, apply=False):
    """Relocate every evidence row whose whole function is unchanged."""
    previous = _read(previous_path)
    target = _read(profile_path)
    if previous.get("digestScheme") != DIGEST_SCHEME:
        raise ValueError(
            "上一版本 profile 的摘要方案已过期，请先用上一版本的 EXE 重新运行 resolve-symbols"
        )
    old_digests = previous.get("evidenceDigests", {})
    new_digests = dict(target.get("evidenceDigests", {}))
    report = dict(
        migrated=0,
        unchanged=0,
        nativeBytesRefreshed=0,
        bytesRefreshed=0,
        applied=apply,
        review=[],
        files={},
        unsupportedDependencies=[],
    )
    method_rows = 0
    with PE(exe) as pe, Il2cppMetadata(metadata_path) as metadata:
        names = CallNames(pe, metadata, address_catalog(metadata))
        for path in evidence_documents():
            document = _read(path)
            report["unsupportedDependencies"].extend(
                _uncovered_json_dependencies(document, path)
            )
            pending, renames = [], {}
            for row in evidence_rows(document):
                method_rows += 1
                key = row["type"] + "::" + row["method"]
                registered = old_digests.get(key)
                if registered is None:
                    pending.append(
                        dict(
                            row=key, reason="上一版本 profile 缺少该证据行的规范化摘要"
                        )
                    )
                    continue
                old_start = int(row["address"], 16)
                row_length = int(row["end"], 16) - old_start
                variants = _digest_variants(registered)
                matching_ranges = [
                    variant
                    for variant in variants
                    if int(variant["address"], 16) == old_start
                    and variant["rowLength"] == row_length
                ]
                if len(matching_ranges) != 1:
                    pending.append(
                        dict(
                            row=key,
                            reason=(
                                "上一版本 profile 未登记该证据行范围，需用旧 EXE 核对并刷新摘要"
                                if not matching_ranges
                                else "上一版本 profile 对该证据行范围有多份不同证明，需要人工复核"
                            ),
                            address=row["address"],
                            end=row["end"],
                            rowLength=row_length,
                            availableRanges=[
                                dict(
                                    address=variant["address"],
                                    end=hex(
                                        int(variant["address"], 16)
                                        + variant["rowLength"]
                                    ),
                                    rowLength=variant["rowLength"],
                                )
                                for variant in variants
                            ],
                        )
                    )
                    continue
                old = matching_ranges[0]
                candidates = _candidates(metadata, row)
                if not candidates and old.get("pattern"):
                    # Unnamed helpers carry a relocation-masked opening pattern.
                    candidates = [
                        (row["method"], a) for a in scan_pattern(pe, old["pattern"])
                    ]
                matches = [
                    (name, address)
                    for name, address in candidates
                    if _same_function(pe, address, old, names)
                ]
                if len(matches) != 1:
                    pending.append(
                        dict(
                            row=key,
                            reason="函数长度、规范化代码或被调方已变化，或无法唯一对应，需要人工复核",
                            candidates=[hex(a) for _, a in matches],
                        )
                    )
                    continue
                name, address = matches[0]
                end = address + old["rowLength"]
                updated = dict(
                    method=name,
                    address=hex(address),
                    end=hex(end),
                )
                byte_fields = [
                    field for field in ("nativeBytes", "bytes") if field in row
                ]
                if byte_fields:
                    data = pe.read(address, old["rowLength"])
                    invalid_fields = []
                    for field in byte_fields:
                        try:
                            original = bytes.fromhex(row[field])
                        except (TypeError, ValueError):
                            original = b""
                        if len(original) != old["rowLength"]:
                            invalid_fields.append(field)
                    if invalid_fields or len(data) != old["rowLength"]:
                        pending.append(
                            dict(
                                row=key,
                                reason="原生字节证据长度与行范围不一致，不能自动刷新",
                                fields=invalid_fields or byte_fields,
                            )
                        )
                        continue
                    # Count existing fields separately, including in preview;
                    # neither spelling grants a new row range or proof.
                    for field in byte_fields:
                        updated[field] = data.hex()
                        report[field + "Refreshed"] += row[field] != updated[field]
                if all(row[k] == v for k, v in updated.items()):
                    report["unchanged"] += 1
                else:
                    report["migrated"] += 1
                if row["method"] != name:
                    renames[row["method"]] = name
                _merge_digest(
                    new_digests,
                    row["type"] + "::" + name,
                    dict(old, address=hex(address)),
                )
                if apply:
                    row.update(updated)
            report["files"][Path(path).name] = dict(review=len(pending))
            report["review"].extend(dict(file=Path(path).name, **p) for p in pending)
            if apply and not pending:
                _rename_keys(document, renames)
                _write(path, document)
    if apply:
        target["evidenceDigests"] = dict(sorted(new_digests.items()))
        target["digestScheme"] = DIGEST_SCHEME
        _write(profile_path, target, indent=1)
    report["unsupportedDependencies"].extend(_uncovered_python_dependencies())
    kinds = Counter(row["kind"] for row in report["unsupportedDependencies"])
    report["coverage"] = dict(
        status="partial" if kinds else "standard_method_rows_only",
        standardMethodRows=method_rows,
        unsupportedDependencyCount=sum(kinds.values()),
        unsupportedByKind=dict(sorted(kinds.items())),
        scope="自动迁移仅覆盖标准 JSON 方法行；其余 JSON 地址记录、怪物 Python 字面方法范围与方法名对只报告。动态 Python 值和未登记引用不在此静态清单内。",
    )
    return report


def _rename_keys(value, renames):
    """Evidence dictionaries keyed by method name follow the renamed rows."""
    if isinstance(value, dict):
        for old, new in renames.items():
            if (
                old in value
                and isinstance(value[old], dict)
                and value[old].get("method") == new
            ):
                value[new] = value.pop(old)
        for item in value.values():
            _rename_keys(item, renames)
    elif isinstance(value, list):
        for item in value:
            _rename_keys(item, renames)
