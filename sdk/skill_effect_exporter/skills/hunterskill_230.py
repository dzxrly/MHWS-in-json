"""HunterSkill_230 烧烤玉米炮: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_230"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillRoastCorn_AttackRate": {
        "效果": "炮击攻击力倍率",
        "作用于": "铳枪炮击的攻击力",
        "计算": "乘算，并入命中攻击力倍率",
        "条件": "龙击槽红光闪烁时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcHitAttackRate（按技能等级）",
    },
    "getSkillRoastCorn_FireAdd": {
        "效果": "炮击火属性值加算",
        "作用于": "铳枪炮击的火属性值",
        "计算": "加算",
        "条件": "龙击槽红光闪烁时（游戏说明）",
        "单位": "点（内部值，推测游戏内显示为其 10 倍）",
        "依据": "cHunterSkill.calcHitAttackRate（按技能等级）",
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
