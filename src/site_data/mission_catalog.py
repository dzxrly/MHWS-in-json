"""Quest counter categories and monster cells in the exported 100 px icon atlas."""

import json
from pathlib import Path

from src.database.missions.build import QuestRecord
from src.shared.source.user3 import load_user3_table

# Simplified Chinese titles from RefQuest_0009 and RefQuest_0018_010.
QUEST_CATEGORIES = {
    "MAINSTORY": "关键任务",
    "FREEQUEST": "自由任务",
    "STREAM_EVENTQUEST": "活动任务",
    "TOURNAMENTQUEST": "斗技大会任务",
    "STREAM_CHALLENGEQUEST": "挑战任务",
    "TA_FREEQUEST": "自由挑战任务",
}


def quest_category(record: QuestRecord) -> str:
    stem = record.source.name.removesuffix("_QuestData.user.3.json")
    if record.stream_text is not None:
        source = record.source.with_name(name=f"{stem}_StreamQuestData.user.3.json")
        data_type = "app.user_data.StreamQuestData"
    else:
        directory = record.source.parent
        if directory.name == "_Quest":
            directory = directory.parent
        source = directory / f"{stem}_MsData.user.3.json"
        data_type = "app.user_data.MissionData"
    with source.open(encoding="utf-8") as handle:
        data = json.load(fp=handle)[0][data_type]
    return QUEST_CATEGORIES[data["_MissionTypeSerial"].split()[-1]]


def load_monster_icons(natives_dir: Path) -> dict[str, int]:
    rows = load_user3_table(
        path=natives_dir / "STM/GameDesign/Common/Enemy/EnemyData.user.3.json"
    )
    icons = {}
    for row in rows:
        boss = row["BossIconType"]
        small = row["ZakoIconType"]
        # E0000 (unknown large monster) starts row 8; S0000 starts row 13.
        # The 2048 px atlas packs twenty 100 px cells per row.
        if boss:
            icons[row["enemyId"]] = 160 + int(boss[1:])
        elif small:
            icons[row["enemyId"]] = 260 + int(small[1:])
    return icons
