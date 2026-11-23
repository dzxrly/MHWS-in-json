"""Game quest list, with one entry per assignment and one row per target instance."""

from collections import defaultdict
import json
from pathlib import Path
import re

from config import ZH_HANS_LANGUAGE_ID
from src.database.missions.build import (
    _enemy_name,
    _enum_symbol,
    _quest_text,
    _typed_conditions,
    load_mission_catalog,
)
from src.database.missions.text import MissionTextResolver
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource

from .mission_catalog import QUEST_CATEGORIES, load_monster_icons, quest_category
from .mission_rates import load_combat_profile, load_speed_bounds, target_combat
from .mission_speed_variation import load_motion_sizes, motion_phases, target_sizes

OUTPUT_NAME = "missions/quests.json"
REWARDS_DIR = "STM/GameDesign/Mission/_UserData/_Reward"
ITEM_TABLE = "STM/GameDesign/Common/Item/itemData.user.3.json"
STAGE_TEXT = {
    "ST101": "RefEnvironment_0000_0000",
    "ST102": "RefEnvironment_0000_0001",
    "ST103": "RefEnvironment_0000_0002",
    "ST104": "RefEnvironment_0000_0003",
    "ST105": "RefEnvironment_0000_0004",
    "ST401": "RefEnvironment_0000_0005",
    "ST402": "RefEnvironment_0001_0004",
    "ST403": "RefEnvironment_0001_0003",
    "ST405": "RefEnvironment_0001_0005",
}
QUEST_TYPES = {
    "HUNTING": "狩猎",
    "KILL": "讨伐",
    "CAPTURE": "捕获",
    "BOSSRUSH": "连续狩猎",
    "TRANSPORT": "交货",
    "SPECIAL": "特殊",
    "ARENA": "斗技",
}
OBJECTIVES = {
    "EM_BOSS_HUNTING": "狩猎",
    "EM_BOSS_KILL": "讨伐",
    "EM_BOSS_CAPTURE": "捕获",
    "EM_ZAKO_KILL": "讨伐",
    "ITEM": "交货",
}
MESSAGE_TAG = re.compile(r"</?STYLE(?: [^>]+)?>|<REF [^>]+>")


def _reward_pools(repository: SourceRepository, item_names: dict) -> dict:
    tables = {}
    for name in ("CommonRewardData", "AddRewardData"):
        groups = defaultdict(list)
        for row in repository.table(relative_path=f"{REWARDS_DIR}/{name}.user.3.json"):
            if row["itemId"] != "NONE" and row["num"] > 0:
                groups[row["tableId"]].append(
                    {
                        "name": item_names[row["itemId"]],
                        "quantity": row["num"],
                        "probability": row["probability"],
                    }
                )
        tables[name] = dict(groups)

    result = {}
    for row in repository.table(
        relative_path=f"{REWARDS_DIR}/QuestRewardSetting.user.3.json"
    ):
        rewards = []
        for field, table, group in (
            ("commonRewardTableId", "CommonRewardData", "基础报酬"),
            ("targetAddRewardTableId", "AddRewardData", "目标追加报酬"),
            ("questAddRewardTableId", "AddRewardData", "任务追加报酬"),
        ):
            if row[field]:
                rewards.extend(
                    {**item, "group": group} for item in tables[table][row[field]]
                )
        result[row["missionID"]] = rewards
    return result


def _story_rewards(repository: SourceRepository, item_names: dict) -> dict:
    rewards = defaultdict(list)
    for row in repository.table(
        relative_path=f"{REWARDS_DIR}/MissionRewardData.user.3.json"
    ):
        items = [
            {"name": item_names[item], "quantity": count}
            for item, count in zip(row["ItemId"], row["ItemNum"], strict=True)
            if count > 0
        ]
        rewards[row["MissonId"]].append(
            {
                "rank": row["MissionRank"].removeprefix("RANK_"),
                "items": items,
                "money": row["Money"],
                "points": row["SurveyPoint"],
                "hrPoints": row["HunterRankPoint"],
            }
        )
    return rewards


