"""Versioned build inputs, with exactly one active model per monster."""

from dataclasses import dataclass
from pathlib import Path
import re
from .io import load_model
from ..config import MODEL_DIR, RULES_PATH

TRAINING_ENEMY_ID = "EM0165_00_0"
# EnemyData snapshot. Keep variants separate and verify it against live resources.
EXPECTED_ENEMY_IDS = (
    "EM0001_00_0",
    "EM0002_00_0",
    "EM0002_50_0",
    "EM0005_00_0",
    "EM0008_00_0",
    "EM0009_00_0",
    "EM0021_00_0",
    "EM0022_00_0",
    "EM0046_00_0",
    "EM0070_00_0",
    "EM0071_00_0",
    "EM0077_00_0",
    "EM0078_00_0",
    "EM0082_00_0",
    "EM0100_51_0",
    "EM0113_51_0",
    "EM0150_00_0",
    "EM0150_50_0",
    "EM0151_00_0",
    "EM0152_00_0",
    "EM0153_00_0",
    "EM0154_00_0",
    "EM0155_00_0",
    "EM0156_00_0",
    "EM0157_00_0",
    "EM0158_00_0",
    "EM0159_00_0",
    "EM0160_00_0",
    "EM0160_50_0",
    "EM0161_00_0",
    "EM0162_00_0",
    "EM0163_00_0",
    "EM0164_50_0",
    "EM0166_00_0",
)


DEFAULT_TEMPLATE = MODEL_DIR / "em0001.upstream.v1.json"


@dataclass(frozen=True)
class ModelSpec:
    enemy_id: str
    path: Path


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


def require_model_set(specs, expected=EXPECTED_ENEMY_IDS):
    actual = {spec.enemy_id for spec in specs}
    if actual != set(expected):
        raise ValueError(
            "正式发布缺少已恢复的怪物行动模型："
            f"missing={sorted(set(expected)-actual)}, extra={sorted(actual-set(expected))}"
        )
