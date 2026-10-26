"""HunterSkill_110 逆袭: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_110"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillCounterAttack_ActiveTime": {
        "效果": "效果持续时间",
        "作用于": "被击飞后攻击力提升的持续时间",
        "计算": "设为该值",
        "条件": "被击飞后（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginCounterAttack（按技能等级）",
    },
    "getSkillCounterAttack_AttackAdd": {
        "效果": "基础攻击力加算",
        "作用于": "基础攻击力",
        "计算": "加算（SkillData 槽 0），并入攻击力加算汇总",
        "条件": "被击飞后的持续时间内（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcAttackAdd",
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
