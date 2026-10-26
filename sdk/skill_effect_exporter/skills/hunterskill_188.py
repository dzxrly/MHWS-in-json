"""HunterSkill_188 暗器蛸之力: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_188"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBarbarianDurationTime": {
        "效果": "效果持续时间",
        "作用于": "攻击力提升的持续时间",
        "计算": "设为该值",
        "条件": "食用烤熟的肉等道具后（游戏说明）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillBarbarianAttackAdd": {
        "效果": "基础攻击力加算",
        "作用于": "基础攻击力",
        "计算": "加算",
        "条件": "食用烤熟的肉等道具后的一定时间内（游戏说明）",
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
