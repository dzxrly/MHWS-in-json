"""Versioned build inputs, with exactly one active model per monster."""

from dataclasses import dataclass
import json
from pathlib import Path
import re

MODEL_DIR = Path(__file__).with_name("models")
DEFAULT_TEMPLATE = MODEL_DIR / "em0001.upstream.v1.json"
RULES_PATH = MODEL_DIR / "rules.v1.json"
BUNDLE_DIR = "enemy_battle_logic"
INDEX_NAME = f"{BUNDLE_DIR}/index.json"


@dataclass(frozen=True)
class ModelSpec:
    enemy_id: str
    path: Path

    @property
    def output_names(self):
        return tuple(
            f"{BUNDLE_DIR}/{self.enemy_id}.{extension}"
            for extension in ("json", "html")
        )


def read_models(models_dir=MODEL_DIR, *, template_path=None):
    paths = (
        [Path(template_path)]
        if template_path is not None
        else sorted(Path(models_dir).glob("em*.v*.json"))
    )
    if not paths:
        raise ValueError("没有已固化的怪物行动模型")
    specs, seen = [], set()
    for path in paths:
        model = json.loads(path.read_text(encoding="utf-8"))
        enemy_id = model.get("enemyId", "")
        if model.get("schemaVersion") != 1 or not re.fullmatch(
            r"EM\d{4}_\d{2}_\d+", enemy_id
        ):
            raise ValueError(f"模型标识或格式无效：{path.name}")
        if enemy_id in seen:
            raise ValueError(f"同一怪物只能有一个正式模型：{enemy_id}")
        seen.add(enemy_id)
        specs.append(ModelSpec(enemy_id, path))
    return tuple(specs)


def output_names(models_dir=MODEL_DIR):
    return (
        INDEX_NAME,
        *(name for spec in read_models(models_dir) for name in spec.output_names),
    )
