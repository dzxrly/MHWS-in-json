"""HunterSkill_236 暗黑骑士之证: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_236"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDarkWaveAttrRate": {
        "效果": "属性值倍率",
        "作用于": "属性值",
        "计算": "乘算",
        "条件": "体力槽有红色部分时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.updateAfter（按技能等级）",
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