def _common_reward_slots(repository: SourceRepository) -> list[dict]:
    path = repository.root / REWARDS_DIR / "QuestRewardVariousData.user.3.json"
    settings = json.loads(s=path.read_text(encoding="utf-8"))[0][
        "app.user_data.QuestRewardVariousData"
    ]
    return [
        {
            "count": settings["_QuestCommonRewardConfirmNum"] + row["addLotNum"],
            "probability": row["probability"],
        }
        for row in repository.table(
            relative_path=f"{REWARDS_DIR}/RewardLotProbabilityTable.user.3.json"
        )
        if row["tableId"] == settings["_QuestCommonRewardLotProbabilityTableId"]
    ]


def _spawn_text(entry: dict, names: list[str]) -> str:
    condition = entry["_PopType"].split()[-1]
    value, extra = entry["_ConditionValue_1"], entry["_ConditionValue_2"]
    if condition == "BEGINNING":
        return "开场"
    if condition == "REMAIN_HP":
        return f"第 {value + 1} 个目标（{names[value]}）剩余体力降至 {extra}%"
    if condition == "HUNT_NUM":
        return f"累计狩猎 {value} 只后"
    if condition in {"HUNT_NUM_OR_TIME", "HUNT_NUM_AND_TIME"}:
        join = "或" if condition == "HUNT_NUM_OR_TIME" else "且"
        return f"累计狩猎 {value} 只{join}达到计时条件（{extra}）"
    raise ValueError(f"Unknown quest spawn condition {condition}")


