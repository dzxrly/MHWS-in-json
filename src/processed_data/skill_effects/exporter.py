"""Export one auditable skill catalog for damage calculator consumers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from config import NATIVES_DIR, SUPPORT_FILES, ZH_HANS_LANGUAGE_ID
from src.processed_data.skill_effects.specs import (
    ELEMENTS, MELEE_WEAPONS, PARAMETER_CANDIDATES, PENDING_DAMAGE_IDS,
    RANGED_WEAPONS, SLOT_EFFECTS, WEAPONS,
)
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource


OUTPUT_NAME = "skill_effects.zh-Hans.json"
SKILL_DATA = "STM/GameDesign/Common/Equip/SkillData.user.3.json"
SKILL_PARAM = "STM/GameDesign/Player/ActionData/Common/GlobalParam/Part/PlayerSkillParam.user.3.json"
STATUS_PARAM = "STM/GameDesign/Player/ActionData/Common/GlobalParam/Part/PlayerStatusParam.user.3.json"
SOURCE_FILES = (SUPPORT_FILES["skill_common"], SKILL_DATA, SKILL_PARAM, STATUS_PARAM)
STAGES = frozenset({
    "attack.stat.rate", "attack.stat.flat", "attack.hit.rate", "attack.hit.flat",
    "element.stat.rate", "element.stat.flat", "physical.critical.rate",
    "element.critical.rate", "part.rate",
})


def _param_root(natives_dir: Path, path: str, type_name: str) -> dict:
    document = json.loads((natives_dir / path).read_text(encoding="utf-8"))
    return document[0][type_name]


def _pack(root: dict, field: str) -> list[float]:
    wrapper = root[field]
    pack = wrapper["app.user_data.PlayerSkillParam.cSkillBasicDataPack"]["_DataPack"]
    result = [float(entry["app.user_data.PlayerSkillParam.cSkillBasicData"]) for entry in pack]
    if not result or any(not math.isfinite(value) or value < 0 for value in result):
        raise ValueError(f"Invalid PlayerSkillParam pack: {field}")
    return result


def _effect(stage: str, value: float, source: str, **scope: object) -> dict:
    return {"stage": stage, "value": value, "source": source, **scope}


def _slot_effects(skill_id: str, values: list[int]) -> list[dict]:
    result = []
    for stage, slot, unit in SLOT_EFFECTS.get(skill_id, ()):
        if slot >= len(values):
            raise ValueError(f"Missing {skill_id} value[{slot}]")
        raw = values[slot]
        value = raw / 100 if unit == "percent" else raw
        scope = {}
        if skill_id in ELEMENTS:
            scope["element"] = ELEMENTS[skill_id]
        if skill_id in {"HunterSkill_018", "HunterSkill_020"}:
            scope["weapons"] = list(MELEE_WEAPONS)
        elif skill_id == "HunterSkill_047":
            scope["weapons"] = ["switchaxe", "chargeblade"]
        elif skill_id == "HunterSkill_057":
            scope["weapons"] = ["hammer"]
        result.append(_effect(stage, value, f"SkillData._value[{slot}]", **scope))
    return result


def _element_critical(level: int, params: dict) -> list[dict]:
    rates = _pack(params, "_AttrPowerRateData")
    if len(rates) != 6:
        raise ValueError("Unexpected elemental critical pack layout")
    strong = {WEAPONS[index] for index in (0, 4, 5, 12)}
    return [
        _effect("element.critical.rate", rates[level - 1],
                f"PlayerSkillParam._AttrPowerRateData[{level - 1}]",
                weapons=[weapon for weapon in WEAPONS if weapon not in strong]),
        _effect("element.critical.rate", rates[level + 2],
                f"PlayerSkillParam._AttrPowerRateData[{level + 2}]",
                weapons=[weapon for weapon in WEAPONS if weapon in strong]),
    ]


def _burst(level: int, params: dict) -> list[dict]:
    result = []
    for index, weapon in enumerate(WEAPONS):
        field = f"_ContinuousAttackWp{index:02d}Data"
        values = _pack(params, field)
        if len(values) == 13:
            initial_attack, initial_element = values[1:3]
            reinforced_attack = values[3 + (level - 1) * 2]
            reinforced_element = values[4 + (level - 1) * 2]
        elif len(values) == 7:
            initial_attack, initial_element = values[1], None
            reinforced_attack, reinforced_element = values[level + 1], None
        else:
            raise ValueError(f"Unexpected continuous attack layout for {weapon}")
        for state, attack, element in (
            ("initial", initial_attack, initial_element),
            ("reinforced", reinforced_attack, reinforced_element),
        ):
            result.append(_effect("attack.stat.flat", attack,
                                  f"PlayerSkillParam.{field}", weapons=[weapon], state=state))
            if element is not None:
                result.append(_effect("element.stat.flat", element,
                                      f"PlayerSkillParam.{field}", weapons=[weapon], state=state))
    return result


def _ballistic(level: int, params: dict) -> list[dict]:
    if level != 3:
        return []
    result = []
    for index, weapon in ((11, "bow"), (12, "heavybowgun"), (13, "lightbowgun")):
        field = f"_Ballistic_Wp{index}AttackAdd"
        result.append(_effect("attack.hit.flat", float(params[field]),
                              f"PlayerSkillParam.{field}", weapons=[weapon]))
    return result


def _effects(skill_id: str, level: int, values: list[int], params: dict) -> list[dict]:
    result = _slot_effects(skill_id, values)
    if skill_id == "HunterSkill_003":
        result.extend(_element_critical(level, params))
    elif skill_id == "HunterSkill_114":
        result.extend(_burst(level, params))
    elif skill_id == "HunterSkill_019":
        result.extend(_ballistic(level, params))
    return result


def build_catalog(natives_dir: Path, repository: SourceRepository, text_source: TextSource) -> dict:
    natives_dir = Path(natives_dir)
    text = text_source.build(ZH_HANS_LANGUAGE_ID)
    params = _param_root(natives_dir, SKILL_PARAM, "app.user_data.PlayerSkillParam")
    status = _param_root(natives_dir, STATUS_PARAM, "app.user_data.PlayerStatusParam")
    levels_by_id: dict[str, list[dict]] = {}
    for row in repository.table(SKILL_DATA):
        levels_by_id.setdefault(row["skillId"], []).append(row)

    skills = []
    for row in repository.table(SUPPORT_FILES["skill_common"]):
        skill_id = row["skillId"]
        if skill_id == "NONE":
            continue
        levels = []
        for data in sorted(levels_by_id.get(skill_id, []), key=lambda item: item["SkillLv"]):
            level = data["SkillLv"]
            raw = data["value"]
            levels.append({
                "level": level,
                "description": text.get(data["skillExplain"]) or "",
                "rawValues": raw,
                "effects": _effects(skill_id, level, raw, params),
            })
        has_effect = any(level["effects"] for level in levels)
        verification = (
            "verified" if has_effect else
            "parameter_found" if skill_id in PARAMETER_CANDIDATES else
            "unresolved" if skill_id in PENDING_DAMAGE_IDS else
            "not_audited"
        )
        entry = {
            "id": skill_id,
            "name": text.get(row["skillName"]) or skill_id,
            "description": text.get(row["skillExplain"]) or "",
            "category": row["skillCategory"],
            "verification": verification,
            "levels": levels,
        }
        if skill_id in PARAMETER_CANDIDATES:
            entry["candidateSources"] = list(PARAMETER_CANDIDATES[skill_id])
        if skill_id == "HunterSkill_114":
            entry["states"] = [
                {"id": "initial", "name": "发动后"},
                {"id": "reinforced", "name": "强化后"},
            ]
        skills.append(entry)

    catalog = {
        "schemaVersion": 1,
        "language": "zh-Hans",
        "assumptions": {"skillsAlreadyActive": True, "criticalChance": 1},
        "rules": {
            "physicalCriticalBase": float(status["_CriticalAttackRate"]),
            "source": "PlayerStatusParam._CriticalAttackRate",
        },
        "sourceHashes": {
            path: hashlib.sha256((natives_dir / path).read_bytes()).hexdigest()
            for path in SOURCE_FILES
        },
        "skills": skills,
    }
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: dict) -> None:
    if catalog.get("schemaVersion") != 1 or catalog.get("language") != "zh-Hans":
        raise ValueError("Unsupported skill effect schema")
    if catalog.get("assumptions") != {"skillsAlreadyActive": True, "criticalChance": 1}:
        raise ValueError("Unexpected skill calculation assumptions")
    base = catalog.get("rules", {}).get("physicalCriticalBase")
    if not isinstance(base, (int, float)) or isinstance(base, bool) or not math.isfinite(base) or base < 1:
        raise ValueError("Invalid base critical rate")
    hashes = catalog.get("sourceHashes")
    if not isinstance(hashes, dict) or set(hashes) != set(SOURCE_FILES) or any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in hashes.values()
    ):
        raise ValueError("Invalid skill source hashes")
    skills = catalog.get("skills")
    if not isinstance(skills, list) or not skills:
        raise ValueError("Empty skill catalog")
    ids = set()
    for skill in skills:
        skill_id = skill.get("id")
        if not isinstance(skill_id, str) or not skill_id.startswith("HunterSkill_") or skill_id in ids:
            raise ValueError(f"Invalid skill identity: {skill_id}")
        ids.add(skill_id)
        if not skill.get("name") or skill.get("verification") not in {
            "verified", "parameter_found", "unresolved", "not_audited"
        }:
            raise ValueError(f"Invalid skill metadata: {skill_id}")
        states = skill.get("states", [])
        if not isinstance(states, list) or any(
            not isinstance(state, dict) or not isinstance(state.get("id"), str)
            or not state["id"] or not isinstance(state.get("name"), str) or not state["name"]
            for state in states
        ):
            raise ValueError(f"Invalid skill states: {skill_id}")
        state_ids = {state["id"] for state in states}
        if len(state_ids) != len(states):
            raise ValueError(f"Duplicate skill state: {skill_id}")
        levels = skill.get("levels")
        if not isinstance(levels, list):
            raise ValueError(f"Invalid skill level list: {skill_id}")
        seen_levels = set()
        has_effect = False
        for level in levels:
            number = level.get("level")
            if not isinstance(number, int) or isinstance(number, bool) or number < 1 or number in seen_levels:
                raise ValueError(f"Invalid skill level: {skill_id}/{number}")
            seen_levels.add(number)
            raw = level.get("rawValues")
            if not isinstance(raw, list) or len(raw) != 4 or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in raw
            ):
                raise ValueError(f"Invalid raw skill values: {skill_id}/{number}")
            effects = level.get("effects")
            if not isinstance(effects, list):
                raise ValueError(f"Invalid skill effect list: {skill_id}/{number}")
            if skill["verification"] != "verified" and effects:
                raise ValueError(f"Unverified skill has numeric effects: {skill_id}")
            has_effect |= bool(effects)
            for effect in effects:
                if not isinstance(effect, dict):
                    raise ValueError(f"Invalid skill effect record: {skill_id}/{number}")
                value = effect.get("value")
                stage = effect.get("stage")
                if stage not in STAGES or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0 or (stage.endswith(".rate") and value == 0):
                    raise ValueError(f"Invalid skill effect: {skill_id}/{number}")
                if not isinstance(effect.get("source"), str) or not effect["source"]:
                    raise ValueError(f"Missing skill effect source: {skill_id}/{number}")
                weapons = effect.get("weapons")
                if weapons is not None and (
                    not isinstance(weapons, list) or not weapons
                    or any(not isinstance(weapon, str) or weapon not in WEAPONS for weapon in weapons)
                    or len(weapons) != len(set(weapons))
                ):
                    raise ValueError(f"Unknown effect weapon: {skill_id}/{number}")
                if "element" in effect and effect["element"] not in ELEMENTS.values():
                    raise ValueError(f"Unknown effect element: {skill_id}/{number}")
                if (states and effect.get("state") not in state_ids) or (not states and "state" in effect):
                    raise ValueError(f"Unknown effect state: {skill_id}/{number}")
        if (skill["verification"] == "verified") != has_effect:
            raise ValueError(f"Inconsistent skill verification: {skill_id}")
    if not all(key in ids for key in (*SLOT_EFFECTS, "HunterSkill_003", "HunterSkill_019", "HunterSkill_114")):
        raise ValueError("Missing audited skills")


def export_skill_effects(path: Path, repository: SourceRepository, text_source: TextSource) -> Path:
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
    print(export_skill_effects(args.output, repository, source))


if __name__ == "__main__":
    main()
