"""Bounded, project-contained model reads; research indexes are not models."""

import hashlib
import json
from pathlib import Path
import warnings

MODEL_WARNING_BYTES = 10 * 1024 * 1024
MODEL_LIMIT_BYTES = 25 * 1024 * 1024


def read_json(path):
    path = Path(path)
    size = path.stat().st_size
    if size > MODEL_LIMIT_BYTES:
        raise ValueError(
            f"模型文件超过 25 MiB，请去重或按语义分片，不能截断逻辑：{path.name}"
        )
    if size > MODEL_WARNING_BYTES:
        warnings.warn(f"模型文件超过 10 MiB，检查重复证据：{path.name}", stacklevel=2)
    return json.loads(path.read_text(encoding="utf-8"))


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


SHARED_VALUES_FORMAT = "shared-values-v1"


def expand_shared_values(document):
    """Resolve {"$": index} references of a published model's sharedValues."""
    storage = document.get("storage")
    if storage is None:
        return document
    if storage.get("format") != SHARED_VALUES_FORMAT:
        raise ValueError("不支持的模型存储格式")
    shared = document.get("sharedValues")
    if not isinstance(shared, list):
        raise ValueError("共享值表缺失")

    def expand(value, depth=0):
        if depth > 64:
            raise ValueError("共享值引用层级过深")
        if isinstance(value, dict):
            if set(value) == {"$"}:
                index = value["$"]
                if type(index) is not int or not 0 <= index < len(shared):
                    raise ValueError("共享值引用无效")
                return expand(shared[index], depth + 1)
            return {k: expand(v, depth) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v, depth) for v in value]
        return value

    return {
        key: expand(value)
        for key, value in document.items()
        if key not in ("storage", "sharedValues")
    }


def load_model(path):
    """Resolve optional semantic fragments without leaving the model directory."""
    path = Path(path)
    model = expand_shared_values(read_json(path))
    if model.get("documentType") in (
        "enemy_native_model",
        "enemy_battle_resource_catalog",
    ):
        raise ValueError("原生索引和资源清单不能作为正式行动模型")
    model.setdefault("documentType", "enemy_battle_logic")
    root = path.parent.resolve()
    for reference in model.pop("fragments", []):
        relative = Path(reference["path"])
        fragment = (root / relative).resolve()
        if relative.is_absolute() or not fragment.is_relative_to(root):
            raise ValueError("模型分片不能越出模型目录")
        if file_digest(fragment) != reference["sha256"]:
            raise ValueError("模型分片摘要不匹配")
        content = expand_shared_values(read_json(fragment))
        if content.get("profile") != model.get("profile"):
            raise ValueError("模型分片来源版本不匹配")
        if content.get("enemyId", model.get("enemyId")) != model.get("enemyId"):
            raise ValueError("模型分片怪物标识不匹配")
        model.setdefault("tables", []).extend(content.get("tables", []))
        for key in ("evidenceCatalog", "resources"):
            for identity, value in content.get(key, {}).items():
                catalog = model.setdefault(key, {})
                if identity in catalog and catalog[identity] != value:
                    raise ValueError("模型分片的共享资源或证据定义冲突")
                catalog[identity] = value
    evidence = model.get("evidenceCatalog", {})
    for table in model.get("tables", []):
        if "evidenceRef" in table:
            reference = table.pop("evidenceRef")
            if reference not in evidence:
                raise ValueError("子表引用缺失的原生证据")
            table["evidence"] = dict(
                evidence[reference],
                type=table["nativeType"],
                method=table["nativeMethod"],
            )
    if not model.get("tables") or not model.get("entry"):
        raise ValueError("行动模型缺少语义控制流和入口")
    return model
