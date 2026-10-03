"""Validate every reviewed semantic model before updating any formal input."""

import json
from pathlib import Path

from src.processed_data.enemy_battle_logic.builder import build_chain
from src.processed_data.enemy_battle_logic.definitions import (
    read_models,
    require_model_set,
)
from src.processed_data.enemy_battle_logic.validation import validate_graph
from src.processed_data.enemy_battle_logic.audit import validate_release_graph
from src.processed_data.enemy_battle_logic.model_io import load_model, MODEL_LIMIT_BYTES
from .native import digest, verify_rows
from .evidence import semantic_evidence


def freeze_reviewed_models(source, output, exe, metadata, natives, profile):
    source, output = Path(source), Path(output)
    specs = read_models(source)
    require_model_set(specs)
    if (
        digest(exe) != profile["exeSha256"]
        or digest(metadata) != profile["metadataSha256"]
    ):
        raise ValueError("Source version changed; review recipes before freezing")
    results = []
    for spec in specs:
        model = load_model(spec.path)
        if model["profile"] != profile:
            raise ValueError("审核模型来源版本不匹配")
        graph = build_chain(natives, spec.path, rules_path=source / "rules.v1.json")
        validate_graph(graph)
        validate_release_graph(graph)
        evidence = [table["evidence"] for table in graph["tables"]]
        evidence.extend(entry["evidence"] for entry in graph["entryPoints"])
        verify_rows(exe, evidence)
        catalog, bindings = semantic_evidence(
            [table["evidence"] for table in model["tables"]]
        )
        model["evidenceCatalog"] = catalog
        for table, binding in zip(model["tables"], bindings):
            table.pop("evidence", None)
            table.update(
                nativeType=binding["type"],
                nativeMethod=binding["method"],
                evidenceRef=binding["evidenceRef"],
            )
        content = json.dumps(model, ensure_ascii=False, indent=2) + "\n"
        if len(content.encode()) > MODEL_LIMIT_BYTES:
            raise ValueError("固化模型超过体积预算，必须保留语义并去重或分片")
        results.append((spec.path.name, content))
    # No formal input changes before the full set has passed semantic gates.
    rules = (source / "rules.v1.json").read_text(encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in results + [("rules.v1.json", rules)]:
        (output / name).write_text(content, encoding="utf-8")
    print("FROZEN SEMANTIC MODELS", len(specs))
