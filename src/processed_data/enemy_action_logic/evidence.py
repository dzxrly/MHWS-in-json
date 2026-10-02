"""Accept explicit native-derived graphs only against matching source hashes."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from src.processed_data.enemy_action_logic.document import validate_document
from src.processed_data.enemy_action_logic.graph import validate_graph
from src.processed_data.enemy_action_logic.layout import compact_layout
from src.processed_data.enemy_action_logic.source import (
    ENEMY_ID,
    ResourceCatalog,
    ResourceReader,
)


def load_evidence(path: Path | None) -> dict:
    if path is None:
        return {}
    if Path(path).suffix.lower() == ".html":
        payload = validate_document(Path(path))
        if any(
            "nativeSnapshot" in enemy.get("provenance", {})
            and not enemy.get("nativeEvidence")
            and any(
                graph.get("basis") == "native_candidates" for graph in enemy["graphs"]
            )
            for enemy in payload["enemies"]
        ):
            raise ValueError(
                "Previous HTML has only merged candidates; use the original native evidence JSON"
            )
        return {
            enemy["enemyId"]: {
                "sourceFiles": enemy["resources"]["sourceFiles"],
                "nativeSnapshot": enemy["provenance"]["nativeSnapshot"],
                "graphs": (enemy.get("nativeEvidence") or {}).get("graphs")
                or enemy["graphs"],
            }
            for enemy in payload["enemies"]
            if "nativeSnapshot" in enemy.get("provenance", {})
        }
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if payload.get("schemaVersion") != 1 or not isinstance(
        payload.get("enemies"), dict
    ):
        raise ValueError("Native evidence requires schemaVersion=1 and enemies")
    for enemy_id in payload["enemies"]:
        if not ENEMY_ID.fullmatch(enemy_id) or not enemy_id.startswith("EM"):
            raise ValueError(f"Invalid evidence enemy ID: {enemy_id}")
    return payload["enemies"]


def apply_evidence(
    catalog: ResourceCatalog, reader: ResourceReader, evidence: dict
) -> tuple[list[dict], dict]:
    source_files = evidence.get("sourceFiles", {})
    if not source_files:
        raise ValueError(f"Evidence for {catalog.enemy.enemy_id} has no source hashes")
    # Cover every source consumed by the graph's catalogue, rather than accepting
    # a hash of one unrelated file as a version check.
    missing = set(catalog.sources) - set(source_files)
    if missing:
        raise ValueError(f"Evidence lacks source coverage: {sorted(missing)[:3]}")
    for relative, digest in source_files.items():
        path = reader.resolve(relative)
        if (
            path is None
            or not re.fullmatch(r"[0-9a-f]{64}", str(digest))
            or reader.read(path)[1] != digest
        ):
            raise ValueError(f"Evidence source hash mismatch: {relative}")
    snapshot = evidence.get("nativeSnapshot", {})
    if not re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get("exeSha256", ""))):
        raise ValueError("Native evidence requires an executable SHA256")
    graphs = deepcopy(evidence.get("graphs", []))
    if not graphs or len({graph["id"] for graph in graphs}) != len(graphs):
        raise ValueError("Native evidence has no graphs or duplicate phases")
    configured = {phase["id"] for phase in catalog.phases}
    if configured != {"unresolved"} and configured != {graph["id"] for graph in graphs}:
        raise ValueError("Native evidence does not match the configured combat phases")
    for graph in graphs:
        validate_graph(graph)
        if not any(node["evidence"] == "native" for node in graph["nodes"]):
            raise ValueError("A native graph must contain native-derived nodes")
        graph["mode"] = "imported_native"
        for key in ("layout", "playerLayout"):
            if key in graph:
                compact_layout(graph[key])
        graph["coverage"] = {
            "nativeNodes": sum(node["evidence"] == "native" for node in graph["nodes"]),
            "resourceNodes": sum(
                node["evidence"] == "resource" for node in graph["nodes"]
            ),
            "unresolvedEdges": sum(
                edge["evidence"] == "unresolved" for edge in graph["edges"]
            ),
            "complete": False,
        }
        limitation = "原生图来自外部证据文件；本次只校验源 JSON 哈希与图结构，未重新反汇编 EXE，也未进行游戏内验证。"
        if limitation not in graph.setdefault("limitations", []):
            graph["limitations"].append(limitation)
    return graphs, {
        "nativeSnapshot": snapshot,
        "evidenceSha256": hashlib.sha256(
            json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "verification": "source_hashes_and_graph_structure",
        "inGameVerified": False,
    }
