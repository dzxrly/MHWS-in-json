"""Verified weapon pre-hit state parameters (native 1.42.0.2)."""

import json
import math
from functools import lru_cache
from pathlib import Path

BOW_SOURCE = "STM/GameDesign/Player/ActionData/Wp11/GlobalParam/Wp11GlobalActionParam.user.3.json"
DISTANCE_FIELDS = {"optimal": "_Critical_AttackRate", "near": "_Before_Critical_AttackRate",
                   "far": "_After_Critical_AttackRate"}
STANDARD_ARROWS = {"NORMAL", "GOSHA", "QUICK_SHOT"}


@lru_cache(maxsize=8)
def bow_global(natives_dir: Path) -> dict:
    return json.loads((natives_dir / BOW_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp11ActionParam"]


def bow_parameters(natives_dir: Path, source: str, arrow: dict) -> dict | None:
    kind = arrow["_ArrowType"].split("] ", 1)[-1]
    # Homing/LV_MAX uses a separate native distance table. Do not substitute the
    # ordinary projectile table for special arrows.
    level = int(arrow["_ArrowLv"].split("]", 1)[0].lstrip("["))
    if kind not in STANDARD_ARROWS or level not in {1, 2, 3, 4}:
        return None
    params = bow_global(natives_dir)
    effectiveness = params["_QuickShotBottleEffectiveRate"] if kind == "QUICK_SHOT" else 1
    # mcShellPlWp11Arrow.getAttackRate552266: distance * (1 + (bottle - 1) * effectiveness).
    return {"sources": [source, BOW_SOURCE],
            "distanceRates": {key: arrow[field] for key, field in DISTANCE_FIELDS.items()},
            "coatingRates": {"none": 1, "close": 1 + (params["_CloseBottleAttackUpRate"] - 1) * effectiveness,
                             "power": 1 + (params["_StrongBottleAttackUpRate"] - 1) * effectiveness}}


def shared_bow_parameters(candidates: list[dict]) -> dict | None:
    """An action alias can share rates only when every resource agrees."""
    if not candidates or any(value is None for value in candidates):
        return None
    first = candidates[0]
    if any(value["distanceRates"] != first["distanceRates"] or
           value["coatingRates"] != first["coatingRates"] for value in candidates):
        return None
    return {**first, "sources": sorted({source for value in candidates for source in value["sources"]})}


def validate_weapon_states(profile: dict) -> None:
    value = profile.get("renkiAttack")
    if value is not None and (profile.get("scope") != "Wp03" or isinstance(value, bool)
                              or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0):
        raise ValueError("Invalid consumed spirit motion")


def validate_bow(action: dict) -> None:
    bow = action.get("bow")
    if bow is None:
        return
    if action.get("weapons") != ["bow"] or not bow.get("sources"):
        raise ValueError("Invalid bow source")
    for field, keys in (("distanceRates", {"optimal", "near", "far"}),
                        ("coatingRates", {"none", "close", "power"})):
        rates = bow.get(field, {})
        if set(rates) != keys or any(isinstance(value, bool) or not isinstance(value, (float, int))
                                    or not math.isfinite(value) or value < 0 for value in rates.values()):
            raise ValueError(f"Invalid bow {field}")
