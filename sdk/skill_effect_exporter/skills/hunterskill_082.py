"""HunterSkill_082 属性异常耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_082"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillAttrResistanceMaxTimeRate": {
        "效果": "属性异常持续时间倍率",
        "作用于": "火、水、雷、冰、龙属性异常的持续时间 _DurationTimer",
        "计算": "乘算；为 0 时不会陷入",
        "条件": "陷入属性异常时",
        "单位": "倍",
        "依据": "cHunterElementConditionBase.onActivate",
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
