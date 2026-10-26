"""HunterSkill_105 饥饿耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_105"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHungerResistanceTimeRate": {
        "效果": "耐力上限减少间隔倍率",
        "作用于": "耐力上限随时间减少的间隔",
        "计算": "乘算；Lv3 不再减少",
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
