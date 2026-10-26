"""HunterSkill_065 耐力急速回复: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_065"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillStaminaHighSpeedRate": {
        "效果": "耐力回复速度倍率",
        "作用于": "耐力回复速度",
        "计算": "乘算",
        "单位": "倍",
    }
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
