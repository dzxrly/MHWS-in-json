"""HunterSkill_215 千刃龙的斗志: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_215"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBladeSharp_AttackRate": {
        "效果": "攻击力倍率",
        "作用于": "攻击力",
        "计算": "乘算",
        "条件": "Lv4，“巧击”发动期间再次满足条件时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.beginTechnicalAttack（按技能等级）",
    },
    "getSkillBladeSharp_DodgeTimeAdd": {
        "效果": "巧击效果时间加算",
        "作用于": "“巧击”的效果时间",
        "计算": "加算",
        "条件": "“巧击”发动期间再次满足条件时（仅限一次）（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginTechnicalAttack（按技能等级）",
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
