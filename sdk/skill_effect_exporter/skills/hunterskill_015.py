"""HunterSkill_015 利刃: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_015"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillWazamonoPercent": {
        "效果": "不消耗锋利度概率",
        "作用于": "锋利度消耗",
        "计算": "以本数值为百分比概率随机判定，成立时本次不消耗",
        "条件": "攻击消耗锋利度时",
        "单位": "%",
        "依据": "cHunterSkill.checkSkillReduceKireaji",
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
