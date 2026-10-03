"""Render semantic graphs; a preview cannot silently satisfy the release gate."""

from pathlib import Path

from .builder import build_chain
from .definitions import (
    INDEX_NAME,
    EXPECTED_ENEMY_IDS,
    read_models,
    output_names,
    require_model_set,
)
from .resources import Resources
from .validation import validate_graph, validate_html
from .audit import validate_release_graph
from .viewer import render_html
from .index_viewer import render_index
from .model_io import file_digest

OUTPUT_NAMES = output_names()


def export_battle_logic(
    output_dir,
    natives,
    *,
    template_path=None,
    rules_path=None,
    metadata_path=None,
    text_db=None
):
    output_dir = Path(output_dir)
    preview = template_path is not None
    specs = read_models(template_path=template_path)
    if not preview:
        require_model_set(specs)
        from config import SUPPORT_FILES
        from src.shared.source.user3 import load_user3_table
        from .definitions import TRAINING_ENEMY_ID
        import re

        live_ids = {
            row["enemyId"]
            for row in load_user3_table(Path(natives) / SUPPORT_FILES["enemy"])
            if re.fullmatch(r"EM\d{4}_\d{2}_\d+", row.get("enemyId", ""))
            and int(row["enemyId"][2:6]) < 1000
            and row["enemyId"] != TRAINING_ENEMY_ID
        }
        if live_ids != set(EXPECTED_ENEMY_IDS):
            raise ValueError("资源侧怪物范围与正式名单不匹配")
    resources = Resources(natives)
    records, results = [], []
    metadata_digest = file_digest(metadata_path) if metadata_path is not None else None
    names = {}
    if text_db:
        from config import SUPPORT_FILES
        from src.shared.source.user3 import load_user3_table

        names = {
            row["enemyId"]: row.get("EnemyName", "")
            for row in load_user3_table(Path(natives) / SUPPORT_FILES["enemy"])
        }
    for spec in specs:
        graph = build_chain(
            natives, spec.path, rules_path=rules_path, resources=resources
        )
        if metadata_digest is not None:
            if metadata_digest != graph["profile"]["metadataSha256"]:
                raise ValueError("当前元数据版本与固化规则不匹配")
            graph["metadataVerification"] = "matched"
        graph.update(
            documentType="enemy_battle_logic", logicStatus="recovered_with_boundaries"
        )
        graph["enemyName"] = (
            (text_db.get(names.get(spec.enemy_id, "")) if text_db else None)
            or graph.get("enemyName")
            or ("雌火龙" if spec.enemy_id == "EM0001_00_0" else spec.enemy_id)
        )
        validate_graph(graph)
        if not preview:
            validate_release_graph(graph)
        html = render_html(graph)
        validate_html(html, graph)
        name = spec.output_names[0]
        results.append((name, html))
        records.append(
            dict(
                enemyId=spec.enemy_id,
                enemyName=graph["enemyName"],
                html=Path(name).name,
                logicStatus=graph["logicStatus"],
                profile=graph["profile"],
                coverage=graph["coverage"],
            )
        )
    results.append((INDEX_NAME, render_index(records, release_ready=not preview)))
    folder = output_dir / Path(INDEX_NAME).parent
    if folder.exists() and any(
        path.name not in {Path(name).name for name, _ in results}
        for path in folder.iterdir()
        if path.is_file()
    ):
        raise ValueError("行动图输出目录存在旧版或范围不一致的文件，请使用新的预览目录")
    for relative, content in results:
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return [output_dir / relative for relative, _ in results]
