"""HunterSkill_169 毛皮之诱惑: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_169"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDiversionHateRate": {
        "效果": "仇恨值倍率",
        "作用于": "攻击命中时对怪物的仇恨值",
        "计算": "乘算",
        "条件": "攻击命中时（游戏说明）",
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
