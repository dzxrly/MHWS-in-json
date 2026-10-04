"""Run complete offline evidence discovery; retain the semantic release boundary."""

import json
import zipfile
from pathlib import Path

from .batch import export_native_index
from .evidence import method_rows, pack_methods
from .inventory import discover_inventory
from .native import digest
from .requests import discover_requests
from .streaming import extract_cached
from .workbench import render_workbench
from .native_viewer import export_native_views
from src.processed_data.enemy_battle_logic.viewer import render_html
from src.processed_data.enemy_battle_logic.index_viewer import render_index
from src.processed_data.enemy_battle_logic.validation import validate_html
from src.processed_data.enemy_battle_logic.definitions import (
    read_models,
    EXPECTED_ENEMY_IDS,
)
from src.processed_data.enemy_battle_logic.builder import build_chain
from src.processed_data.enemy_battle_logic.validation import validate_graph
from src.processed_data.enemy_battle_logic.audit import validate_release_graph


def package_result(output):
    """Bundle review pages and compact receipts, excluding native caches."""
    output = Path(output)
    archive = output.with_suffix(".zip")
    temporary = archive.with_suffix(".zip.pending")
    roots = {"index.html", "inventory.json", "action-requests.json", "run-result.json"}
    files = sorted(
        p
        for p in output.rglob("*")
        if p.is_file()
        and (
            p.relative_to(output).as_posix() in roots
            or p.relative_to(output).parts[0] in {"native-flow", "semantic-preview"}
        )
    )
    with zipfile.ZipFile(
        temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6
    ) as bundle:
        for path in files:
            bundle.write(
                path, "enemy-battle-analysis/" + path.relative_to(output).as_posix()
            )
    with zipfile.ZipFile(temporary) as bundle:
        invalid = bundle.testzip()
        if invalid:
            raise ValueError("离线结果压缩包校验失败：" + invalid)
    temporary.replace(archive)
    receipt = dict(
        path=str(archive),
        bytes=archive.stat().st_size,
        files=len(files),
        crcVerified=True,
        nativeCachesIncluded=False,
    )
    (output.parent / "bundle-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print("REVIEW BUNDLE", json.dumps(receipt), flush=True)
    return receipt


def run_all(
    exe,
    metadata,
    natives,
    output,
    version,
    ghidra,
    project_dir,
    *,
    project_name=None,
    index_path=None,
    cache_dir=None
):
    output = Path(output).resolve()
    root = Path(__file__).resolve().parents[2]
    if not output.is_relative_to(root / ".agents"):
        raise ValueError("全量离线研究结果只允许输出到项目 .agents")
    output.mkdir(parents=True, exist_ok=True)
    if index_path is None:
        index_path = output / "native-index.json"
        index = export_native_index(exe, metadata, index_path, version)
    else:
        index = json.loads(Path(index_path).read_text(encoding="utf8"))
        if (
            index["profile"]["gameVersion"] != version
            or index["profile"]["metadataSha256"] != digest(metadata)
            or index["profile"]["exeSha256"] != digest(exe)
        ):
            raise ValueError("全量运行索引与当前 EXE、元数据或版本不匹配")
    inventory = discover_inventory(natives, Path(metadata), index["profile"])
    inventory_path = output / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, separators=(",", ":")),
        encoding="utf8",
    )
    export_types = {r["exportType"] for r in inventory["resources"]}
    rows = [
        r
        for r in method_rows(index)
        if r["type"] in export_types
        and r["method"].startswith(("table_", "updateTableInpl"))
    ]
    if (
        sum(r["method"].startswith("table_") for r in rows)
        != inventory["nativeTableMethodBindings"]
    ):
        raise ValueError("原生索引未完整覆盖实际资源的子表方法")
    manifest = pack_methods(rows, index["profile"])
    cache_dir = Path(cache_dir or output / "native")
    extraction = extract_cached(
        manifest, exe, cache_dir, project_dir, ghidra, project_name=project_name
    )
    request_path = output / "action-requests.json"
    requests = discover_requests(
        cache_dir / "index.json", inventory_path, exe, metadata, natives, request_path
    )
    request_data = json.loads(request_path.read_text(encoding="utf8"))
    native_views = export_native_views(
        cache_dir / "index.json", inventory, request_data, output / "native-flow"
    )
    model_results = []
    preview_records = []
    preview_dir = output / "semantic-preview/enemy_battle_logic"
    preview_dir.mkdir(parents=True, exist_ok=True)
    for spec in read_models():
        graph = build_chain(natives, spec.path)
        if graph["profile"] != index["profile"]:
            raise ValueError("正式语义模型来源与全量运行版本不匹配")
        graph["metadataVerification"] = "matched"
        validate_graph(graph)
        html = render_html(graph)
        validate_html(html, graph)
        (preview_dir / (spec.enemy_id + ".html")).write_text(html, encoding="utf8")
        preview_records.append(
            dict(
                enemyId=spec.enemy_id,
                enemyName=graph.get("enemyName", spec.enemy_id),
                html=spec.enemy_id + ".html",
                logicStatus="recovered_with_boundaries",
                profile=graph["profile"],
                coverage=graph["coverage"],
            )
        )
        try:
            validate_release_graph(graph)
            eligible, reason = True, ""
        except ValueError as error:
            eligible, reason = False, str(error)
        model_results.append(
            dict(
                enemyId=spec.enemy_id,
                model=spec.path.relative_to(root).as_posix(),
                coverage=graph["coverage"],
                releaseEligible=eligible,
                reason=reason,
            )
        )
    (preview_dir / "index.html").write_text(
        render_index(preview_records, release_ready=False), encoding="utf8"
    )
    available = {r["enemyId"] for r in model_results}
    result = dict(
        profile=index["profile"],
        stages=dict(
            inventory="complete",
            nativeExtraction="complete",
            actionRequestDiscovery="complete",
            nativeFlowRendering="complete",
            semanticRecovery=(
                "complete"
                if len(available) == len(EXPECTED_ENEMY_IDS)
                and all(r["releaseEligible"] for r in model_results)
                else "incomplete"
            ),
        ),
        inventory=dict(
            monsters=inventory["monsterCount"],
            uniqueBTableResources=inventory["uniqueBTableResources"],
            nativeTableMethods=inventory["nativeTableMethodBindings"],
            shellNameResources=len(inventory["shellNameCatalog"]),
            shellNameRows=sum(len(x["entries"]) for x in inventory["shellNameCatalog"]),
        ),
        nativeExtraction=extraction,
        actionRequests=requests,
        nativeFlowViews=native_views,
        semanticModels=model_results,
        missingSemanticModels=sorted(set(EXPECTED_ENEMY_IDS) - available),
        releaseReady=len(available) == len(EXPECTED_ENEMY_IDS)
        and all(r["releaseEligible"] for r in model_results),
        artifacts=dict(
            inventory=str(inventory_path),
            nativeIndex=str(cache_dir / "index.json"),
            actionRequests=str(request_path),
            nativeFlowPreview=str(output / "native-flow/index.html"),
            semanticPreview=str(preview_dir / "index.html"),
        ),
        boundary="全量证据提取与资源动作身份绑定已运行；未经语义审核的原生控制流不得转成已核实行动树，缺少的模型及入口不通过正式发布验收。",
    )
    (output / "run-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
    )
    (output / "index.html").write_text(
        render_workbench(result, inventory, request_data), encoding="utf8"
    )
    package_result(output)
    print(
        "FULL RUN",
        json.dumps(
            {
                k: result[k]
                for k in (
                    "stages",
                    "inventory",
                    "nativeExtraction",
                    "actionRequests",
                    "releaseReady",
                )
            }
        ),
        flush=True,
    )
    return result
