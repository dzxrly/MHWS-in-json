"""HunterSkill_017 刚刃打磨: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_017"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillToishiBoostDurationTime": {
        "效果": "不消耗锋利度持续时间",
        "作用于": "打磨后不消耗锋利度的时间",
        "计算": "设为该值",
        "条件": "打磨武器后",
        "单位": "秒（游戏说明）",
        "依据": "cHunterSkill.beginSkillToishiBoost",
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
