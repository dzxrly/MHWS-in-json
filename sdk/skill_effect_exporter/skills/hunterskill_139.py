"""HunterSkill_139 威吓: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_139"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillLowerIntimidationRate": {
        "效果": "察觉值倍率（Lower）",
        "作用于": "怪物对猎人的察觉值变化",
        "计算": "乘算（0 即不再增加，推测）",
        "条件": "怪物察觉猎人时；Lower 与 Upper 分别对应哪类怪物或情形未核实",
        "单位": "倍",
        "依据": "mcUpdater.updateFeelValue_Pl（按技能等级）",
    },
    "getSkillUpperIntimidationRate": {
        "效果": "察觉值倍率（Upper）",
        "作用于": "怪物对猎人的察觉值变化",
        "计算": "乘算（0 即不再增加，推测）",
        "条件": "怪物察觉猎人时；Lower 与 Upper 分别对应哪类怪物或情形未核实",
        "单位": "倍",
        "依据": "mcUpdater.updateFeelValue_Pl（按技能等级）",
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
