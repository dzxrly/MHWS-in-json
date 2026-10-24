"""Move the SDK to a new game build: re-resolve symbols, then migrate evidence.

Both steps only write what they can prove. A symbol or evidence row whose
relocation-insensitive digest changed is reported for manual review and is
never rewritten automatically. Evidence digests cover the whole function at
its current boundary and name every external callee, so a retargeted call, an
appended tail or a different function length all count as changes.
"""

import json
from pathlib import Path

from ..config import ACTIVE_PROFILE_PATH, EVIDENCE_DIR, RULES_PATH, SYMBOL_SPECS
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
            result[row["type"] + "::" + row["method"]] = entry
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
    report = dict(migrated=0, unchanged=0, review=[], files={})
    with PE(exe) as pe, Il2cppMetadata(metadata_path) as metadata:
        names = CallNames(pe, metadata, address_catalog(metadata))
        for path in evidence_documents():
            document = _read(path)
            pending, renames = [], {}
            for row in evidence_rows(document):
                key = row["type"] + "::" + row["method"]
                old = old_digests.get(key)
                if old is None:
                    pending.append(
                        dict(
                            row=key, reason="上一版本 profile 缺少该证据行的规范化摘要"
                        )
                    )
                    continue
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
                if all(row[k] == v for k, v in updated.items()):
                    report["unchanged"] += 1
                else:
                    report["migrated"] += 1
                if row["method"] != name:
                    renames[row["method"]] = name
                new_digests[row["type"] + "::" + name] = dict(old, address=hex(address))
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
