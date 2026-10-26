"""HunterSkill_176 煌雷龙之力: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_176"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillElecStorageTimeAdd": {
        "效果": "力量解放持续时间加算",
        "作用于": "“力量解放”的持续时间",
        "计算": "加算",
        "条件": "调用处未追踪到",
        "单位": "时间（游戏内部单位）",
    },
    "beginSkillPowerAwake→_PowerAwakeInfo._Timer：_PowerAwakeData": {
        "效果": "力量解放持续时间",
        "作用于": "技能状态 _PowerAwakeInfo._Timer",
        "计算": "设为该值",
        "条件": "“力量解放”发动时",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginSkillPowerAwake",
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
