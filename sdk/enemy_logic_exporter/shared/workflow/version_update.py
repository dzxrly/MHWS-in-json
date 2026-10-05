"""Move the SDK to a new game build: re-resolve symbols, then migrate evidence.

Both steps only write what they can prove. A symbol or evidence row whose
relocation-insensitive digest changed is reported for manual review and is
never rewritten automatically.
"""

import json
from pathlib import Path

from ..config import EVIDENCE_DIR, PROFILE_DIR, RULES_PATH, SYMBOL_SPECS
from ..native.evidence import digest
from ..native.metadata import Il2cppMetadata
from ..native.pe import PE
from ..native.symbols import (
    evidence_rows,
    method_stem,
    native_digest,
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
        json.dumps(value, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
    )


def resolve_profile(exe, metadata_path, version, previous_path, output=None):
    """Write data/profiles/<version>.json and return the change report."""
    previous = _read(previous_path)
    output = Path(output or PROFILE_DIR / f"{version}.json")
    with PE(exe) as pe, Il2cppMetadata(metadata_path) as metadata:
        profile = dict(
            gameVersion=version,
            exeSha256=digest(exe),
            metadataSha256=metadata.sha256,
        )
        symbols, report = resolve_symbols(SYMBOL_SPECS, metadata, pe, previous, profile)
    same_build = previous["profile"] == profile
    document = dict(
        schemaVersion=1,
        profile=profile,
        symbols=symbols,
        evidenceDigests=previous.get("evidenceDigests", {}) if same_build else {},
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


def migrate_evidence(exe, metadata_path, previous_path, profile_path, *, apply=False):
    """Relocate every evidence row whose normalized code is unchanged."""
    previous = _read(previous_path)
    target = _read(profile_path)
    old_digests = previous.get("evidenceDigests", {})
    new_digests = dict(target.get("evidenceDigests", {}))
    report = dict(migrated=0, unchanged=0, review=[], files={})
    with PE(exe) as pe, Il2cppMetadata(metadata_path) as metadata:
        if metadata.sha256 != target["profile"]["metadataSha256"]:
            raise ValueError("元数据与目标 profile 不匹配")
        for path in evidence_documents():
            document = _read(path)
            pending, renames = [], {}
            for row in evidence_rows(document):
                key = row["type"] + "::" + row["method"]
                old = old_digests.get(key)
                if old is None:
                    pending.append(dict(row=key, reason="上一版本 profile 缺少该证据行的规范化摘要"))
                    continue
                length = int(row["end"], 16) - int(row["address"], 16)
                candidates = _candidates(metadata, row)
                if not candidates and old.get("pattern"):
                    # Unnamed helpers carry a relocation-masked opening pattern.
                    candidates = [(row["method"], a) for a in scan_pattern(pe, old["pattern"])]
                matches = []
                for name, address in candidates:
                    end = address + length
                    if normalized_digest(pe, address, end) == old["normalizedSha256"]:
                        matches.append((name, address, end))
                if len(matches) != 1:
                    pending.append(
                        dict(
                            row=key,
                            reason="规范化代码已变化或无法唯一对应，需要人工复核",
                            candidates=[hex(a) for _, a, _ in matches],
                        )
                    )
                    continue
                name, address, end = matches[0]
                updated = dict(
                    method=name,
                    address=hex(address),
                    end=hex(end),
                    nativeSha256=native_digest(pe, address, end),
                )
                if all(row[k] == v for k, v in updated.items()):
                    report["unchanged"] += 1
                else:
                    report["migrated"] += 1
                if row["method"] != name:
                    renames[row["method"]] = name
                new_digests[row["type"] + "::" + name] = dict(
                    old, address=hex(address), normalizedSha256=old["normalizedSha256"]
                )
                if apply:
                    row.update(updated)
            report["files"][Path(path).name] = dict(review=len(pending))
            report["review"].extend(dict(file=Path(path).name, **p) for p in pending)
            if apply and not pending:
                _rename_keys(document, renames)
                if "profile" in document:
                    document["profile"] = dict(target["profile"])
                _write(path, document)
    if apply:
        target["evidenceDigests"] = dict(sorted(new_digests.items()))
        _write(profile_path, target, indent=1)
    return report


def _rename_keys(value, renames):
    """Evidence dictionaries keyed by method name follow the renamed rows."""
    if isinstance(value, dict):
        for old, new in renames.items():
            if old in value and isinstance(value[old], dict) and value[old].get("method") == new:
                value[new] = value.pop(old)
        for item in value.values():
            _rename_keys(item, renames)
    elif isinstance(value, list):
        for item in value:
            _rename_keys(item, renames)
