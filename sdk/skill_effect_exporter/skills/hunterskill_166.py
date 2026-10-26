"""HunterSkill_166 铺鳞之技法: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_166"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBattleRideMasterRideRate": {
        "效果": "骑乘积蓄倍率",
        "作用于": "骑乘怪物的积蓄",
        "计算": "乘算",
        "条件": "调用处未追踪到（游戏说明）",
        "单位": "倍",
    },
    "getSkillBattleRideMasterRideScarRate": {
        "效果": "骑乘伤口倍率",
        "作用于": "骑乘时与伤口相关的数值",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
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
