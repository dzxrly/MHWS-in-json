"""Monster battle logic data for the website; game files and the SDK are not inputs.

Only what the pages read, split per monster so no file comes near GitHub's
file size limits:

  enemy_battle_logic/index.json             monster list of the overview page
  enemy_battle_logic/<enemyId>/tree.json    decision tree (player view) and names
  enemy_battle_logic/<enemyId>/tables.json  behaviour table nodes shown as raw data
  enemy_battle_logic/<enemyId>/flow.json    technical flow chart (loaded on demand)

The release download is one file with every monster's full graph instead
(export_battle_release).
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
PAGE_FILES = ("tree.json", "tables.json", "flow.json")
TREE_FIELDS = (
    "enemyId",
    "enemyName",
    "coverage",
    "entry",
    "playerView",
    "actionNameCatalog",
)
TABLE_FIELDS = ("tableGuid", "evidence", "nodes")


def page_files(graph):
    """The three files of one monster page, keyed by file name."""
    return {
        "tree.json": {key: graph[key] for key in TREE_FIELDS if key in graph},
        "tables.json": [
            {key: table[key] for key in TABLE_FIELDS if key in table}
            for table in graph["tables"]
        ],
        "flow.json": combined_diagram(
            graph, compact_details=bool(graph.get("playerView"))
        ),
    }


def page_names(enemy_id):
    return tuple(f"{BUNDLE_DIR}/{enemy_id}/{name}" for name in PAGE_FILES)


def monsters(models_dir=MODEL_DIR, *, template_path=None, preview=False):
    """Each validated model with its overview record, in model order."""
    specs = read_models(models_dir, template_path=template_path)
    if not preview:
        require_model_set(specs)
    for spec in specs:
        graph = load_model(spec.path)
        if graph.get("artifactKind") != "extracted_battle_graph":
            raise ValueError(
                "网页构建只接受 SDK 离线提取的图 JSON；请先在本机执行 extract 或 freeze"
            )
        # The pages drop most fields, so the full graph is checked here.
        validate_graph(graph)
        view = graph.get("playerView") or {}
        record = dict(
            enemyId=spec.enemy_id,
            enemyName=graph.get("enemyName", spec.enemy_id),
            logicStatus=graph.get("logicStatus", "recovered_with_boundaries"),
            coverage=graph["coverage"],
            behaviorTables=sum(
                entry.get("relation") != "unknown" for entry in view.get("entries", [])
            ),
            actions=len(
                {
                    node.get("technicalName") or node["title"]
                    for node in view.get("nodes", {}).values()
                    if node["kind"] == "action"
                }
            ),
        )
        yield spec.enemy_id, graph, record


def export_battle_data(
    output_dir, *, models_dir=MODEL_DIR, template_path=None, research_preview=False
):
    output_dir = Path(output_dir)
    preview = template_path is not None or research_preview
    records, results = [], []
    for enemy_id, graph, record in monsters(
        models_dir, template_path=template_path, preview=preview
    ):
        for name, content in page_files(graph).items():
            results.append((f"{BUNDLE_DIR}/{enemy_id}/{name}", content))
        records.append(record)
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


def export_battle_release(path, models_dir=MODEL_DIR):
    """One file for the release download: every monster's full graph."""
    data = dict(
        schemaVersion=1,
        monsters=[
            dict(record, graph=graph) for _, graph, record in monsters(models_dir)
        ],
    )
    path = Path(path)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return path


def validate_bundle(output_dir, *, require_release=True):
    """File set and index agree; contents are checked against the models by
    regenerating them (tests/site_data)."""
    output_dir = Path(output_dir)
    index = json.loads((output_dir / INDEX_NAME).read_text(encoding="utf-8"))
    if index.get("schemaVersion") != 1 or not index.get("monsters"):
        raise ValueError("怪物索引无效")
    expected = {INDEX_NAME}
    seen = set()
    for item in index["monsters"]:
        enemy_id = item["enemyId"]
        if enemy_id in seen or not re.fullmatch(r"EM\d{4}_\d{2}_\d+", enemy_id):
            raise ValueError("怪物索引标识重复或无效")
        seen.add(enemy_id)
        expected.update(page_names(enemy_id))
        tree = json.loads(
            (output_dir / BUNDLE_DIR / enemy_id / "tree.json").read_text(
                encoding="utf-8"
            )
        )
        if (
            tree.get("enemyId") != enemy_id
            or tree.get("enemyName") != item["enemyName"]
            or tree.get("coverage") != item["coverage"]
        ):
            raise ValueError("怪物索引与怪物数据不一致")
    folder = output_dir / BUNDLE_DIR
    actual = {
        path.relative_to(output_dir).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise ValueError("行动图数据目录只允许索引与各怪物的三个 JSON")
    if require_release and seen != set(EXPECTED_ENEMY_IDS):
        raise ValueError("行动图发布必须包含全部 34 个怪物")
    return index
