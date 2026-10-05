"""Large-monster publication scope; variants retain separate identities.

The roster is published by the SDK next to the models (models/roster.json), so
a game update that adds a monster changes data, not this module.
"""

import json
from pathlib import Path

ROSTER_PATH = Path(__file__).with_name("models") / "roster.json"
_ROSTER = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
if _ROSTER.get("schemaVersion") != 1:
    raise ValueError("不支持的怪物名单格式")
EXPECTED_ENEMY_IDS = tuple(_ROSTER["enemyIds"])
EXCLUDED_ENEMY_IDS = tuple(_ROSTER["excludedEnemyIds"])
TRAINING_ENEMY_ID = "EM0165_00_0"
if TRAINING_ENEMY_ID not in EXCLUDED_ENEMY_IDS:
    raise ValueError("训练靶必须保留在排除名单中")