def build_site_data(repository: SourceRepository, text_source: TextSource) -> dict:
    natives = repository.root
    enums_path = natives.parent / "Enums_Internal.json"
    catalog = load_mission_catalog(
        natives_dir=natives,
        enums_path=enums_path,
        repository=repository,
    )
    text = MissionTextResolver(
        source=text_source,
        language_id=ZH_HANS_LANGUAGE_ID,
    )
    item_names = {
        row["ItemId"]: text.get_guid(guid=row["RawName"])
        for row in repository.table(relative_path=ITEM_TABLE)
    }
    fixed_items = {
        fixed_id: item_id
        for item_id, fixed_id in json.loads(s=enums_path.read_text(encoding="utf-8"))[
            "app.ItemDef.ID_Fixed"
        ].items()
    }
    reward_pools = _reward_pools(
        repository=repository,
        item_names=item_names,
    )
    reward_slots = _common_reward_slots(repository=repository)
    story_rewards = _story_rewards(
        repository=repository,
        item_names=item_names,
    )
    icons = load_monster_icons(natives_dir=natives)
    speed_bounds = load_speed_bounds(natives=natives)
    size_tables = load_motion_sizes(natives=natives)
    profiles = {}
    quests = []
    for record in catalog.quests:
        q = record.data
        mission_id = _enum_symbol(value=q["_MissionId"])
        order = q["_OrderCondition"]["app.user_data.QuestData.cOrderCondition"]
        msg = q["_QuestMsg"]["app.user_data.QuestData.cQuestMsg"]
        messages = {}
        for key, field, suffix in (
            ("name", "_TitleMsg", "100"),
            ("client", "_ClientNameMsg", "101"),
            ("description", "_DetailMsg", "102"),
        ):
            messages[key] = MESSAGE_TAG.sub(
                repl="",
                string=_quest_text(
                    record=record,
                    text=text,
                    guid=msg[field],
                    suffix=suffix,
                    mission_id=mission_id,
                ),
            )
        targets = []
        for i, clear in enumerate(
            _typed_conditions(
                data=q["_ClearCondition"],
                source=record.source,
            )
        ):
            kind = _enum_symbol(value=clear["_TargetType"])
            for j, wrapped in enumerate(clear["_TargetInfoArray"]):
                target = wrapped["app.user_data.QuestData.cClearCondition.cTargetInfo"]
                fixed_id = target["_TargetIDValue"] & 0xFFFFFFFF
                enemy = None
                if kind == "ITEM":
                    name = item_names[fixed_items[fixed_id]]
                else:
                    enemy = catalog.fixed_enemy_ids[fixed_id]
                    name = _enemy_name(
                        catalog=catalog,
                        text=text,
                        enemy_id=enemy,
                    )
                value = target["_TargetValue"]
                is_hp = kind == "EM_BOSS_REMAIN_HP"
                state = _enum_symbol(value=target["_LegendaryID"])
                data = {
                    "id": enemy,
                    "name": name,
                    "icon": icons.get(enemy),
                    "state": state,
                    "count": 1 if is_hp else value,
                    "objective": (
                        f"将剩余体力削减至 {value}%" if is_hp else OBJECTIVES[kind]
                    ),
                    "spawn": "",
                    "combat": None,
                }
                row = catalog.difficulty.targets.get((mission_id, i, j))
                if row is not None:
                    role = _enum_symbol(value=target["_RoleID"])
                    profile_key = (enemy, role)
                    if profile_key not in profiles:
                        profiles[profile_key] = load_combat_profile(
                            natives=natives,
                            enemy=enemy,
                            role=role,
                        )
                    upper = q["_QuestLv"] >= 4
                    combat = target_combat(
                        row=row,
                        profile=profiles[profile_key],
                        enemy=enemy,
                        state=state,
                        upper=upper,
                        max_players=order["_MaxPlayerNum"],
                        speed_bounds=speed_bounds,
                    )
                    combat["phases"] = motion_phases(
                        natives=natives, enemy=enemy, upper=upper
                    )
                    combat["sizes"] = target_sizes(row=row, size_tables=size_tables)
                    data["combat"] = combat
                targets.append(data)
        waves = q["_BossRushParams"]
        if waves:
            names = [target["name"] for target in targets]
            for target, wave in zip(targets, waves, strict=True):
                target["spawn"] = _spawn_text(
                    entry=wave["app.user_data.QuestData.cBossRushParam"],
                    names=names,
                )
        quest_type = _enum_symbol(value=q["_QuestType"])
        stage = _enum_symbol(value=q["_Stage"])
        quests.append(
            {
                "id": mission_id,
                **messages,
                "category": quest_category(record=record),
                "type": QUEST_TYPES[quest_type],
                "rank": "上位" if q["_QuestLv"] >= 4 else "下位",
                "stars": q["_QuestLv"],
                "hr": order["_OrderHR"],
                "maxPlayers": order["_MaxPlayerNum"],
                "timeLimit": q["_TimeLimit"],
                "faints": q["_QuestLife"],
                "money": q["_RemMoney"],
                "points": q["_AddPoint"],
                "hrPoints": q["_HRPoint"],
                "stage": text.get_name(name=STAGE_TEXT[stage]),
                "prerequisite": _enum_symbol(value=order["_PremiseMission"]),
                "targets": targets,
                "rewards": reward_pools[mission_id],
                "rewardSlots": reward_slots,
                "rankRewards": story_rewards.get(mission_id, []),
            }
        )
    by_id = {mission["id"]: mission["name"] for mission in quests}
    for quest in quests:
        key = quest["prerequisite"]
        quest["prerequisite"] = ""
        if key.startswith("MISSION_"):
            quest["prerequisite"] = by_id.get(key) or next(
                (
                    label
                    for suffix in ("100", "000")
                    if (label := text.get_name(name=f"Mission{key[8:]}_{suffix}"))
                ),
                key,
            )
    listed_categories = {quest["category"] for quest in quests}
    categories = [
        name for name in QUEST_CATEGORIES.values() if name in listed_categories
    ]
    counter_order = {
        row["MissionId"]: row["Index"]
        for table in ("MainStorySortData", "FreeQuestSortData")
        for row in repository.table(
            relative_path=f"STM/GameDesign/Mission/_UserData/{table}.user.3.json"
        )
    }
    # Categories without a counter sort table retain the catalog's mission ID order.
    quests.sort(
        key=lambda quest: (
            categories.index(quest["category"]),
            counter_order.get(quest["id"], float("inf")),
        )
    )
    return {
        "categories": categories,
        "quests": quests,
    }


def export_mission_data(
    output_dir: Path, repository: SourceRepository, text_source: TextSource
) -> Path:
    path = output_dir / OUTPUT_NAME
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    data = build_site_data(
        repository=repository,
        text_source=text_source,
    )
    path.write_text(
        data=json.dumps(
            obj=data,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return path
