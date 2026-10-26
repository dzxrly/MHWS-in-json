"""HunterSkill_235 协作程序: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_235"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillCooperationValue_ToNpc": {
        "效果": "效果数值（随从与支援猎人）",
        "作用于": "“协作程序”对随从与支援猎人的效果",
        "计算": "未追踪到调用处",
        "单位": "",
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
