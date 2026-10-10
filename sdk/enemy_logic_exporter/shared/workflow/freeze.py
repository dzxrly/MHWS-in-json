"""Extract one monster through its module and verify its native evidence."""

import json
from .extraction import extract_model
from ..native.evidence import digest
from ..native.pe import verify_rows
from ..models.io import MODEL_LIMIT_BYTES


def native_evidence(value):
    rows = {}

    def collect(item):
        if isinstance(item, dict):
            if all(key in item for key in ("address", "end", "type", "method")):
                rows[(item["type"], item["method"], item["address"])] = item
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    if not rows:
        raise ValueError("离线模型没有可核对的原生方法证据")
    return list(rows.values())


def freeze_native_model(
    enemy_id,
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    *,
    requests_path=None,
    rules_path=None,
    inventory_path=None,
):
    """Build an EM's reviewed recipe and verify every embedded native method."""
    from ...monster import get_monster

    module = get_monster(enemy_id)
    recipe = getattr(module, "build_model", None)
    if recipe is None:
        raise ValueError(f"{enemy_id} 尚无可执行的原生语义配方；不能生成占位图")
    model = recipe(
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        requests_path=requests_path,
        **({"inventory_path": inventory_path} if inventory_path is not None else {}),
    )
    graph = extract_model(
        enemy_id, natives, metadata_path=metadata, rules_path=rules_path, model=model
    )
    if digest(exe) != graph["profile"]["exeSha256"]:
        raise ValueError("原生模型与当前 EXE 版本不匹配")
    verify_rows(exe, native_evidence(graph))
    graph["nativeVerification"] = "matched"
    content = json.dumps(graph, ensure_ascii=False, indent=2) + "\n"
    if len(content.encode("utf8")) > MODEL_LIMIT_BYTES:
        raise ValueError("提取的图超过 25 MiB，需在保留语义的前提下去重或分片")
    return content
