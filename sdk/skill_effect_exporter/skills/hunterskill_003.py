"""HunterSkill_003 会心击【属性】: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_003"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillElementCriticalRate": {
        "效果": "属性会心伤害倍率",
        "作用于": "会心攻击时的属性伤害",
        "计算": "乘算；按武器取不同数据",
        "条件": "会心攻击时（游戏说明）",
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
