"""HunterSkill_165 皮革制品之顺滑: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_165"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillSlidingPowerUpBeginTime": {
        "效果": "滑行判定时间",
        "作用于": "滑行后发动所需的时间",
        "计算": "设为该值",
        "条件": "利用地形滑行时；用法未追踪到",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.update（按技能等级）",
    },
    "getSkillSlidingPowerUpActiveTime": {
        "效果": "效果持续时间",
        "作用于": "滑行后会心率提升的持续时间",
        "计算": "设为该值",
        "条件": "利用地形滑行后（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.update（按技能等级）",
    },
    "getSkillSlidingPowerUpCriticalAdd": {
        "效果": "会心率加算",
        "作用于": "会心率",
        "计算": "加算",
        "条件": "利用地形滑行后的一定时间内（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.update（按技能等级）",
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
