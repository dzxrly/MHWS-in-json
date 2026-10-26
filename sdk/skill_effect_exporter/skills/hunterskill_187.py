"""HunterSkill_187 雷颚龙之斗志: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_187"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillToughStaminaAdd": {
        "效果": "额外耐力槽",
        "作用于": "额外耐力槽的长度",
        "计算": "加算",
        "单位": "点",
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
