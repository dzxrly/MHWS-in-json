"""HunterSkill_037 特殊射击强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_037"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGunnerAmmo_Special": {
        "效果": "特殊射击攻击力倍率",
        "作用于": "命中时攻击数据的攻击力 _Attack",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "弩炮特殊弹药、弓的龙之箭等命中时",
        "单位": "倍",
        "依据": "cHunterWpGunHandling.doOnHit_AttackPre、cHunterWp11Handling.doOnHit_AttackPre",
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
