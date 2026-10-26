"""HunterSkill_006 水属性攻击强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_006"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillWaterAttackRate": {
        "效果": "水属性值倍率",
        "作用于": "武器的水属性值",
        "计算": "乘算（SkillData 槽 0 × 0.01），并入属性值倍率汇总；先乘后加",
        "单位": "倍",
        "依据": "cHunterSkill.calcElemWaterRate",
    },
    "getSkillWaterAttackAdd": {
        "效果": "水属性值加算",
        "作用于": "武器的水属性值",
        "计算": "加算（SkillData 槽 1），并入属性值加算汇总",
        "单位": "点（内部值，游戏内显示为其 10 倍）",
        "依据": "cHunterSkill.calcElemWaterAdd",
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
