"""HunterSkill_032 击晕术: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_032"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillKOStunRate": {
        "效果": "眩晕值倍率",
        "作用于": "命中时攻击数据的眩晕值 _StunDamage",
        "计算": "乘算（SkillData 槽 0 × 0.01），有上限",
        "条件": "攻击命中时",
        "单位": "倍",
        "依据": "HunterCharacter.makeActualAttackParam",
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
