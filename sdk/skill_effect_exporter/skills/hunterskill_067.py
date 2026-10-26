"""HunterSkill_067 防御: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_067"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDefenseRate": {
        "效果": "防御力倍率",
        "作用于": "防御力",
        "计算": "乘算（SkillData 槽 0 × 0.01），并入防御力倍率汇总；先乘后加",
        "条件": "Lv3 起不为 1",
        "单位": "倍",
        "依据": "cHunterSkill.calcDefenseRate",
    },
    "getSkillDefenseAdd": {
        "效果": "防御力加算",
        "作用于": "防御力",
        "计算": "加算（SkillData 槽 1），并入防御力加算汇总",
        "单位": "点",
        "依据": "cHunterSkill.calcDefenseAdd",
    },
    "getSkillDefenseAttrAdd": {
        "效果": "全属性耐性加算",
        "作用于": "火、水、雷、冰、龙耐性",
        "计算": "加算（SkillData 槽 2），并入属性耐性加算汇总",
        "条件": "Lv4 起不为 0",
        "单位": "点",
        "依据": "cHunterSkill.calcAttrDefenseAdd",
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
