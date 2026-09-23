"""Resolve quest targets to enemy layouts and difficulty/multiplayer rates."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.database.missions.health import SoloHealthCalculator


RATE_FIELDS = (
    "_RewardRank", "_RewardGrade", "_Health", "_Attack", "_PartsVital",
    "_DamageSlashBlow", "_DamageShot",
)
STATUS_FIELDS = ("_DefaultLimit", "_AddAndMaxLimit")
REQUIRED_STATUSES = (
    "_Poison", "_Paralyze", "_Sleep", "_Stun", "_Exhaust", "_Explosion",
    "_Ride", "_SkillStabbing", "_SkillRyuki",
)
TRAILING_RATE_FIELDS = (
    "_ScarNormalAndTear", "_ScarRaw", "_DyingHpVitalRate", "_CaptureHpVitalRate",
)
SIZE_FIELDS = ("_IsUseRandomSize", "_FixedSize")
ZERO_GUID = "00000000-0000-0000-0000-000000000000"
ENUM_PREFIX = re.compile(r"^\[-?\d+\]\s*")
RATE_TYPE = "app.user_data.EmParamDifficulty2.cDifficultyRate"
MULTI_TYPE = "app.user_data.EmParamDifficulty2.cMultiRateTable"
COUNT_TYPE = "app.user_data.EmParamDifficulty2.cMultiRate"
STATUS_TYPE = "app.user_data.EmParamDifficulty2.cBadConditionRate"
LAYOUT_TYPE = "app.user_data.EnemyLayoutDataBossZako"
MAIN_TARGET_TYPE = "app.user_data.EnemyLayoutDataBossZako.cMainTarget"


@dataclass(frozen=True, slots=True)
class MissionColumn:
    key: str
    top: str
    bottom: str | None = None
    section: str = "mission"


@dataclass(frozen=True, slots=True)
class MissionDifficultySchema:
    statuses: tuple[str, ...]
    counts: tuple[int, ...]
    count_fields: tuple[str, ...]

    def columns(self) -> tuple[MissionColumn, ...]:
        columns = []
        for field in RATE_FIELDS:
            if field == "_Health":
                columns.append(MissionColumn("SoloHealth", "SoloHealth", section="difficulty"))
            columns.append(MissionColumn(field, field, section="difficulty"))
        columns.append(MissionColumn("_DifficultyRankId", "_DifficultyRankId", section="difficulty"))
        columns.extend(
            MissionColumn(f"{status}.{field}", status, field, "status")
            for status in self.statuses for field in STATUS_FIELDS
        )
        columns.extend(
            MissionColumn(field, field, section="difficulty") for field in TRAILING_RATE_FIELDS
        )
        columns.append(MissionColumn("_MultiTableId", "_MultiTableId", section="multiplayer"))
        columns.extend(
            MissionColumn(f"_Count={count}.{field}", f"_Count = {count}", field, "multiplayer")
            for count in self.counts for field in self.count_fields
        )
        columns.extend(MissionColumn(field, field, section="size") for field in SIZE_FIELDS)
        return tuple(columns)


@dataclass(frozen=True, slots=True)
class MissionDifficultyCatalog:
    schema: MissionDifficultySchema
    targets: dict[tuple[str, int, int], dict[str, Any]]


def load_mission_difficulty(
    natives_dir: Path,
    quests: Iterable[tuple[Path, dict]],
    fixed_enemy_ids: dict[int, str],
) -> MissionDifficultyCatalog:
    source = natives_dir / "STM/GameDesign/Enemy/CommonData/Data/EmCommonDifficulty2.user.3.json"
    data = _typed(_read_json(source), "app.user_data.EmParamDifficulty2", source)
    rates = _guid_index(_array(data, "_DifficultyRateArray", RATE_TYPE), RATE_TYPE, source)
    multi_tables = _guid_index(_array(data, "_MultiRateTblArray", MULTI_TYPE), MULTI_TYPE, source)
    solo_health = SoloHealthCalculator(natives_dir, data)

    statuses = tuple(dict.fromkeys(
        key for rate in rates.values() for key, value in rate.items()
        if isinstance(value, dict) and STATUS_TYPE in value
    ))
    if not set(REQUIRED_STATUSES) <= set(statuses):
        raise ValueError(f"Missing required difficulty statuses in {source}")
    counts = tuple(sorted({
        entry["_Count"]
        for table in multi_tables.values()
        for entry in _multi_entries(table, source)
    }))
    count_fields = tuple(dict.fromkeys(
        key for table in multi_tables.values()
        for entry in _multi_entries(table, source)
        for key in entry if key != "_Count"
    ))
    schema = MissionDifficultySchema(statuses, counts, count_fields)

    targets: dict[tuple[str, int, int], dict[str, Any]] = {}
    for quest_source, quest in quests:
        mission_id = _symbol(quest["_MissionId"])
        main_targets = _main_targets_for_quest(natives_dir, quest_source)
        clears = quest["_ClearCondition"]
        clears = clears if isinstance(clears, list) else [clears]
        for clear_index, wrapped_clear in enumerate(clears):
            clear = _typed(wrapped_clear, "app.user_data.QuestData.cClearCondition", quest_source)
            target_type = _symbol(clear["_TargetType"])
            if target_type in ("ITEM", "EM_ZAKO_KILL") or not target_type.startswith("EM_"):
                continue
            for target_index, wrapped_target in enumerate(clear.get("_TargetInfoArray", [])):
                target = _typed(
                    wrapped_target, "app.user_data.QuestData.cClearCondition.cTargetInfo", quest_source
                )
                fixed_id = int(target["_TargetIDValue"]) & 0xFFFFFFFF
                enemy_id = fixed_enemy_ids.get(fixed_id)
                if enemy_id is None:
                    raise ValueError(f"Unknown fixed enemy ID {fixed_id} in {quest_source}")
                key = (
                    enemy_id, int(target["_EmTargetID"]), _symbol(target["_RoleID"]),
                    _symbol(target["_LegendaryID"]),
                )
                matches = [main for main in main_targets if _main_target_key(main) == key]
                if len(matches) != 1:
                    raise ValueError(
                        f"Expected one layout main target for {mission_id} {key}; found {len(matches)}"
                    )
                main = matches[0]
                rate_guid = _guid(main, "_DifficultyRankId", "app.cEmParamGuid_Difficulty2_DifficultyRate")
                rate = rates.get(rate_guid)
                if rate is None:
                    raise ValueError(f"Unknown difficulty rate {rate_guid} for {mission_id}")
                multi_guid = _guid(rate, "_MultiTableId", "app.cEmParamGuid_Difficulty2_MultiRateTbl")
                if multi_guid != ZERO_GUID and multi_guid not in multi_tables:
                    raise ValueError(f"Unknown multiplayer table {multi_guid} for {mission_id}")
                multi = multi_tables.get(multi_guid)
                targets[(mission_id, clear_index, target_index)] = _flatten_target(
                    schema, main, rate_guid, rate, multi_guid, multi, source,
                    solo_health.calculate(main, rate),
                )
    return MissionDifficultyCatalog(schema, targets)


def _flatten_target(
    schema: MissionDifficultySchema,
    main: dict,
    rate_guid: str,
    rate: dict,
    multi_guid: str,
    multi: dict | None,
    source: Path,
    health: int | str,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "_DifficultyRankId": rate_guid, "_MultiTableId": multi_guid, "SoloHealth": health,
    }
    for field in (*RATE_FIELDS, *TRAILING_RATE_FIELDS):
        value = rate[field]
        values[field] = _symbol(value) if field == "_RewardRank" else value
    for status in schema.statuses:
        if status not in rate:
            if status in REQUIRED_STATUSES:
                raise ValueError(f"Missing {status} in difficulty rate {rate_guid}: {source}")
            continue
        pair = _typed(rate[status], STATUS_TYPE, source)
        for field in STATUS_FIELDS:
            values[f"{status}.{field}"] = pair[field]
    if multi is not None:
        for entry in _multi_entries(multi, source):
            for field in schema.count_fields:
                if field in entry:
                    values[f"_Count={entry['_Count']}.{field}"] = entry[field]
    for field in SIZE_FIELDS:
        values[field] = main[field]
    return values


def _main_targets_for_quest(natives_dir: Path, quest_source: Path) -> list[dict]:
    mission_dir = quest_source.parent.parent if quest_source.parent.name == "_Quest" else quest_source.parent
    ms_source = mission_dir / quest_source.name.replace("_QuestData.user.3.json", "_MsData.user.3.json")
    if ms_source.exists():
        mission = _typed(_read_json(ms_source), "app.user_data.MissionData", ms_source)
        groups = mission["_EnemySetDataList"]
        use_index = int(mission["_QuestUseIndex"])
        if not 0 <= use_index < len(groups):
            raise ValueError(f"Invalid _QuestUseIndex {use_index} in {ms_source}")
        selected = _typed(groups[use_index], "app.user_data.MissionData.EmSetDataListParts", ms_source)
        layout_sources = []
        for part in selected["_EmSetDataList"]:
            em_set = _typed(part, "app.user_data.MissionData.EmSetDataParts", ms_source)
            layout_ref = em_set["_EmSet_BossZako"].get(LAYOUT_TYPE, {})
            path = layout_ref.get("path")
            if path:
                relative = path + ".3.json"
                layout_sources.append(natives_dir / "STM" / relative)
    else:
        # StreamQuestData may have an empty _EmSet_BossZako reference. Its
        # same-stem layout is the available source for target difficulty.
        companion = quest_source.with_name(
            quest_source.name.replace("_QuestData.user.3.json", "_BossZakoLayout.user.3.json")
        )
        layout_sources = [companion] if companion.exists() else []
    result = []
    for source in dict.fromkeys(layout_sources):
        layout = _typed(_read_json(source), LAYOUT_TYPE, source)
        result.extend(_typed(item, MAIN_TARGET_TYPE, source) for item in layout["_MainTargetDataList"])
    return result


def _main_target_key(main: dict) -> tuple[str, int, str, str]:
    return (
        _symbol(main["_EmID"]), int(main["_StoryTargetID"]),
        _symbol(main["_RoleID"]), _symbol(main["_LegendaryID"]),
    )


def _array(data: dict, field: str, item_type: str) -> list[dict]:
    wrapper = data[field]
    expected = f"ace.cInstanceGuidArray`1<{item_type}>"
    return wrapper[expected]["_DataArray"]


def _guid_index(items: list[dict], item_type: str, source: Path) -> dict[str, dict]:
    result = {}
    for wrapped in items:
        item = _typed(wrapped, item_type, source)
        guid = item["_InstanceGuid"]
        if guid in result:
            raise ValueError(f"Duplicate {item_type} GUID {guid} in {source}")
        result[guid] = item
    return result


def _multi_entries(table: dict, source: Path) -> list[dict]:
    entries = [_typed(item, COUNT_TYPE, source) for item in table["_MultiRateTbl"]]
    counts = [entry["_Count"] for entry in entries]
    if len(counts) != len(set(counts)):
        raise ValueError(f"Duplicate _Count in multiplayer table {table['_InstanceGuid']}: {source}")
    return entries


def _guid(data: dict, field: str, wrapper_type: str) -> str:
    return data[field][wrapper_type]["Value"]


def _symbol(value: Any) -> str:
    return ENUM_PREFIX.sub("", str(value))


def _read_json(source: Path) -> Any:
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _typed(data: Any, item_type: str, source: Path) -> dict:
    if isinstance(data, list):
        if len(data) != 1:
            raise ValueError(f"Expected one {item_type} record: {source}")
        data = data[0]
    value = data.get(item_type) if isinstance(data, dict) else None
    if not isinstance(value, dict):
        raise ValueError(f"Missing {item_type}: {source}")
    return value
