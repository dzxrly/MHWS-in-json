"""HunterSkill_207 花舞祈祷: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_207"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillSpringEvent_AttackRate": {
        "效果": "攻击力倍率",
        "作用于": "攻击力",
        "计算": "乘算（SkillData 槽 0 × 0.01），并入攻击力倍率汇总",
        "条件": "Lv4，活动之仪期间（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcAttackRate",
    },
    "getSkillSpringEvent_DefenseAdd": {
        "效果": "防御力加算",
        "作用于": "防御力",
        "计算": "加算（SkillData 槽 1），并入防御力加算汇总",
        "条件": "Lv4，活动之仪期间（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcDefenseAdd",
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
