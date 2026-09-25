"""Build a deterministic, Chinese-labelled subset of monster part parameters."""

import argparse
import json
import math
import re
from pathlib import Path

from config import NATIVES_DIR, SUPPORT_FILES, ZH_HANS_LANGUAGE_ID
from src.shared.action_values.rcol import load_action_value_request_sets
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource
from src.processed_data.damage_calculator.actions import action_catalog
from src.processed_data.damage_calculator.contract import source_contract, validate_source_contract
from src.processed_data.damage_calculator.bonuses import item_catalog
from src.processed_data.damage_calculator.sharpness import sharpness_catalog
from src.processed_data.damage_calculator.multihit import physical_curve_points

OUTPUT_NAME = "damage_calculator.zh-Hans.json"
PARAM_GLOB = "STM/GameDesign/Enemy/Em*/*/Data/*_Param_Parts.user.3.json"
MEAT_FIELDS = ("Slash", "Blow", "Shot", "Fire", "Water", "Thunder", "Ice", "Dragon")
ZERO_GUID = "00000000-0000-0000-0000-000000000000"
PROFILE_RATE_FIELDS = {
    "PartsBreak": "_PartsBreakRate",
    "TearScarDamage": "_TearScarDamageRate",
    "RawScarDamage": "_RawScarDamageRate",
    "OldScarDamage": "_OldScarDamageRate",
}
PART_NAMES = {
    "HEAD": "头部", "TORSO": "躯干", "BODY": "身体", "HIDE": "外皮",
    "NECK": "颈部", "BACK": "背部", "STOMACH": "腹部", "CHEST": "胸部",
    "TAIL": "尾巴", "TAIL_TIP": "尾尖", "MOUTH": "嘴", "NOSE": "鼻",
    "LEFT_LEG": "左腿", "RIGHT_LEG": "右腿",
    "LEFT_FRONT_LEG": "左前腿", "RIGHT_FRONT_LEG": "右前腿",
    "LEFT_HIND_LEG": "左后腿", "RIGHT_HIND_LEG": "右后腿",
    "LEFT_WING": "左翼", "RIGHT_WING": "右翼",
    "LEFT_NAIL": "左爪", "RIGHT_NAIL": "右爪",
    "FULL_BODY": "全身", "FRONT_LEGS": "前腿", "HIND_LEGS": "后腿",
}
ENUM_NAME = re.compile(r"^\[-?\d+\]\s*(.*)$")


def _symbol(value: str) -> str:
    match = ENUM_NAME.fullmatch(value)
    return match.group(1) if match else value


def _typed_array(root: dict, field: str, item_type: str) -> list[dict]:
    wrapper = root.get(field, {})
    if not isinstance(wrapper, dict) or len(wrapper) != 1:
        raise ValueError(f"Invalid {field} wrapper")
    array = next(iter(wrapper.values())).get("_DataArray")
    if not isinstance(array, list):
        raise ValueError(f"Missing {field}._DataArray")
    result = []
    for item in array:
        if not isinstance(item, dict) or set(item) != {item_type} or not isinstance(item[item_type], dict):
            raise ValueError(f"Invalid {field} entry")
        result.append(item[item_type])
    return result


def _vital(entry: dict, key: str) -> list[float]:
    values = entry.get(key, [])
    if not isinstance(values, list):
        raise ValueError(f"Invalid {key} values")
    result = []
    for item in values:
        value = item["app.user_data.EmParamParts.cVital"]
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"Invalid {key} value: {value}")
        result.append(value)
    return result


def _meat(row: dict) -> dict[str, int]:
    result = {}
    for field in MEAT_FIELDS:
        value = row[f"_{field}"]
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(f"Invalid {field} meat: {value}")
        result[field.lower()] = value
    return result


def _monster_names(repository: SourceRepository, text_source: TextSource) -> dict[str, str]:
    text = text_source.build(ZH_HANS_LANGUAGE_ID)
    result = {}
    for row in repository.table(SUPPORT_FILES["enemy"]):
        enemy_id = row.get("enemyId")
        if enemy_id:
            result[enemy_id] = text.get(row.get("EnemyName", "")) or enemy_id
    return result


