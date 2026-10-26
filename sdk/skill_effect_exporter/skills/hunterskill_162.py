"""HunterSkill_162 甲虫之直觉: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_162"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHoneyHunter_Add_Min": {
        "效果": "蜂蜜额外取得数下限",
        "作用于": "原野采集蜂蜜时的额外取得数",
        "计算": "随机数的下限",
        "条件": "在原野采集蜂蜜时（游戏说明）",
        "单位": "个",
    },
    "getSkillHoneyHunter_Add_Max": {
        "效果": "蜂蜜额外取得数上限",
        "作用于": "原野采集蜂蜜时的额外取得数",
        "计算": "随机数的上限",
        "条件": "在原野采集蜂蜜时（游戏说明）",
        "单位": "个",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
