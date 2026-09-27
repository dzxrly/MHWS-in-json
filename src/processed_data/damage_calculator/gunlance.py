"""Gunlance source parameters, preserving level indices and projectile identity."""

import json
import math
from pathlib import Path

SOURCE = "STM/GameDesign/Player/ActionData/Wp07/GlobalParam/Wp07GlobalActionParam.user.3.json"
TABLES = ("_AttackInfoList", "_RyuugekiAttackInfoList", "_PileBlastAttackInfoList", "_PileAttackList")
RATES = ("_ChargeShot_AttackRate", "_FullBurst_AttackRate", "_FullBurst_BF_AttackRate", "_FullBurst_RBF_AttackRate")
SHELL_TYPES = {"NONE", "SHOT", "CHARGE_SHOT", "CHARGE_SHOT_CHILD", "FULL_BURST", "RYUUGEKI",
               "PILE", "PILE_CONST", "PILE_BLAST", "RBF_PILE_CONST", "RBF_PILE_BLAST", "DRILL"}
SUPPORTED_TYPES = SHELL_TYPES - {"NONE", "RYUUGEKI", "DRILL"}
SUPPORTED_REQUESTS = {0, 1, 2, 5, 6, 7, 10, 11, 12, 25, 26, 27, 28, 32, 34, 35, 36, 37}


def parameters(natives_dir: Path) -> dict:
    native = json.loads((natives_dir / SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp07ActionParam"]
    result = {"source": SOURCE, "levelIndexBase": 0, "shellTypes": {},
              "rbfPileBlastRate": native["_Pile_RBF_BlastRate"]}
    # EXE 1.42.0.2 getAttackParam / getRyuugekiAttackParam /
    # getPileBlastAttackParam / getPileAttack use array[level] directly.
    for kind in ("Normal", "Wide", "Long"):
        info = native[f"_{kind}ShellTypeInfo"]["app.Wp07Def.cShellTypeInfo"]
        attack = info["_ShotAttackInfo"]["app.Wp07Def.cShotAttackInfo"]
        result["shellTypes"][kind.lower()] = {
            "tables": {name: attack[name] for name in TABLES},
            "rates": {name: info[name] for name in RATES},
        }
    validate_parameters(result)
    return result


def validate_parameters(data: dict) -> None:
    def number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    if (data.get("source") != SOURCE or data.get("levelIndexBase") != 0
            or isinstance(data.get("levelIndexBase"), bool)
            or not number(data.get("rbfPileBlastRate"))
            or set(data.get("shellTypes", {})) != {"normal", "wide", "long"}):
        raise ValueError("Invalid gunlance parameters")
    for item in data["shellTypes"].values():
        tables, rates = item.get("tables", {}), item.get("rates", {})
        if set(tables) != set(TABLES) or set(rates) != set(RATES) or not all(map(number, rates.values())):
            raise ValueError("Invalid gunlance tables or rates")
        for name, rows in tables.items():
            if not isinstance(rows, list) or len(rows) != 7:
                raise ValueError("Invalid gunlance level table")
            for row in rows:
                if name == "_PileAttackList":
                    valid = number(row)
                else:
                    valid = isinstance(row, dict) and set(row) == {"Attack", "FireAttack"} and all(map(number, row.values()))
                if not valid:
                    raise ValueError("Invalid gunlance attack parameter")
