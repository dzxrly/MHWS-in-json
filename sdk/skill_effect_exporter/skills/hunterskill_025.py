"""HunterSkill_025 体术: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_025"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillMartialArtStaminaRate": {
        "效果": "固定耐力消耗倍率",
        "作用于": "回避等一次性消耗耐力的行动的耐力消耗",
        "计算": "乘算",
        "条件": "固定消耗耐力的行动（游戏说明）",
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
