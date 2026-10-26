"""Monster battle logic data for the website; game files and the SDK are not inputs.

One JSON per monster holds its frozen graph and the combined diagram of the
technical view; ``index.json`` lists the monsters for the overview page.
"""

import json
from pathlib import Path
import re

from src.processed_data.enemy_battle_logic.definitions import (
    EXPECTED_ENEMY_IDS,
    MODEL_DIR,
    read_models,
    require_model_set,
)
from src.processed_data.enemy_battle_logic.diagram import combined_diagram
from src.processed_data.enemy_battle_logic.model_io import load_model
from src.processed_data.enemy_battle_logic.validation import validate_graph

BUNDLE_DIR = "enemy_battle_logic"
INDEX_NAME = f"{BUNDLE_DIR}/index.json"


def page_payload(graph):
    return {
        "graph": graph,
        "diagram": combined_diagram(
            graph, compact_details=bool(graph.get("playerView"))
        ),
    }


def export_battle_data(
    output_dir, *, models_dir=MODEL_DIR, template_path=None, research_preview=False
):
    output_dir = Path(output_dir)
    preview = template_path is not None or research_preview
    specs = read_models(models_dir, template_path=template_path)
    if not preview:
        require_model_set(specs)
    records, results = [], []
    for spec in specs:
        graph = load_model(spec.path)
        if graph.get("artifactKind") != "extracted_battle_graph":
            raise ValueError(
                "网页构建只接受 SDK 离线提取的图 JSON；请先在本机执行 extract 或 freeze"
            )
        # validate_bundle checks every graph after writing.
        results.append((f"{BUNDLE_DIR}/{spec.enemy_id}.json", page_payload(graph)))
        view = graph.get("playerView") or {}
        records.append(
            dict(
                enemyId=spec.enemy_id,
                enemyName=graph.get("enemyName", spec.enemy_id),
                logicStatus=graph.get("logicStatus", "recovered_with_boundaries"),
                coverage=graph["coverage"],
                # Overview summary only; validate_bundle ignores these keys.
                behaviorTables=sum(
                    entry.get("relation") != "unknown"
                    for entry in view.get("entries", [])
                ),
                actions=len(
                    {
                        node.get("technicalName") or node["title"]
                        for node in view.get("nodes", {}).values()
                        if node["kind"] == "action"
                    }
                ),
            )
        )
    index = dict(schemaVersion=1, releaseReady=not preview, monsters=records)
    results.append((INDEX_NAME, index))
    folder = output_dir / BUNDLE_DIR
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("行动图输出目录必须为空，避免混入旧版或范围不一致的文件")
    for relative, content in results:
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(content, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    validate_bundle(output_dir, require_release=not preview)
    return [output_dir / relative for relative, _ in results]


def validate_payload(payload, document):
    if payload.get("graph") != document or payload.get("diagram") != combined_diagram(
        document, compact_details=bool(document.get("playerView"))
    ):
        raise ValueError("网页数据与行动模型的内容或连接不一致")


def validate_bundle(output_dir, *, require_release=True):
    folder = Path(output_dir) / BUNDLE_DIR
    index = json.loads((Path(output_dir) / INDEX_NAME).read_text(encoding="utf-8"))
    if index.get("schemaVersion") != 1 or not index.get("monsters"):
        raise ValueError("怪物索引无效")
    expected = {Path(INDEX_NAME).name}
    seen = set()
    for item in index["monsters"]:
        enemy_id = item["enemyId"]
        if enemy_id in seen or not re.fullmatch(r"EM\d{4}_\d{2}_\d+", enemy_id):
            raise ValueError("怪物索引标识重复或无效")
        seen.add(enemy_id)
        expected.add(f"{enemy_id}.json")
        payload = json.loads((folder / f"{enemy_id}.json").read_text(encoding="utf-8"))
        document = payload.get("graph")
        if not document or document.get("artifactKind") != "extracted_battle_graph":
            raise ValueError("网页数据未使用 SDK 离线提取的图 JSON")
        if (
            any(
                document[key] != item[key]
                for key in ("enemyId", "enemyName", "logicStatus")
            )
            or document.get("coverage") != item["coverage"]
        ):
            raise ValueError("怪物索引与怪物数据不一致")
        validate_graph(document)
        validate_payload(payload, document)
    actual = {path.name for path in folder.iterdir() if path.is_file()}
    if actual != expected:
        raise ValueError("行动图数据目录只允许索引与各怪物 JSON")
    if require_release and seen != set(EXPECTED_ENEMY_IDS):
        raise ValueError("行动图发布必须包含全部 34 个怪物")
    return index
