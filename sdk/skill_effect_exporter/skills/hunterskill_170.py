"""HunterSkill_170 霸主之骄傲: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_170"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillYell_AttackPowerAdd": {
        "效果": "攻击力加算",
        "作用于": "范围内同伴的攻击力",
        "计算": "加算",
        "条件": "发动对范围内同伴生效的效果（如旋律）后（游戏说明）",
        "单位": "点",
    },
    "getSkillYell_ActiveTime": {
        "效果": "效果持续时间",
        "作用于": "攻击力提升的持续时间",
        "计算": "设为该值",
        "条件": "发动对范围内同伴生效的效果后（游戏说明）",
        "单位": "时间（游戏内部单位）",
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
