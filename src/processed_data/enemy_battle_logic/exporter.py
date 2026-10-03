"""Release export from frozen models and source JSON, with no native inputs."""

import json
from pathlib import Path

from .builder import build_chain
from .definitions import INDEX_NAME, read_models
from .validation import validate_catalog, validate_graph, validate_html
from .viewer import render_html
from .catalog import CATALOG_TYPE, bundle_names, enemies, resource_catalog
from .predicates import RuleRegistry
from .resources import Resources

OUTPUT_NAMES = bundle_names(model_ids=[spec.enemy_id for spec in read_models()])


def export_battle_logic(
    output_dir,
    natives,
    *,
    template_path=None,
    rules_path=None,
    metadata_path=None,
    text_db=None,
):
    output_dir = Path(output_dir)
    specs = read_models(template_path=template_path)
    specs = {spec.enemy_id: spec for spec in specs}
    resources = Resources(natives)
    registry = RuleRegistry.load(rules_path)
    results, records = [], []
    targets = enemies(natives, text_db)
    if set(specs) - {enemy["enemyId"] for enemy in targets}:
        raise ValueError("固化模型包含 EnemyData 中不存在的大型怪物标识")
    for enemy in targets:
        enemy_id = enemy["enemyId"]
        if template_path is not None and enemy_id not in specs:
            continue
        catalog = resource_catalog(enemy, resources, registry)
        validate_catalog(catalog)
        if enemy_id in specs:
            spec = specs[enemy_id]
            graph = build_chain(
                natives,
                spec.path,
                rules_path=rules_path,
                metadata_path=metadata_path,
                resources=resources,
            )
            graph.update(
                enemyName=enemy["enemyName"],
                objectKind=enemy["objectKind"],
                documentType="enemy_battle_logic",
                logicStatus="partial",
                resourceCatalog=catalog,
            )
            validate_graph(graph)
            html = render_html(graph)
            validate_html(html, graph)
            json_name, html_name = spec.output_names
            results.append((html_name, html))
        else:
            graph = dict(
                schemaVersion=1,
                documentType=CATALOG_TYPE,
                enemyId=enemy_id,
                enemyName=enemy["enemyName"],
                objectKind=enemy["objectKind"],
                logicStatus="not_recovered",
                scope="原生控制流尚未恢复，不能由此推断行动逻辑树。",
                rulesProfile=registry.data["profile"],
                resourceCatalog=catalog,
            )
            json_name, html_name = f"enemy_battle_logic/{enemy_id}.json", None
        results.append(
            (json_name, json.dumps(graph, ensure_ascii=False, indent=2) + "\n")
        )
        records.append(
            dict(
                enemyId=enemy_id,
                json=Path(json_name).name,
                html=Path(html_name).name if html_name else None,
                enemyName=enemy["enemyName"],
                objectKind=enemy["objectKind"],
                logicStatus=graph["logicStatus"],
                profile=graph.get("profile", graph.get("rulesProfile")),
                coverage=graph.get("coverage"),
                metadataVerification=graph.get("metadataVerification", "not_supplied"),
                resourceSummary={
                    key: catalog[key]
                    for key in (
                        "tableCount",
                        "argumentCount",
                        "actionBindings",
                        "verifiedPredicates",
                    )
                },
            )
        )
    index = dict(
        schemaVersion=1,
        scope="EnemyData 中基础编号小于 1000 的全部大型怪物及训练对象；明确区分局部控制流模型与尚未恢复控制流的资源清单。",
        monsters=records,
    )
    results.append((INDEX_NAME, json.dumps(index, ensure_ascii=False, indent=2) + "\n"))
    for relative, content in results:
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return [output_dir / relative for relative, _ in results]
