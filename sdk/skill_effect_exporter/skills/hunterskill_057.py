"""HunterSkill_057 蓄击强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_057"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHyperCharge_StunRate": {
        "效果": "蓄力攻击眩晕值倍率",
        "作用于": "命中时攻击数据的眩晕值 _StunDamage",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "大锤蓄力攻击命中时",
        "单位": "倍",
        "依据": "cHunterWp04Handling.doOnHit_AttackPre",
    },
    "getSkillHyperCharge_Attackate": {
        "效果": "蓄力攻击攻击力倍率",
        "作用于": "命中时攻击数据的攻击力 _Attack",
        "计算": "乘算（SkillData 槽 1 × 0.01）",
        "条件": "大锤蓄力攻击命中时",
        "单位": "倍",
        "依据": "cHunterWp04Handling.doOnHit_AttackPre",
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
