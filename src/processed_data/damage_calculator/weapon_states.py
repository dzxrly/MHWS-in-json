"""Verified weapon pre-hit state parameters (native 1.42.0.2)."""

import json
import math
from functools import lru_cache
from pathlib import Path

BOW_SOURCE = "STM/GameDesign/Player/ActionData/Wp11/GlobalParam/Wp11GlobalActionParam.user.3.json"
LANCE_SOURCE = "STM/GameDesign/Player/ActionData/Wp06/GlobalParam/Wp06GlobalActionParam.user.3.json"
SWITCHAXE_SOURCE = "STM/GameDesign/Player/ActionData/Wp08/GlobalParam/Wp08GlobalActionParam.user.3.json"
DISTANCE_FIELDS = {"optimal": "_Critical_AttackRate", "near": "_Before_Critical_AttackRate",
                   "far": "_After_Critical_AttackRate"}
STANDARD_ARROWS = {"NORMAL", "GOSHA", "QUICK_SHOT", "SPECIAL"}


@lru_cache(maxsize=8)
def switchaxe_parameters(natives_dir: Path) -> dict:
    params = json.loads((natives_dir / SWITCHAXE_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp08ActionParam"]
    # Ordinary weapon contact only: native getOnHitAttackPowerRate 0x1487417C0
    # and getOnHitOriginalAttrAttack 0x148741978. Shell branches are separate.
    return {"source": SWITCHAXE_SOURCE, "powerAttackRate": params["_Bin_Power_AttackRate"],
            "elementSeedRate": params["_Bin_Element_ElementRate"]}


def lance_charge_parameters(natives_dir: Path, scope: str, rcol: str, request_set_id: int) -> dict | None:
    # Finish stinger collision, runtime trace 526. Handling.doOnHit_AttackPre
    # 0x147592D10 reads _FinishChargeLevelForAction and table[level - 1].
    if scope != "Wp06" or not rcol.endswith("/Wp06_Attack.rcol.38.json") or request_set_id != 28:
        return None
    params = json.loads((natives_dir / LANCE_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp06ActionParam"]
    return {"source": LANCE_SOURCE, "rates": [1, *params["_FinishStingerChargeAttackRate"]]}


def runtime_support_reasons(scope: str, rcol: str, props: dict) -> list[str]:
    """Reject source-only estimates for weapon branches with missing state.

    Capture 20260926_132827 confirms that NORMAL does not mean the RCOL values
    survive weapon preprocessing: Wp08 changes the element seed, Wp07 changes
    pile motion, and the heavy-bowgun laser changes motion and hit scaling.
    These guards describe missing inputs; they do not fit those runtime ratios
    into unconditional motion values shared by other builds.
    """
    if "WpGunEnergyLaser_MultiHitCurve" in props.get("_MultiHitRateCurve.path", ""):
        return ["能量射线的能量状态及独立多段曲线尚未完整核验"]
    if scope == "Wp07" and rcol.endswith("/Wp07_Shell.rcol.38.json"):
        return ["铳枪弹体依赖炮击类型、等级及运行时参数，尚不能仅用碰撞动作值计算"]
    if scope == "Wp08" and (props.get("_GeneralValue._GeneralValue3", 0) > 0
                            or rcol.endswith("/Wp08_Shell.rcol.38.json")):
        return ["该斩斧命中的瓶类型及瓶修正尚未接入，不能按普通武器属性计算"]
    return []


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
    phial = profile.get("switchaxe")
    if phial is not None:
        if (profile.get("scope") != "Wp08" or profile.get("specialType") != "NORMAL"
                or profile.get("rcol") != "Wp08/Collision/Collider/Wp08_Attack.rcol.38.json"
                or profile.get("actionType") != "SLASH" or profile.get("elementSource") != "weapon"
                or phial.get("source") != SWITCHAXE_SOURCE
                or any(isinstance(phial.get(k), bool) or not isinstance(phial.get(k), (float, int))
                       or not math.isfinite(phial[k]) or phial[k] <= 0
                       for k in ("powerAttackRate", "elementSeedRate"))):
            raise ValueError("Invalid switch axe phial parameters")
    charge = profile.get("lanceCharge")
    if charge is not None:
        rates = charge.get("rates", [])
        if (profile.get("scope") != "Wp06" or charge.get("source") != LANCE_SOURCE
                or len(rates) != 4 or rates[0] != 1 or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in rates)):
            raise ValueError("Invalid lance charge parameters")
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
