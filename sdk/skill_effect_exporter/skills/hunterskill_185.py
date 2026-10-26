"""HunterSkill_185 锁刃龙之饥饿: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_185"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillAccHealValue": {
        "效果": "体力回复量",
        "作用于": "体力",
        "计算": "回复该值；按武器取不同数据",
        "条件": "攻击不断命中怪物时（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.evHit_AttackPostProcess（按技能等级）",
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
