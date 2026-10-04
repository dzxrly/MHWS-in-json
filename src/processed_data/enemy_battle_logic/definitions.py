"""Versioned build inputs, with exactly one active model per monster."""

from dataclasses import dataclass
from pathlib import Path
import re

from .model_io import load_model

MODEL_DIR = Path(__file__).with_name("models")
DEFAULT_TEMPLATE = MODEL_DIR / "em0001_00_0.v1.json"
BUNDLE_DIR = "enemy_battle_logic"
INDEX_NAME = f"{BUNDLE_DIR}/index.html"
from .scope import EXPECTED_ENEMY_IDS, TRAINING_ENEMY_ID


@dataclass(frozen=True)
class ModelSpec:
    enemy_id: str
    path: Path

    @property
    def output_names(self):
        return (f"{BUNDLE_DIR}/{self.enemy_id}.html",)


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
        model = load_model(path)
        enemy_id = model.get("enemyId", "")
        if model.get("schemaVersion") != 1 or not re.fullmatch(
            r"EM\d{4}_\d{2}_\d+", enemy_id
        ):
            raise ValueError(f"模型标识或格式无效：{path.name}")
        if enemy_id in seen:
            raise ValueError(f"同一怪物只能有一个正式模型：{enemy_id}")
        seen.add(enemy_id)
        if enemy_id == TRAINING_ENEMY_ID:
            raise ValueError("训练靶不能进入正式怪物行动模型")
        specs.append(ModelSpec(enemy_id, path))
    return tuple(specs)


def output_names(models_dir=MODEL_DIR):
    # Do not parse every model at module import or shrink the release contract to
    # whichever files happen to exist in the working tree.
    return (
        INDEX_NAME,
        *(f"{BUNDLE_DIR}/{enemy_id}.html" for enemy_id in EXPECTED_ENEMY_IDS),
    )


def require_model_set(specs, expected=EXPECTED_ENEMY_IDS):
    actual = {spec.enemy_id for spec in specs}
    if actual != set(expected):
        raise ValueError(
            "正式发布缺少已恢复的怪物行动模型："
            f"missing={sorted(set(expected)-actual)}, extra={sorted(actual-set(expected))}"
        )
