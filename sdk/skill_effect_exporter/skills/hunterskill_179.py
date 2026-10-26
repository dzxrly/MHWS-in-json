"""HunterSkill_179 冻峰龙之反叛: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_179"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillRebellionDurationTime": {
        "效果": "效果持续时间",
        "作用于": "攻击力提升的持续时间",
        "计算": "设为该值",
        "条件": "从束缚或冻结中回复、从束缚攻击解放、角力后（游戏说明）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillRebellionBuffAttackAdd": {
        "效果": "攻击力加算",
        "作用于": "攻击力",
        "计算": "加算",
        "条件": "效果持续时间内（游戏说明）",
        "单位": "点",
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
