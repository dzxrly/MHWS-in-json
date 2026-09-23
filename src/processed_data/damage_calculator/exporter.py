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
from src.processed_data.damage_calculator.actions import action_labels
from src.processed_data.damage_calculator.bonuses import bonus_catalog

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


def _hit_profiles(natives_dir: Path, text_source: TextSource) -> list[dict]:
    action_data = natives_dir / "STM/GameDesign/Player/ActionData"
    records = load_action_value_request_sets(action_data)
    labels = action_labels(natives_dir, text_source)
    profiles = []
    for scope, request_sets in records.items():
        for record in request_sets:
            key = record.key
            rates = {}
            for output_key, source_key in PROFILE_RATE_FIELDS.items():
                value = record.properties.get(source_key)
                if not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"Missing or invalid {source_key}: {key}")
                rates[output_key] = value
            profiles.append({
                "id": f"{scope}|{key.rcol}|{key.request_set_id}|{key.key_hash}|{key.source_ordinal}",
                "scope": scope, "rcol": key.rcol, "requestSetID": key.request_set_id,
                "keyHash": key.key_hash, "sourceRequestSetOrdinal": key.source_ordinal,
                "actionType": _symbol(record.properties.get("_ActionTypeFixed._Value", "NONE")),
                "sourceAttack": record.properties.get("_Attack"),
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
    catalog = {
        "schemaVersion": 3, "language": "zh-Hans",
        "meatUnit": "source percent, divide by 100 in damage formula",
        "scope": "Monster part meat and source vitality plus player RCOL hit-rate profiles; no mission or runtime modifiers",
        "monsters": monsters,
        "hitProfiles": _hit_profiles(natives_dir, text_source),
        **bonus_catalog(natives_dir, repository, text_source),
    }
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: dict) -> None:
    if catalog.get("schemaVersion") != 3 or catalog.get("language") != "zh-Hans":
        raise ValueError("Unsupported calculator catalog schema")
    profile_ids = set()
    profiles = catalog.get("hitProfiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Empty hit profile list")
    for profile in profiles:
        profile_id = profile.get("id")
        if not isinstance(profile_id, str) or profile_id in profile_ids:
            raise ValueError(f"Invalid hit profile identity: {profile_id}")
        profile_ids.add(profile_id)
        attack = profile.get("sourceAttack")
        if not isinstance(attack, (int, float)) or not math.isfinite(attack) or attack < 0:
            raise ValueError(f"Invalid motion value: {profile_id}")
        if not isinstance(profile.get("actionNames"), list) or any(
            not isinstance(name, str) or not name for name in profile["actionNames"]
        ):
            raise ValueError(f"Invalid action names: {profile_id}")
        rates = profile.get("rates", {})
        if set(rates) != set(PROFILE_RATE_FIELDS) or any(
            not isinstance(value, (int, float)) or value < 0 for value in rates.values()
        ):
            raise ValueError(f"Invalid hit profile rates: {profile_id}")
    for skill in catalog.get("skills", []):
        if not skill.get("name") or not skill.get("levels"):
            raise ValueError(f"Invalid skill bonus: {skill.get('id')}")
        for level in skill["levels"]:
            if any(
                not isinstance(level.get(key), (int, float))
                or not math.isfinite(level[key]) or level[key] < 0
                for key in ("level", "percent", "flat")
            ):
                raise ValueError(f"Invalid skill level: {skill.get('id')}")
    if not catalog.get("skills") or not catalog.get("items"):
        raise ValueError("Empty bonus catalog")
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
