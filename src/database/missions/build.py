"""Read quest definitions and prepare one localized row per clear target."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.database.missions.difficulty import (
    MissionColumn,
    MissionDifficultyCatalog,
    load_mission_difficulty,
)
from src.shared.text.catalog import TextSource
from src.database.missions.text import MissionTextResolver, mission_content as _content_at
from src.shared.source.user3 import load_user3_table
from src.shared.source.repository import SourceRepository


MISSION_PREFIX_COLUMNS = (
    "_MissionId",
    "_QuestLv",
    "_OrderHR",
    "_OrderMR",
    "_TitleMsg",
    "MonsterName",
    "_TargetType",
    "_LegendaryID",
)
MISSION_TAIL_COLUMNS = (
    "_Version",
    "_QuestType",
    "_QuestAttribute",
    "_MaxPlayerNum",
    "_TimeLimit",
    "_RemMoney",
    "_HRPoint",
    "_AddPoint",
    "_EnableGuestNpc",
    "_Stage",
    "_BattleBGM",
    "_ClearBGM",
    "_DetailMsg",
)
MISSION_COLUMNS = (*MISSION_PREFIX_COLUMNS, *MISSION_TAIL_COLUMNS, "_SubBossInfoArray")
TARGET_COLUMNS = frozenset({"MonsterName", "_TargetType", "_LegendaryID"})
BASE_HEADERS = tuple(
    MissionColumn(column, column, section="target" if column in TARGET_COLUMNS else "mission")
    for column in MISSION_COLUMNS
)

# StreamQuestTextData uses field names instead of msg language indices. Preserve
# the source's spellings, including its two Chinese field-name typos.
STREAM_TEXT_FIELDS = {
    0: "_JapaneseList",
    1: "_EnglishList",
    2: "_FrenchList",
    3: "_ItalianList",
    4: "_GermanList",
    5: "_SpanishList",
    6: "_RussianList",
    7: "_PolishList",
    10: "_PortugueseBrList",
    11: "_KoreanList",
    12: "_TransitionalChineseList",
    13: "_SimplelifiedChineseList",
    21: "_ArabicList",
    26: "_ThaiList",
    32: "_LatinAmericanSpanishList",
}

# These are quest-attribute labels, not quest-type labels. When no matching
# in-game text exists (NORMAL, for example), retain the English enum symbol.
ATTRIBUTE_TEXT_NAMES = {
    "SIDE_MISSION": ("MsgGUI020203_0001", "MsgGUI030500_0002_01"),
}
MISSION_TEXT_SUFFIXES = {
    "_TitleMsg": ("100", "000"),
    "_DetailMsg": ("102", "001"),
}
ENUM_PREFIX = re.compile(r"^\[-?\d+\]\s*")
MISSION_NUMBER = re.compile(r"MISSION_(\d+)$")


@dataclass(frozen=True, slots=True)
class QuestRecord:
    source: Path
    data: dict
    stream_text: dict | None


@dataclass(frozen=True, slots=True)
class MissionCatalog:
    quests: tuple[QuestRecord, ...]
    fixed_enemy_ids: dict[int, str]
    enemy_name_guids: dict[str, str]
    missions_without_quest_data: tuple[str, ...] = ()
    difficulty: MissionDifficultyCatalog | None = None


@dataclass(frozen=True, slots=True)
class MissionWorkbookData:
    rows: list[dict]
    groups: tuple[tuple[int, int], ...]
    headers: tuple[MissionColumn, ...] = BASE_HEADERS

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(header.key for header in self.headers)


def load_mission_catalog(natives_dir: Path, enums_path: Path, repository: SourceRepository | None = None) -> MissionCatalog:
    natives_dir = Path(natives_dir)
    mission_dir = natives_dir / "STM/GameDesign/Mission"
    if not mission_dir.is_dir():
        raise FileNotFoundError(f"Mission directory not found: {mission_dir}")

    enums = _read_json(enums_path)
    quest_attributes = enums["app.QuestDef.QUEST_ATTRIBUTE"]
    fixed_enemy_ids: dict[int, str] = {}
    for enemy_id, value in enums["app.EnemyDef.ID_Fixed"].items():
        if not enemy_id.startswith("EM"):
            continue
        unsigned = int(value) & 0xFFFFFFFF
        if unsigned in fixed_enemy_ids and fixed_enemy_ids[unsigned] != enemy_id:
            raise ValueError(f"Duplicate fixed enemy ID {unsigned}: {enemy_id}")
        fixed_enemy_ids[unsigned] = enemy_id

    enemy_path = natives_dir / "STM/GameDesign/Common/Enemy/EnemyData.user.3.json"
    enemy_name_guids: dict[str, str] = {}
    enemies = repository.table(str(enemy_path.relative_to(natives_dir)).replace("\\", "/")) if repository else load_user3_table(enemy_path)
    for enemy in enemies:
        enemy_id = enemy.get("enemyId")
        name_guid = enemy.get("EnemyName")
        if not enemy_id or not name_guid:
            continue
        if enemy_id in enemy_name_guids and enemy_name_guids[enemy_id] != name_guid:
            raise ValueError(f"Conflicting EnemyName GUID for {enemy_id}")
        enemy_name_guids[enemy_id] = name_guid

    quests: list[QuestRecord] = []
    seen_missions: set[str] = set()
    for source in mission_dir.rglob("*_QuestData.user.3.json"):
        quest = _typed(_read_json(source), "app.user_data.QuestData", source)
        mission_id = _enum_symbol(quest["_MissionId"])
        attribute = _enum_symbol(quest["_QuestAttribute"])
        if attribute not in quest_attributes:
            raise ValueError(f"Unknown quest attribute {attribute} in {source}")
        numeric_attribute = re.match(r"^\[(-?\d+)\]", quest["_QuestAttribute"])
        if numeric_attribute and int(numeric_attribute.group(1)) & 0xFFFFFFFF != quest_attributes[attribute]:
            raise ValueError(f"Quest attribute enum mismatch for {mission_id} in {source}")
        if mission_id in seen_missions:
            raise ValueError(f"Duplicate mission ID: {mission_id}")
        seen_missions.add(mission_id)
        stream_source = source.with_name(
            source.name.replace("_QuestData.user.3.json", "_StreamQuestTextData.user.3.json")
        )
        stream_text = (
            _typed(_read_json(stream_source), "app.user_data.StreamQuestTextData", stream_source)
            if stream_source.exists()
            else None
        )
        quests.append(QuestRecord(source, quest, stream_text))
    quests.sort(key=_quest_sort_key)
    if not quests:
        raise ValueError(f"No QuestData files found: {mission_dir}")
    mission_ids: set[str] = set()
    for source in mission_dir.rglob("*_MsData.user.3.json"):
        mission = _typed(_read_json(source), "app.user_data.MissionData", source)
        mission_id = _enum_symbol(mission["_MissionIDSerial"])
        if mission_id in mission_ids:
            raise ValueError(f"Duplicate MsData mission ID: {mission_id}")
        mission_ids.add(mission_id)
    missions_without_quest_data = tuple(sorted(mission_ids - seen_missions, key=_mission_id_sort_key))
    difficulty = load_mission_difficulty(
        natives_dir,
        ((record.source, record.data) for record in quests),
        fixed_enemy_ids,
    )
    return MissionCatalog(
        tuple(quests), fixed_enemy_ids, enemy_name_guids, missions_without_quest_data,
        difficulty,
    )


def build_mission_workbook_data(
    catalog: MissionCatalog, text_source: TextSource, language_id: int
) -> MissionWorkbookData:
    text = MissionTextResolver(text_source, language_id)
    rows: list[dict] = []
    groups: list[tuple[int, int]] = []
    headers = (
        BASE_HEADERS[:len(MISSION_PREFIX_COLUMNS)]
        + catalog.difficulty.schema.columns()
        + BASE_HEADERS[len(MISSION_PREFIX_COLUMNS):]
        if catalog.difficulty else BASE_HEADERS
    )
    columns = tuple(header.key for header in headers)
    for record in catalog.quests:
        quest = record.data
        mission_id = _enum_symbol(quest["_MissionId"])
        clears = _typed_conditions(quest["_ClearCondition"], record.source)
        order = _typed(quest["_OrderCondition"], "app.user_data.QuestData.cOrderCondition", record.source)
        messages = _typed(quest["_QuestMsg"], "app.user_data.QuestData.cQuestMsg", record.source)
        title = _quest_text(record, text, messages["_TitleMsg"], "100", mission_id)
        detail = _quest_text(record, text, messages["_DetailMsg"], "102", mission_id)
        sub_bosses = list(
            dict.fromkeys(
                _enemy_name(
                    catalog,
                    text,
                    _enum_symbol(
                        _typed(item, "app.user_data.QuestData.cSubBossInfo", record.source)["_EmID"]
                    ),
                )
                for item in quest.get("_SubBossInfoArray", [])
            )
        )
        common = {
            "_MissionId": mission_id,
            "_Version": _enum_symbol(quest["_Version"]),
            "_QuestType": _enum_symbol(quest["_QuestType"]),
            "_QuestAttribute": _quest_attribute(text, quest["_QuestAttribute"]),
            "_QuestLv": quest["_QuestLv"],
            "_TitleMsg": title,
            "_MaxPlayerNum": order["_MaxPlayerNum"],
            "_OrderHR": order["_OrderHR"],
            "_OrderMR": order["_OrderMR"],
            "_TimeLimit": quest["_TimeLimit"],
            "_RemMoney": quest["_RemMoney"],
            "_HRPoint": quest["_HRPoint"],
            "_AddPoint": quest["_AddPoint"],
            "_EnableGuestNpc": quest["_EnableGuestNpc"],
            "_Stage": _enum_symbol(quest["_Stage"]),
            "_BattleBGM": _enum_symbol(quest["_BattleBGM"]),
            "_ClearBGM": _enum_symbol(quest["_ClearBGM"]),
            "_DetailMsg": detail,
            "_SubBossInfoArray": "\n".join(sub_bosses),
        }
        first_row = len(rows) + 3  # two header rows
        for clear_index, clear in enumerate(clears):
            target_type = _enum_symbol(clear["_TargetType"])
            targets = (
                [None] if target_type == "ITEM" else clear.get("_TargetInfoArray", []) or [None]
            )
            for target_index, item in enumerate(targets):
                legendary = ""
                monster_name = ""
                if item is not None:
                    target = _typed(
                        item, "app.user_data.QuestData.cClearCondition.cTargetInfo", record.source
                    )
                    legendary = _enum_symbol(target["_LegendaryID"])
                    if target_type.startswith("EM_"):
                        fixed_id = int(target["_TargetIDValue"]) & 0xFFFFFFFF
                        enemy_id = catalog.fixed_enemy_ids.get(fixed_id)
                        if not enemy_id:
                            raise ValueError(f"Unknown fixed enemy ID {fixed_id} in {mission_id}")
                        monster_name = _enemy_name(catalog, text, enemy_id)
                values = {
                    **common,
                    "_TargetType": target_type,
                    "_LegendaryID": legendary,
                    "MonsterName": monster_name,
                }
                if (
                    catalog.difficulty and item is not None
                    and target_type.startswith("EM_") and target_type != "EM_ZAKO_KILL"
                ):
                    values.update(
                        catalog.difficulty.targets[(mission_id, clear_index, target_index)]
                    )
                rows.append({column: values.get(column, "") for column in columns})
        groups.append((first_row, len(rows) + 2))
    for mission_id in catalog.missions_without_quest_data:
        values = dict.fromkeys(columns, "")
        values["_MissionId"] = mission_id
        message_prefix = "Mission" + mission_id.removeprefix("MISSION_")
        for column, suffixes in MISSION_TEXT_SUFFIXES.items():
            values[column] = next(
                (
                    value
                    for suffix in suffixes
                    if (value := text.get_name(f"{message_prefix}_{suffix}"))
                ),
                "",
            )
        rows.append(values)
        excel_row = len(rows) + 2
        groups.append((excel_row, excel_row))
    return MissionWorkbookData(rows, tuple(groups), headers)


def _quest_text(
    record: QuestRecord, text: MissionTextResolver, guid: str, suffix: str, mission_id: str
) -> str:
    if record.stream_text is None:
        value = text.get_guid(guid)
    else:
        ids = record.stream_text["_IDList"]
        matches = [index for index, key in enumerate(ids) if key.endswith(f"_{suffix}")]
        if len(matches) != 1:
            raise ValueError(f"Expected one StreamQuest text ID ending _{suffix}: {record.source}")
        index = matches[0]
        local_field = STREAM_TEXT_FIELDS.get(text.language_id, "_EnglishList")
        local_values = record.stream_text.get(local_field, [])
        english_values = record.stream_text.get("_EnglishList", [])
        local = _content_at(local_values, index)
        english = _content_at(english_values, index)
        value = text.resolve(local or english)
    if not value:
        raise ValueError(f"Missing quest text _{suffix} for {mission_id}: {record.source}")
    return value


def _quest_attribute(text: MissionTextResolver, raw: str) -> str:
    symbol = _enum_symbol(raw)
    names = ATTRIBUTE_TEXT_NAMES.get(symbol, ())
    for name in names:
        localized = text.local_name(name)
        if localized:
            return localized
    for name in names:
        english = text.english_name(name)
        if english:
            return english
    return symbol


def _enemy_name(catalog: MissionCatalog, text: MissionTextResolver, enemy_id: str) -> str:
    guid = catalog.enemy_name_guids.get(enemy_id)
    return text.enemy_name(guid, enemy_id)


def _read_json(path: Path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _typed(data, key: str, source: Path) -> dict:
    if isinstance(data, list):
        if len(data) != 1:
            raise ValueError(f"Expected one {key} record: {source}")
        data = data[0]
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, dict):
        raise ValueError(f"Missing {key}: {source}")
    return value


def _typed_conditions(data, source: Path) -> list[dict]:
    key = "app.user_data.QuestData.cClearCondition"
    if isinstance(data, list):
        if not data:
            raise ValueError(f"No clear conditions in {source}")
        return [_typed(condition, key, source) for condition in data]
    return [_typed(data, key, source)]


def _enum_symbol(value: str) -> str:
    return ENUM_PREFIX.sub("", str(value))


def _quest_sort_key(record: QuestRecord) -> tuple[int, str]:
    mission_id = _enum_symbol(record.data["_MissionId"])
    return _mission_id_sort_key(mission_id)


def _mission_id_sort_key(mission_id: str) -> tuple[int, str]:
    match = MISSION_NUMBER.fullmatch(mission_id)
    return (int(match.group(1)) if match else 2**31, mission_id)
