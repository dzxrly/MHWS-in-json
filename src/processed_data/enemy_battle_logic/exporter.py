"""Render frozen offline graph JSON; game files and the SDK are not build inputs."""

from pathlib import Path

from .definitions import (
    INDEX_NAME,
    MODEL_DIR,
    read_models,
    output_names,
    require_model_set,
)
from .validation import validate_graph, validate_html
from .viewer import render_html
from .index_viewer import render_index
from .model_io import load_model

OUTPUT_NAMES = output_names()


def export_battle_logic(
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
        validate_graph(graph)
        html = render_html(graph)
        validate_html(html, graph)
        name = spec.output_names[0]
        results.append((name, html))
        records.append(
            dict(
                enemyId=spec.enemy_id,
                enemyName=graph.get("enemyName", spec.enemy_id),
                html=Path(name).name,
                logicStatus=graph.get("logicStatus", "recovered_with_boundaries"),
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
        path.write_text(content, encoding="utf8")
    return [output_dir / relative for relative, _ in results]
