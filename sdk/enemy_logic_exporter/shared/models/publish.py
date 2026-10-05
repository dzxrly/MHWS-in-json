"""Write compact web models from full research models.

Research-only provenance is dropped, and every repeated JSON value is stored
once in ``sharedValues`` and referenced as ``{"$": index}``. The web loader
expands references before any validation, so the rendered graph is unchanged.
"""

import copy
import json
from pathlib import Path

from .io import expand_shared_values
from ..config import (
    PREDICATE_DUPLICATE_FIELDS,
    PUBLISHED_STORAGE_FORMAT,
    RESEARCH_ONLY_MODEL_FIELDS,
    RESEARCH_ONLY_NODE_FIELDS,
    SHARED_VALUE_MIN_BYTES,
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def strip_research_fields(model):
    result = copy.deepcopy(model)
    for key in RESEARCH_ONLY_MODEL_FIELDS:
        result.pop(key, None)
    for table in result["tables"]:
        for node in table["nodes"]:
            for key in RESEARCH_ONLY_NODE_FIELDS:
                node.pop(key, None)
            predicate = node.get("predicate")
            if isinstance(predicate, dict):
                for key in PREDICATE_DUPLICATE_FIELDS:
                    if key in predicate and predicate[key] == node.get(key):
                        del predicate[key]
    return result


def restore_predicates(model):
    """Inverse of the predicate de-duplication, used for round-trip checks."""
    for table in model["tables"]:
        for node in table["nodes"]:
            predicate = node.get("predicate")
            if isinstance(predicate, dict):
                for key in PREDICATE_DUPLICATE_FIELDS:
                    if key not in predicate and key in node:
                        predicate[key] = copy.deepcopy(node[key])
    return model


def share_values(model):
    counts = {}

    def scan(value):
        if isinstance(value, dict):
            for item in value.values():
                scan(item)
        elif isinstance(value, list):
            for item in value:
                scan(item)
        if isinstance(value, (dict, list, str)):
            key = _canonical(value)
            if len(key.encode()) >= SHARED_VALUE_MIN_BYTES:
                counts[key] = counts.get(key, 0) + 1

    scan(model)
    shared, index = [], {}

    def encode(value):
        if isinstance(value, (dict, list, str)):
            key = _canonical(value)
            if counts.get(key, 0) > 1:
                if key not in index:
                    stored = inner(value)
                    index[key] = len(shared)
                    shared.append(stored)
                return {"$": index[key]}
        return inner(value)

    def inner(value):
        if isinstance(value, dict):
            if set(value) == {"$"}:
                raise ValueError("模型值与共享引用格式冲突")
            return {k: encode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [encode(v) for v in value]
        return value

    body = {key: encode(value) for key, value in model.items()}
    body["storage"] = dict(format=PUBLISHED_STORAGE_FORMAT)
    body["sharedValues"] = shared
    return body


def publish_models(source, output):
    """Publish every extracted model in ``source`` into ``output``."""
    source, output = Path(source), Path(output)
    paths = sorted(source.glob("em*.v*.json"))
    if not paths:
        raise ValueError("没有可发布的怪物图 JSON")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for path in paths:
        model = json.loads(path.read_text(encoding="utf8"))
        if model.get("storage"):
            raise ValueError("发布步骤只接受 .agents 中的完整研究模型")
        stripped = strip_research_fields(model)
        packed = share_values(stripped)
        if expand_shared_values(packed) != stripped:
            raise ValueError("共享值编码未能还原：" + path.name)
        content = json.dumps(packed, ensure_ascii=False, separators=(",", ":")) + "\n"
        (output / path.name).write_text(content, encoding="utf8")
        results.append(
            dict(
                model=path.name,
                sourceBytes=path.stat().st_size,
                publishedBytes=len(content.encode()),
            )
        )
    return results
