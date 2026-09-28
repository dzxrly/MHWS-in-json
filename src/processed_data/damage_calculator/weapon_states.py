"""Verified weapon pre-hit state parameters (native 1.42.0.2)."""

import json
import math
from functools import lru_cache
from pathlib import Path

BOW_SOURCE = "STM/GameDesign/Player/ActionData/Wp11/GlobalParam/Wp11GlobalActionParam.user.3.json"
LANCE_SOURCE = "STM/GameDesign/Player/ActionData/Wp06/GlobalParam/Wp06GlobalActionParam.user.3.json"
SWITCHAXE_SOURCE = "STM/GameDesign/Player/ActionData/Wp08/GlobalParam/Wp08GlobalActionParam.user.3.json"
DUALBLADES_SOURCE = "STM/GameDesign/Player/ActionData/Wp02/GlobalParam/Wp02GlobalActionParam.user.3.json"
LONGSWORD_SOURCE = "STM/GameDesign/Player/ActionData/Wp03/GlobalParam/Wp03GlobalActionParam.user.3.json"
INSECTGLAIVE_SOURCE = "STM/GameDesign/Player/ActionData/Wp10/GlobalParam/Wp10GlobalActionParam.user.3.json"
MUSIC_SOURCE = "STM/GameDesign/Player/ActionData/Common/GlobalParam/Part/PlayerMusicSkillParam.user.3.json"
CHARGEBLADE_SOURCE = "STM/GameDesign/Player/ActionData/Wp09/GlobalParam/Wp09GlobalActionParam.user.3.json"
DISTANCE_FIELDS = {"optimal": "_Critical_AttackRate", "near": "_Before_Critical_AttackRate",
                   "far": "_After_Critical_AttackRate"}
STANDARD_ARROWS = {"NORMAL", "GOSHA", "QUICK_SHOT", "SPECIAL"}
CHARGEBLADE_SHELL = "Wp09/Collision/Collider/Wp09_Shell.rcol.38.json"


def chargeblade_phial_kind(scope: str, rcol: str, request_id: int, props: dict) -> str | None:
    """Classify exact active collisions, not the originating action name.

    mcShellPlWp09.setInfo 0x145077670 selects the normal/overcharged/combo
    collision IDs from cShellminiParamPlWp09; callers must select that hit.
    """
    if (scope != "Wp09" or rcol != CHARGEBLADE_SHELL
            or not props.get("_IsNoCritical") or not props.get("_IsNoUseKireaji")
            or not str(props.get("_SpecialType._Value", "")).endswith("NORMAL")
            or not str(props.get("_ActionTypeFixed._Value", "")).endswith("NONE")):
        return None
    if (request_id in range(11) and props.get("_UseStatusAttackPower") is True
            and props.get("_UseStatusAttrPower") is False and props.get("_AttrValue") == 0):
        return "impact"
    if (request_id in range(50, 61) and props.get("_UseStatusAttackPower") is False
            and props.get("_UseStatusAttrPower") is True and props.get("_Attack") == 0):
        return "element"
    return None


