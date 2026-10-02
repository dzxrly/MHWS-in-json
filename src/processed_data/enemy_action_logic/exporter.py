"""Export player-facing enemy phase flowcharts into one offline HTML."""

import argparse
import os
from pathlib import Path

from config import NATIVES_DIR, ZH_HANS_LANGUAGE_ID
from src.processed_data.enemy_action_logic.document import validate_document
from src.processed_data.enemy_action_logic.evidence import apply_evidence, load_evidence
from src.processed_data.enemy_action_logic.player_view import ACTION_NAMES, player_graph
from src.processed_data.enemy_action_logic.render import html_document
from src.processed_data.enemy_action_logic.source import (
    ResourceReader,
    discover_enemies,
    load_resources,
)
from src.shared.log import info
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextDB, TextSource

OUTPUT_NAME = "EnemyActionLogic.html"
EVIDENCE_ENV_VAR = "MHWS_ENEMY_LOGIC_EVIDENCE"


def export_enemy_action_logic(
    output: Path,
    repository: SourceRepository,
    text_db: TextDB,
    *,
    evidence_path: Path | None = None,
    enemy_ids: set[str] | None = None,
) -> Path:
    reader = ResourceReader(repository.root)
    enemies = discover_enemies(repository, text_db)
    discovered = {enemy.enemy_id for enemy in enemies}
    if enemy_ids is not None:
        unknown = enemy_ids - discovered
        if unknown:
            raise ValueError(f"Unknown/out-of-scope enemy IDs: {sorted(unknown)}")
        enemies = [enemy for enemy in enemies if enemy.enemy_id in enemy_ids]
    if not enemies:
        raise ValueError("No enemies selected")
    evidence = load_evidence(evidence_path)
    if set(evidence) - discovered:
        raise ValueError(
            f"Evidence contains unknown enemy IDs: {sorted(set(evidence) - discovered)}"
        )
    records = []
    for enemy in enemies:
        info(f"    Enemy action logic: {enemy.enemy_id} {enemy.name}")
        catalog = load_resources(reader, enemy)
        native_graphs = []
        if enemy.enemy_id in evidence:
            native_graphs, provenance = apply_evidence(
                catalog, reader, evidence[enemy.enemy_id]
            )
            graphs = [player_graph(catalog, graph) for graph in native_graphs]
        else:
            graphs = [
                player_graph(catalog, phase_id=phase["id"]) for phase in catalog.phases
            ]
            provenance = {
                "verification": "typed_resources_only",
                "inGameVerified": False,
            }
        resources = {
            "sourceFiles": catalog.sources,
            "phases": catalog.phases,
            "diagnostics": catalog.diagnostics,
        }
        records.append(
            {
                "enemyId": enemy.enemy_id,
                "name": enemy.name,
                "category": enemy.category,
                "resources": resources,
                "graphs": graphs,
                "provenance": provenance,
                "nativeEvidence": {"graphs": native_graphs} if native_graphs else None,
            }
        )
    payload = {
        "schemaVersion": 1,
        "format": "mhws_enemy_action_logic",
        "scope": "EnemyData full IDs with numeric EM base < 1000; EM0165 retained as training",
        "completeLogicRecovered": False,
        "actionNames": ACTION_NAMES,
        "enemies": records,
    }
    document = html_document(payload)
    validate_document(document)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="")
    count = sum(len(record["graphs"]) for record in records)
    info(
        f"    Saved {output.name}: {len(records)} full enemy IDs, {count} connected player-view graphs"
    )
    return output


def export_from_pipeline(
    output: Path, repository: SourceRepository, text_source: TextSource
) -> Path:
    evidence = os.environ.get(EVIDENCE_ENV_VAR)
    return export_enemy_action_logic(
        output,
        repository,
        text_source.build(ZH_HANS_LANGUAGE_ID),
        evidence_path=Path(evidence) if evidence else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export selected enemy phase flowcharts into one offline HTML"
    )
    parser.add_argument("--natives", type=Path, default=NATIVES_DIR)
    parser.add_argument("--output", type=Path, required=True, help="Output HTML path")
    parser.add_argument(
        "--enemy", action="append", help="Full enemy ID; repeat to select multiple IDs"
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        help="Native graph evidence JSON, or a previous exported HTML",
    )
    args = parser.parse_args()
    text_source = TextSource.from_natives(args.natives)
    export_enemy_action_logic(
        args.output,
        SourceRepository(args.natives),
        text_source.build(ZH_HANS_LANGUAGE_ID),
        evidence_path=args.evidence,
        enemy_ids={value.upper() for value in args.enemy} if args.enemy else None,
    )


if __name__ == "__main__":
    main()
