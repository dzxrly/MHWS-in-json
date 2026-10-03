"""Release export from frozen models and source JSON, with no native inputs."""

import json
from pathlib import Path

from .builder import build_chain
from .definitions import INDEX_NAME, read_models, output_names
from .validation import validate_graph, validate_html
from .viewer import render_html

OUTPUT_NAMES = output_names()


def export_battle_logic(
    output_dir, natives, *, template_path=None, rules_path=None, metadata_path=None
):
    output_dir = Path(output_dir)
    specs = read_models(template_path=template_path)
    results, records = [], []
    for spec in specs:
        graph = build_chain(
            natives, spec.path, rules_path=rules_path, metadata_path=metadata_path
        )
        validate_graph(graph)
        html = render_html(graph)
        validate_html(html, graph)
        json_name, html_name = spec.output_names
        results.append(
            (json_name, json.dumps(graph, ensure_ascii=False, indent=2) + "\n")
        )
        results.append((html_name, html))
        records.append(
            dict(
                enemyId=spec.enemy_id,
                json=Path(json_name).name,
                html=Path(html_name).name,
                profile=graph["profile"],
                coverage=graph["coverage"],
                metadataVerification=graph["metadataVerification"],
            )
        )
    index = dict(
        schemaVersion=1,
        scope="仅包含当前已固化模型；未恢复部分保留未知，不代表全部怪物的完整战斗 AI",
        monsters=records,
    )
    results.append((INDEX_NAME, json.dumps(index, ensure_ascii=False, indent=2) + "\n"))
    for relative, content in results:
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return [output_dir / relative for relative, _ in results]