@lru_cache(maxsize=16)
def chargeblade_phial_parameters(natives_dir: Path, kind: str) -> dict:
    params = json.loads((natives_dir / CHARGEBLADE_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp09ActionParam"]
    # Shield timer > 0: impact _Attack *= 0x2B0, element _StatusAttrRate *= 0x2BC.
    # 0x148D47C68 additionally sets ArtilleryType=WP09 only for shell + GRENADE.
    return {"source": CHARGEBLADE_SOURCE, "kind": kind,
            "shieldMotionRate": params["_ShieldEnhance_GrenadeAttackRate"] if kind == "impact" else 1,
            "shieldElementRate": params["_ShieldEnhance_ElementBinRate"] if kind == "element" else 1}


@lru_cache(maxsize=8)
def chargeblade_parameters(natives_dir: Path) -> dict:
    params = json.loads((natives_dir / CHARGEBLADE_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp09ActionParam"]
    # doOnHit_AttackPre 0x148D47AB3 checks _ShieldEnhancedTimer > 0;
    # non-shell + MODE.AXE (1) multiplies _Attack at 0x148D47B3E.
    # Shells take separate impact/element phial branches and are not covered here.
    return {"source": CHARGEBLADE_SOURCE, "shieldAxeMotionRate": params["_ShieldEnhance_AxeAttackRate"]}


@lru_cache(maxsize=8)
def huntinghorn_parameters(natives_dir: Path) -> dict:
    params = json.loads((natives_dir / MUSIC_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.PlayerMusicSkillParam"]
    table = next(iter(params["_MusicSkillData"].values()))["_ParamList"]
    self_buff = next(row["app.user_data.PlayerMusicSkillParam.cMusicSkillBasicData"] for row in table
                     if row["app.user_data.PlayerMusicSkillParam.cMusicSkillBasicData"]["EnumValue"] == "[1323759744] SELF_BUFF")
    # Handling.getAttackPowerRate 0x14601E910 checks _SkillOverlap[SELF_BUFF=1]
    # then reads SELF_BUFF._WValueDatas[0]. _ValueDatas[0] is movement, not attack.
    return {"source": MUSIC_SOURCE, "selfEncoreAttackRate":
            self_buff["_WValueDatas"][0]["app.user_data.PlayerMusicSkillParam.cMusicSkillValueData"]}


@lru_cache(maxsize=8)
def insectglaive_parameters(natives_dir: Path) -> dict:
    params = json.loads((natives_dir / INSECTGLAIVE_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp10ActionParam"]
    # getAttackPowerRate 0x1493F7C70 requires positive RED and WHITE timers;
    # ORANGE selects 0x3B0 (_TrippleAtkRate), otherwise 0x398 (_RedWhiteAtkRate).
    return {"source": INSECTGLAIVE_SOURCE, "extractRates": {
        "none": 1, "redWhite": params["_RedWhiteAtkRate"], "triple": params["_TrippleAtkRate"]}}


@lru_cache(maxsize=8)
def dualblades_parameters(natives_dir: Path) -> dict:
    params = json.loads((natives_dir / DUALBLADES_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp02ActionParam"]
    # Native 1.42.0.2 getAttackPowerRate 0x143AF3660 reads 0x1FC.
    # doOnHit_AttackPre 0x143AF2CFB multiplies _StatusAttrRate by 0x200;
    # it does not multiply the element seed or its skill/cap stage.
    return {"source": DUALBLADES_SOURCE, "attackRate": params["_JustSuccessAttackRate"],
            "elementMotionRate": params["_JustSuccessStatusRate"]}


@lru_cache(maxsize=8)
def longsword_parameters(natives_dir: Path) -> dict:
    params = json.loads((natives_dir / LONGSWORD_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.Wp03ActionParam"]
    # Handling.getAttackPowerRate 0x1440F2AA0 calls getAuraAtkRate
    # 0x14A3A8070 with current AuraLevel, not the action-start gauge level.
    aura = params["_AuraAtkRate"]["app.user_data.Wp03ActionParam.cAuraAtkRate"]
    return {"source": LONGSWORD_SOURCE, "auraRates": {"none": 1,
            "white": aura["_WhiteAtkRate"], "yellow": aura["_YellowAtkRate"], "red": aura["_RedAtkRate"]}}


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
    phial = profile.get("chargebladePhial")
    if phial is not None:
        kind = phial.get("kind")
        if (profile.get("scope") != "Wp09" or profile.get("rcol") != CHARGEBLADE_SHELL
                or phial.get("source") != CHARGEBLADE_SOURCE or kind not in {"impact", "element"}
                or profile.get("requestSetID") not in (range(11) if kind == "impact" else range(50, 61))
                or profile.get("actionType") != "NONE" or profile.get("specialType") != "NORMAL"
                or profile.get("canCritical") is not False or profile.get("ignoresSharpness") is not True
                or profile.get("usesAttackPower") is not (kind == "impact")
                or profile.get("elementSource") != ("none" if kind == "impact" else "weapon")
                or any(isinstance(phial.get(k), bool) or not isinstance(phial.get(k), (int, float))
                       or not math.isfinite(phial[k]) or phial[k] <= 0
                       for k in ("shieldMotionRate", "shieldElementRate"))
                or phial.get("shieldElementRate" if kind == "impact" else "shieldMotionRate") != 1):
            raise ValueError("Invalid charge blade phial parameters")
    chargeblade = profile.get("chargeblade")
    if chargeblade is not None:
        rate = chargeblade.get("shieldAxeMotionRate")
        if (profile.get("scope") != "Wp09" or chargeblade.get("source") != CHARGEBLADE_SOURCE
                or profile.get("rcol") != "Wp09/Collision/Collider/Wp09_Attack.rcol.38.json"
                or isinstance(rate, bool) or not isinstance(rate, (int, float))
                or not math.isfinite(rate) or rate <= 0):
            raise ValueError("Invalid charge blade shield parameters")
    horn = profile.get("huntinghorn")
    if horn is not None:
        rate = horn.get("selfEncoreAttackRate")
        if (profile.get("scope") != "Wp05" or horn.get("source") != MUSIC_SOURCE
                or isinstance(rate, bool) or not isinstance(rate, (int, float))
                or not math.isfinite(rate) or rate <= 0):
            raise ValueError("Invalid hunting horn self improvement parameters")
    extracts = profile.get("insectglaive")
    if extracts is not None:
        rates = extracts.get("extractRates", {})
        if (profile.get("scope") != "Wp10" or extracts.get("source") != INSECTGLAIVE_SOURCE
                or set(rates) != {"none", "redWhite", "triple"} or rates.get("none") != 1
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or v <= 0 for v in rates.values())):
            raise ValueError("Invalid insect glaive extract parameters")
    spirit = profile.get("longsword")
    if spirit is not None:
        rates = spirit.get("auraRates", {})
        if (profile.get("scope") != "Wp03" or spirit.get("source") != LONGSWORD_SOURCE
                or set(rates) != {"none", "white", "yellow", "red"} or rates.get("none") != 1
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or v <= 0 for v in rates.values())):
            raise ValueError("Invalid longsword aura parameters")
    dodge = profile.get("dualblades")
    if dodge is not None and (profile.get("scope") != "Wp02" or dodge.get("source") != DUALBLADES_SOURCE
            or any(isinstance(dodge.get(k), bool) or not isinstance(dodge.get(k), (float, int))
                   or not math.isfinite(dodge[k]) or dodge[k] <= 0 for k in ("attackRate", "elementMotionRate"))):
        raise ValueError("Invalid dual blades dodge parameters")
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
