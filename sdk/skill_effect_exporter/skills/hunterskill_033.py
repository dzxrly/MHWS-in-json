"""HunterSkill_033 夺取耐力: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_033"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillStaminaTakeStaminaRate": {
        "效果": "减气值倍率",
        "作用于": "命中时攻击数据的减气值 _StaminaDamage",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "攻击命中时",
        "单位": "倍",
        "依据": "HunterCharacter.makeActualAttackParam、cHunterSkill.getWp08BinValueFromPreview",
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
