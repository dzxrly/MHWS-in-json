"""HunterSkill_189 束缚耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_189"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillRestraintResistanceRate": {
        "效果": "束缚、冻结持续时间倍率",
        "作用于": "丝线束缚（基础 7）与冻结（基础 8）的持续时间",
        "计算": "乘算；为 0 时不会陷入",
        "条件": "陷入丝线束缚或冻结时",
        "单位": "倍",
        "依据": "cSticky.onDamageActionBegin、cFrozen.onDamageActionBegin",
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
