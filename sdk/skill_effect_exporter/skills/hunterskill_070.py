"""HunterSkill_070 回复速度: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_070"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHealSpeedRate": {
        "效果": "回复速度倍率",
        "作用于": "体力回复速度",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
    },
    "getSkillRedHealthSpeedRate": {
        "效果": "红色体力回复速度倍率",
        "作用于": "红色体力的回复速度 _RedRecoverTimeRate",
        "计算": "乘算",
        "条件": "体力槽有红色部分时",
        "单位": "倍",
        "依据": "cHunterStatus.updateHealth",
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
