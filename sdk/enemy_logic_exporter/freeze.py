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


def freeze_current_preview(output, exe, metadata, natives, profile):
    """Revalidate the maintained reviewed preview instead of rebuilding an older recipe."""
    root = Path(__file__).resolve().parents[2]
    source = root / "src/processed_data/enemy_battle_logic/models"
    if (
        digest(exe) != profile["exeSha256"]
        or digest(metadata) != profile["metadataSha256"]
    ):
        raise ValueError("Source version changed; review recipes before freezing")
    rules_path = source / "rules.v1.json"
    rules = json.loads(rules_path.read_text(encoding="utf8"))
    rows = {}

    def collect(value):
        if isinstance(value, dict):
            if all(
                k in value for k in ("address", "end", "nativeSha256", "type", "method")
            ):
                rows[(value["type"], value["method"], value["address"])] = value
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    if rules["profile"] != profile:
        raise ValueError("当前预览规则版本不匹配")
    collect(rules)
    results = []
    for spec in read_models(source):
        model = load_model(spec.path)
        if model["profile"] != profile:
            raise ValueError("当前预览模型版本不匹配")
        graph = build_chain(natives, spec.path, rules_path=rules_path)
        validate_graph(graph)
        collect(model)
        results.append(
            (spec.path.name, json.dumps(model, ensure_ascii=False, indent=2) + "\n")
        )
    verify_rows(exe, list(rows.values()))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in results + [
        ("rules.v1.json", rules_path.read_text(encoding="utf8"))
    ]:
        (output / name).write_text(content, encoding="utf8")
    print(
        "FROZEN REVIEWED PREVIEW",
        len(results),
        "models; full release verification is separate",
    )


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
