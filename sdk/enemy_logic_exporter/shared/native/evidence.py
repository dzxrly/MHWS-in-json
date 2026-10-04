"""Deduplicate byte identity, aliases and layouts without merging method contexts."""

import hashlib
import json
from pathlib import Path


def evidence_key(row):
    identity = [row["address"], row["end"], row["nativeSha256"]]
    return hashlib.sha256(
        json.dumps(identity, separators=(",", ":")).encode()
    ).hexdigest()[:24]


def pack_methods(rows, profile, **attributes):
    code, aliases, layouts, bindings = {}, {}, {}, []
    for row in rows:
        key = evidence_key(row)
        code.setdefault(key, {k: row[k] for k in ("address", "end", "nativeSha256")})
        address = row["address"]
        prior = aliases.setdefault(address, row.get("addressAliases", []))
        if prior != row.get("addressAliases", []):
            raise ValueError("同地址别名证据不一致，不能任选一个覆盖")
        layout = row.get("fields", {})
        if row["type"] in layouts and layouts[row["type"]] != layout:
            raise ValueError("同类型字段布局证据不一致")
        layouts[row["type"]] = layout
        binding = {
            k: v
            for k, v in row.items()
            if k not in {"address", "end", "nativeSha256", "addressAliases", "fields"}
        }
        binding["nativeCodeRef"] = key
        bindings.append(binding)
    return dict(
        schemaVersion=2,
        documentType="native_evidence_index",
        profile=profile,
        nativeCode=code,
        aliasesByAddress=aliases,
        fieldsByType=layouts,
        methods=bindings,
        **attributes
    )


def method_rows(document):
    if isinstance(document, list):
        return document
    if document.get("documentType") != "native_evidence_index":
        return document["methods"]
    rows = []
    for binding in document["methods"]:
        row = dict(binding)
        key = row.pop("nativeCodeRef")
        row.update(document["nativeCode"][key])
        row["addressAliases"] = document["aliasesByAddress"][row["address"]]
        row["fields"] = document["fieldsByType"][row["type"]]
        rows.append(row)
    return rows


def semantic_evidence(rows):
    """Small catalog for reviewed models; all aliases remain in research evidence."""
    catalog, bindings = {}, []
    for row in rows:
        key = evidence_key(row)
        catalog.setdefault(key, {k: row[k] for k in ("address", "end", "nativeSha256")})
        bindings.append(dict(type=row["type"], method=row["method"], evidenceRef=key))
    return catalog, bindings


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def evidence(row):
    return {
        key: row[key] for key in ("type", "method", "address", "end", "nativeSha256")
    }