def _hit_profiles(natives_dir: Path, labels: dict) -> list[dict]:
    action_data = natives_dir / "STM/GameDesign/Player/ActionData"
    records = load_action_value_request_sets(action_data)
    profiles = []
    for scope, request_sets in records.items():
        for record in request_sets:
            key = record.key
            no_critical = record.properties.get("_IsNoCritical")
            if not isinstance(no_critical, bool):
                raise ValueError(f"Missing critical flag: {key}")
            rates = {}
            for output_key, source_key in PROFILE_RATE_FIELDS.items():
                value = record.properties.get(source_key)
                if not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"Missing or invalid {source_key}: {key}")
                rates[output_key] = value
            props = record.properties
            special = _symbol(props.get("_SpecialType._Value", "NORMAL"))
            element = _symbol(props.get("_AttackAttrFixed._Value", "NONE")).lower()
            element = {"elec": "thunder"}.get(element, element)
            element_source = ("weapon" if props["_UseStatusAttrPower"] else
                              "attack_scaled" if special == "BOWGUN_ELEMENT_SHOT" else
                              "intrinsic" if props.get("_AttrValue", 0) > 0 else "none")
            unsupported = []
            if special not in {"NORMAL", "BOWGUN_ELEMENT_SHOT"}:
                unsupported.append("该特殊命中的武器预处理尚未完整核验")
            if _symbol(props.get("_ActionTypeFixed._Value", "NONE")) == "NONE" and props.get("_Attack", 0):
                unsupported.append("无常规物理肉质类型，需专用伤害结算")
            profiles.append({
                "id": f"{scope}|{key.rcol}|{key.request_set_id}|{key.key_hash}|{key.source_ordinal}",
                "scope": scope, "rcol": key.rcol, "requestSetID": key.request_set_id,
                "keyHash": key.key_hash, "sourceRequestSetOrdinal": key.source_ordinal,
                "actionType": _symbol(record.properties.get("_ActionTypeFixed._Value", "NONE")),
                "sourceAttack": record.properties.get("_Attack"),
                "usesAttackPower": record.properties.get("_UseStatusAttackPower"),
                "usesElementPower": record.properties.get("_UseStatusAttrPower"),
                "canCritical": not no_critical,
                "ignoresSharpness": record.properties.get("_IsNoUseKireaji"),
                "forcesSharpnessAttackRate": record.properties.get("_IsForceUseKireajiAttackRate"),
                "elementRate": record.properties.get("_StatusAttrRate"),
                "sourceElement": props.get("_AttrValue", 0),
                "elementType": element,
                "elementSource": element_source,
                "sourceFixed": props.get("_FixAttack", 0),
                "specialType": special,
                "damageType": _symbol(props.get("_DamageTypeFixed._Value", "NORMAL")),
                "usesContinuousAttack": props.get("_UseSkillContinuousAttack", False),
                "usesAdditionalDamage": props.get("_UseSkillAdditionalDamage", False),
                "multiHit": {"enabled": "USE_MULIT_HIT" in str(props.get("_FlagBit", "")),
                             "physicalCurve": props.get("_MultiHitRateCurve.path", ""),
                             "statusCurve": props.get("_MultiHitStatusRateCurve.path", ""),
                             "physicalCurvePoints": physical_curve_points(natives_dir, props.get("_MultiHitRateCurve.path", ""))},
                "support": {"status": "unsupported" if unsupported else "basic_hit",
                            "reasons": unsupported},
                "actionNames": labels.get(key, []),
                "rates": rates,
            })
    if not profiles:
        raise ValueError(f"No player hit profiles under {action_data}")
    return profiles


