"""HunterSkill_001 看破: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_001"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillCriticalAdd": {
        "效果": "会心率加算",
        "作用于": "会心率",
        "计算": "加算（SkillData 槽 0），并入会心率汇总",
        "单位": "%",
        "依据": "cHunterSkill.getCalcCriticalAdd",
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
