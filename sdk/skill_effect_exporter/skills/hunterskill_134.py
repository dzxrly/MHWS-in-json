"""HunterSkill_134 环境利用知识: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_134"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillEnvironmentHeal_HealValue": {
        "效果": "体力回复量",
        "作用于": "体力",
        "计算": "回复该值",
        "条件": "使用可任意发动效果的环境物时（游戏说明）",
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
