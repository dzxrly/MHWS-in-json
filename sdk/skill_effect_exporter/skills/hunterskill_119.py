"""HunterSkill_119 裂伤耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_119"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBleedResistanceDamageRate": {
        "效果": "裂伤伤害倍率",
        "作用于": "裂伤状态造成的伤害",
        "计算": "乘算；Lv3 不会陷入裂伤",
        "条件": "裂伤状态中（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillBleed（按技能等级）",
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
