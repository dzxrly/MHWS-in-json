"""Verify offline inputs and freeze extracted graphs, never build HTML."""

import json
from pathlib import Path
from ..models.catalog import read_models, require_model_set
from .extraction import extract_model
from ..native.evidence import digest
from ..native.pe import verify_rows
from ..config import MODEL_DIR, RULES_PATH
from ..models.audit import validate_release_graph
from ..models.io import MODEL_LIMIT_BYTES


def native_evidence(value):
    rows = {}

    def collect(item):
        if isinstance(item, dict):
            if all(
                key in item
                for key in ("address", "end", "nativeSha256", "type", "method")
            ):
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


def freeze_models(
    source,
    output,
    exe,
    metadata,
    natives,
    profile,
    *,
    release=False,
    enemy_id=None,
    template_path=None,
    rules_path=None,
):
    if rules_path is None:
        rules_path = (
            RULES_PATH
            if Path(source).resolve() == MODEL_DIR.resolve()
            else Path(source) / "rules.v1.json"
        )
    specs = read_models(source, template_path=template_path)
    if enemy_id is not None:
        specs = tuple(spec for spec in specs if spec.enemy_id == enemy_id)
        if not specs:
            raise ValueError(
                f"缺少 {enemy_id} 的已维护语义模型；不能从方法清单生成占位图"
            )
    if release:
        require_model_set(specs)
    if (
        digest(exe) != profile["exeSha256"]
        or digest(metadata) != profile["metadataSha256"]
    ):
        raise ValueError("Source version changed; review recipes before freezing")
    results = []
    for spec in specs:
        graph = extract_model(
            spec.enemy_id,
            natives,
            spec.path,
            rules_path=rules_path,
            metadata_path=metadata,
        )
        if graph["profile"] != profile:
            raise ValueError("审核模型来源版本不匹配")
        if release:
            validate_release_graph(graph)
        verify_rows(exe, native_evidence(graph))
        graph["nativeVerification"] = "matched"
        content = json.dumps(graph, ensure_ascii=False, indent=2) + "\n"
        if len(content.encode("utf8")) > MODEL_LIMIT_BYTES:
            raise ValueError("提取的图超过 25 MiB，必须保留语义并去重或分片")
        results.append((spec.path.name, content))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in results:
        (output / name).write_text(content, encoding="utf8")
    return [output / name for name, _ in results]


def freeze_current_preview(output, exe, metadata, natives, profile):
    return freeze_models(MODEL_DIR, output, exe, metadata, natives, profile)


def freeze_reviewed_models(source, output, exe, metadata, natives, profile):
    return freeze_models(source, output, exe, metadata, natives, profile, release=True)
