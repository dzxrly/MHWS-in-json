"""HunterSkill_077 火耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_077"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillFireResistanceAttrAdd": {
        "效果": "火耐性加算",
        "作用于": "火耐性",
        "计算": "加算",
        "单位": "点",
    },
    "getSkillFireResistanceDefenseAdd": {
        "效果": "防御力加算",
        "作用于": "防御力",
        "计算": "加算（SkillData 槽 1），并入防御力加算汇总",
        "条件": "Lv3 起不为 0",
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
