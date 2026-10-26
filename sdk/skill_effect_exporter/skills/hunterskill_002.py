"""HunterSkill_002 超会心: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_002"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillSuperCriticalAttackRate": {
        "效果": "会心伤害倍率",
        "作用于": "会心攻击时的伤害倍率",
        "计算": "替换（SkillData 槽 0 × 0.01，不低于基础的 1.25）",
        "条件": "会心攻击时",
        "单位": "倍",
        "依据": "cHunterCritical.getCriticalAttackRate",
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
