"""HunterSkill_120 防御力下降耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_120"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDefenseDownResistanceMaxTimeRate": {
        "效果": "防御力下降持续时间倍率",
        "作用于": "防御力下降状态的持续时间（基础 45）",
        "计算": "乘算；为 0 时不会陷入",
        "条件": "陷入防御力下降时",
        "单位": "倍",
        "依据": "cDefenceDown.onActivate",
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
