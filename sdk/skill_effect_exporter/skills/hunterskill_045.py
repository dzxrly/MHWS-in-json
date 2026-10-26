"""HunterSkill_045 速射强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_045"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGunnerAmmo_Rapid_Rate": {
        "效果": "速射攻击力倍率",
        "作用于": "命中时攻击数据的攻击力及毒、麻痹、睡眠累积值",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "轻弩速射命中时",
        "单位": "倍",
        "依据": "cHunterWpGunHandling.doOnHit_AttackPre",
    },
    "getSkillGunnerAmmo_Rapid_LightEnVariableLastShotRate": {
        "效果": "速射最后一发倍率（轻弩）",
        "作用于": "轻弩速射最后一发",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
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
