"""Extract real semantic graphs through all independent monster modules."""

import json
import hashlib
from pathlib import Path
from ...monster import get_monster
from ..models.audit import validate_release_graph
from .extraction import extract_model
from .freeze import native_evidence
from ..models.io import encode_model
from ..models.native_recipe import NativeRecipeContext
from ..models.catalog import EXPECTED_ENEMY_IDS
from ..models.validation import validate_graph
from ..config import in_tmp
from sdk.progress import track


def extract_all_models(
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    inventory_path,
    requests_path,
    output,
    *,
    enemy_ids=EXPECTED_ENEMY_IDS,
    rules_path=None
):
    """Write a checked receipt for each graph, including honest remaining gaps."""
    output = Path(output).resolve()
    if not in_tmp(output):
        raise ValueError("批次研究导出只能保存到项目 .tmp")
    if len(set(enemy_ids)) != len(enemy_ids) or set(enemy_ids) - set(
        EXPECTED_ENEMY_IDS
    ):
        raise ValueError("批次包含重复或不支持的完整怪物身份")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with NativeRecipeContext(
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        inventory_path=inventory_path,
        requests_path=requests_path,
    ) as context:
        for enemy_id in track(enemy_ids, "提取怪物模型"):
            module = get_monster(enemy_id)
            model = module.build_model(
                exe,
                metadata,
                natives,
                native_index,
                helper_index,
                requests_path=requests_path,
                inventory_path=inventory_path,
                context=context,
            )
            graph = extract_model(
                enemy_id,
                natives,
                model=model,
                rules_path=rules_path,
                resources=context.resources,
            )
            for row in native_evidence(graph):
                context.native(row)
            graph["nativeVerification"] = "matched"
            validate_graph(graph)
            try:
                validate_release_graph(graph)
                eligible, reason = True, ""
            except ValueError as error:
                eligible, reason = False, str(error)
            content = encode_model(graph)
            path = output / (enemy_id.lower() + ".v1.json")
            temporary = path.with_suffix(".json.pending")
            temporary.write_text(content, encoding="utf8", newline="\n")
            temporary.replace(path)
            item = dict(
                enemyId=enemy_id,
                model=path.name,
                bytes=path.stat().st_size,
                graphSha256=hashlib.sha256(content.encode("utf8")).hexdigest(),
                coverage=graph["coverage"],
                requestCoverage=graph.get("requestCoverage"),
                methodCoverage=graph.get("methodCoverage"),
                releaseEligible=eligible,
                reason=reason,
            )
            results.append(item)
            print(
                "EXTRACTED",
                json.dumps(
                    {k: v for k, v in item.items() if k != "methodCoverage"},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        receipt = dict(
            semanticModels=results,
            missingSemanticModels=sorted(set(EXPECTED_ENEMY_IDS) - set(enemy_ids)),
            allModelsExported=set(enemy_ids) == set(EXPECTED_ENEMY_IDS),
            semanticReviewComplete=all(r["releaseEligible"] for r in results),
            releaseReady=set(enemy_ids) == set(EXPECTED_ENEMY_IDS)
            and all(r["releaseEligible"] for r in results),
        )
    (output / "extraction-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    return receipt
