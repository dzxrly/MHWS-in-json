"""HunterSkill_109 攀岩者: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_109"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillClimberStaminaRate": {
        "效果": "攀爬耐力消耗倍率",
        "作用于": "攀爬藤蔓时的耐力消耗",
        "计算": "乘算",
        "条件": "攀爬藤蔓时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterStatus.updateStamina",
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