def build_catalog(natives_dir: Path, repository: SourceRepository, text_source: TextSource) -> dict:
    natives_dir = Path(natives_dir)
    names = _monster_names(repository, text_source)
    monsters = []
    seen_monsters = set()
    for path in sorted(natives_dir.glob(PARAM_GLOB)):
        monster_id = path.name.split("_Param_Parts.", 1)[0].upper() + "_0"
        if monster_id in seen_monsters:
            raise ValueError(f"Duplicate monster part table: {monster_id}")
        seen_monsters.add(monster_id)
        document = json.loads(path.read_text(encoding="utf-8"))
        root = document[0]["app.user_data.EmParamParts"]
        meats = _typed_array(root, "_MeatArray", "app.user_data.EmParamParts.cMeat")
        meat_by_guid = {row["_InstanceGuid"]: row for row in meats}
        if len(meat_by_guid) != len(meats):
            raise ValueError(f"Duplicate meat GUID in {path}")
        part_rows = _typed_array(root, "_PartsArray", "app.user_data.EmParamParts.cParts")
        scar_rows = _typed_array(root, "_ScarPointArray", "app.user_data.EmParamParts.cScarPoint")
        part_guids = {row["_InstanceGuid"] for row in part_rows}
        if not part_rows or len(part_guids) != len(part_rows):
            raise ValueError(f"Missing or duplicate part GUID in {path}")
        if any(row["_LinkPartsGuid"] not in part_guids for row in scar_rows):
            raise ValueError(f"Scar references missing part in {path}")

        parts = []
        for ordinal, row in enumerate(part_rows, start=1):
            variants = []
            for key, source_key in (
                ("normal", "_MeatGuidNormal"), ("break", "_MeatGuidBreak"),
                *((f"custom{index}", f"_MeatGuidCustom{index}") for index in range(1, 6)),
            ):
                guid = row.get(source_key, ZERO_GUID)
                if guid == ZERO_GUID:
                    if key == "normal":
                        raise ValueError(f"Missing normal meat for {monster_id} part {ordinal}")
                    continue
                if guid not in meat_by_guid:
                    if key == "normal":
                        raise ValueError(f"Missing normal meat GUID {guid} in {path}")
                    variants.append({"key": key, "meatGuid": guid, "meat": None})
                    continue
                variants.append({"key": key, "meatGuid": guid, "meat": _meat(meat_by_guid[guid])})
            part_type = _symbol(row["_PartsType"])
            scars = []
            for scar in scar_rows:
                if scar["_LinkPartsGuid"] != row["_InstanceGuid"]:
                    continue
                guid = scar["_MeatGuid"]
                if guid not in meat_by_guid:
                    raise ValueError(f"Missing scar meat GUID {guid} in {path}")
                scars.append({
                    "id": scar["_InstanceGuid"], "meatGuid": guid, "meat": _meat(meat_by_guid[guid]),
                    "normalVital": _vital(scar, "_NormalVital"),
                    "tearVital": _vital(scar, "_TearVital"),
                    "rawScarVital": _vital(scar, "_RawScarVital"),
                })
            parts.append({
                "id": row["_InstanceGuid"], "type": part_type,
                "name": PART_NAMES.get(part_type, part_type),
                "ordinal": ordinal, "vital": _vital(row, "_Vital"),
                "vitalEnabled": bool(row.get("_IsEnablePartsVital", False)),
                "variants": variants, "scars": scars,
            })
        monsters.append({
            "id": monster_id, "name": names.get(monster_id, monster_id),
            "sourceFile": path.relative_to(natives_dir).as_posix(),
            "parts": parts,
        })
    if not monsters:
        raise ValueError(f"No monster part tables under {natives_dir}")
    labels, actions, mapping = action_catalog(natives_dir, text_source)
    status_path = "STM/GameDesign/Player/ActionData/Common/GlobalParam/Part/PlayerStatusParam.user.3.json"
    status = json.loads((natives_dir / status_path).read_text(encoding="utf-8"))[0]["app.user_data.PlayerStatusParam"]
    catalog = {
        "schemaVersion": 10, "language": "zh-Hans",
        "sourceContract": source_contract(natives_dir),
        "actionMap": mapping,
        "units": {"attack": "true_attack", "weaponElement": "display_divided_by_10",
                  "motion": "percent", "ammoElement": "current_attack_percent", "intrinsicElement": "true_element"},
        "rules": {"attackRateLimit": status["_PhysicalAttack_RateLimit"],
                  "attackAddLimit": status["_PhysicalAttack_AddLimit"],
                  "elementRateLimit": status["_ElementAttack_RateLimit"],
                  "elementAddLimit": status["_ElementAttack_AddLimit"],
                  "gunElementRateLimit": status["_ElementAttack_RateLimit_Gun"],
                  "source": status_path,
                  "nativeVersion": "1.42.0.2",
                  "nativeMethods": ["cHunterWpGunHandling.doOnHit_AttackPre510644",
                                    "HunterCharacter.makeActualAttackParam731166",
                                    "cHunterAttackPower.calcAttrPower491942",
                                    "cHunterAttackPower.calcCurrentAttackPower491937"]},
        "meatUnit": "source percent, divide by 100 in damage formula",
        "scope": "Monster part meat and source vitality plus player RCOL hit-rate profiles; no mission or runtime modifiers",
        "monsters": monsters,
        "hitProfiles": _hit_profiles(natives_dir, labels),
        "actions": actions,
        "sharpness": sharpness_catalog(natives_dir),
        **item_catalog(natives_dir),
    }
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: dict) -> None:
    if catalog.get("schemaVersion") != 10 or catalog.get("language") != "zh-Hans":
        raise ValueError("Unsupported calculator catalog schema")
    validate_source_contract(catalog.get("sourceContract", {}))
    for key in ("attackRateLimit", "attackAddLimit", "elementRateLimit", "elementAddLimit", "gunElementRateLimit"):
        value = catalog.get("rules", {}).get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid calculator rule: {key}")
    sharpness = catalog.get("sharpness")
    if not isinstance(sharpness, list) or len(sharpness) != 7 or len({
        entry.get("id") for entry in sharpness
    }) != 7:
        raise ValueError("Invalid sharpness colors")
    for entry in sharpness:
        if not isinstance(entry.get("name"), str) or not entry["name"]:
            raise ValueError("Invalid sharpness name")
        if any(not isinstance(entry.get(key), (int, float)) or isinstance(entry[key], bool)
               or not math.isfinite(entry[key]) or entry[key] <= 0
               for key in ("physical", "element")):
            raise ValueError(f"Invalid sharpness rates: {entry.get('id')}")
    profile_ids = set()
    profiles = catalog.get("hitProfiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Empty hit profile list")
    for profile in profiles:
        profile_id = profile.get("id")
        if not isinstance(profile_id, str) or profile_id in profile_ids:
            raise ValueError(f"Invalid hit profile identity: {profile_id}")
        profile_ids.add(profile_id)
        for field in ("sourceElement", "sourceFixed"):
            value = profile.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {field}: {profile_id}")
        if profile.get("elementSource") not in {"none", "weapon", "intrinsic", "attack_scaled"}:
            raise ValueError(f"Invalid element source: {profile_id}")
        if profile.get("elementType") not in {"none", "fire", "water", "thunder", "ice", "dragon"}:
            raise ValueError(f"Invalid element type: {profile_id}")
        attack = profile.get("sourceAttack")
        if not isinstance(attack, (int, float)) or not math.isfinite(attack) or attack < 0:
            raise ValueError(f"Invalid motion value: {profile_id}")
        if not isinstance(profile.get("usesAttackPower"), bool) or not isinstance(
            profile.get("usesElementPower"), bool
        ) or not isinstance(profile.get("canCritical"), bool):
            raise ValueError(f"Invalid player stat usage: {profile_id}")
        if not isinstance(profile.get("ignoresSharpness"), bool) or not isinstance(
            profile.get("forcesSharpnessAttackRate"), bool
        ):
            raise ValueError(f"Invalid sharpness flags: {profile_id}")
        element_rate = profile.get("elementRate")
        if not isinstance(element_rate, (int, float)) or not math.isfinite(
            element_rate
        ) or element_rate < 0:
            raise ValueError(f"Invalid action element rate: {profile_id}")
        if not isinstance(profile.get("actionNames"), list) or any(
            not isinstance(name, str) or not name for name in profile["actionNames"]
        ):
            raise ValueError(f"Invalid action names: {profile_id}")
        rates = profile.get("rates", {})
        if set(rates) != set(PROFILE_RATE_FIELDS) or any(
            not isinstance(value, (int, float)) or value < 0 for value in rates.values()
        ):
            raise ValueError(f"Invalid hit profile rates: {profile_id}")
    action_ids = set()
    for action in catalog.get("actions", []):
        if action["id"] in action_ids or action["profileId"] not in profile_ids or not action["weapons"]:
            raise ValueError("Invalid action reference")
        action_ids.add(action["id"])
        level = action.get("ammoLevel")
        if not action.get("name") or not isinstance(level, int) or isinstance(level, bool) or level < 1:
            raise ValueError("Invalid action metadata")
        shell = action.get("shell")
        if shell is not None and level not in {1, 2, 3}:
            raise ValueError("Invalid bowgun ammunition level")
        levels = action.get("ammoLevels")
        if not isinstance(levels, list) or not levels or level not in levels or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in levels
        ) or (shell is not None and any(value not in {1, 2, 3} for value in levels)):
            raise ValueError("Invalid selectable ammunition levels")
        if action.get("arrowType") is not None and not isinstance(action["arrowType"], str):
            raise ValueError("Invalid arrow type")
        if shell is not None and (not shell.get("source") or not shell.get("type") or any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
            for value in shell.get("parameters", {}).values()
        )):
            raise ValueError("Invalid shell parameters")
    if not action_ids or len(catalog.get("sourceContract", {}).get("id", "")) != 64:
        raise ValueError("Missing action catalog or source contract")
    if "skills" in catalog or not catalog.get("items"):
        raise ValueError("Skills must be exported only by skill_effects; item catalog is required")
    for item in catalog["items"]:
        flat = item.get("flat")
        if (not item.get("name") or not item.get("group")
                or not isinstance(flat, (int, float)) or not math.isfinite(flat) or flat < 0):
            raise ValueError(f"Invalid item bonus: {item.get('id')}")
    monsters = catalog.get("monsters")
    if not isinstance(monsters, list) or not monsters:
        raise ValueError("Empty calculator monster list")
    monster_ids = set()
    for monster in monsters:
        monster_id = monster.get("id")
        if not isinstance(monster_id, str) or monster_id in monster_ids or not monster.get("name"):
            raise ValueError(f"Invalid monster identity: {monster_id}")
        monster_ids.add(monster_id)
        parts = monster.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"Missing parts: {monster_id}")
        part_ids = set()
        for part in parts:
            part_id = part.get("id")
            if not isinstance(part_id, str) or part_id in part_ids:
                raise ValueError(f"Invalid part identity: {monster_id}/{part_id}")
            part_ids.add(part_id)
            variants = part.get("variants", [])
            if not any(variant.get("key") == "normal" and variant.get("meat") for variant in variants):
                raise ValueError(f"Missing normal meat: {monster_id}/{part_id}")
            for item in [*variants, *part.get("scars", [])]:
                meat = item.get("meat")
                if meat is None and item in variants and item.get("key") != "normal":
                    continue  # Source contains a reference to a missing alternate table.
                if not isinstance(meat, dict) or set(meat) != {field.lower() for field in MEAT_FIELDS}:
                    raise ValueError(f"Invalid meat: {monster_id}/{part_id}")
                if any(not isinstance(value, int) or not 0 <= value <= 100 for value in meat.values()):
                    raise ValueError(f"Invalid meat value: {monster_id}/{part_id}")


def export_damage_calculator(path: Path, repository: SourceRepository, text_source: TextSource) -> Path:
    catalog = build_catalog(repository.root, repository, text_source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--natives", type=Path, default=NATIVES_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = SourceRepository(args.natives)
    source = TextSource.from_natives(args.natives)
    export_damage_calculator(args.output, repository, source)
    print(args.output)


if __name__ == "__main__":
    main()
