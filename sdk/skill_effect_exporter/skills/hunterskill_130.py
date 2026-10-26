"""HunterSkill_130 指示随从: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_130"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillOtomoPowerUpAttackRate": {
        "效果": "随从攻击力倍率",
        "作用于": "随从的攻击力",
        "计算": "乘算",
        "单位": "倍",
    },
    "getSkillOtomoPowerUpDefensekRate": {
        "效果": "随从防御力倍率",
        "作用于": "随从的防御力",
        "计算": "乘算",
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
