"""HunterSkill_191 属性变换: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_191"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillRyukiAttackAdd": {
        "效果": "龙属性值加算",
        "作用于": "龙属性值",
        "计算": "加算（SkillData 槽 0），并入龙属性加算汇总",
        "条件": "效果发动时（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcElemDragonAdd",
    },
    "getSkillRyukiAccumulationAttackRate": {
        "效果": "追加龙属性伤害倍率",
        "作用于": "累积属性伤害后追加的龙属性伤害",
        "计算": "乘算",
        "条件": "累积属性伤害后（游戏说明）；调用处未追踪到",
        "单位": "倍",
    },
    "damageAttrApply→_RyukiInfo._Timer：_RyukilData": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _RyukiInfo._Timer",
        "计算": "设为该值",
        "条件": "受到属性伤害时写入",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.damageAttrApply",
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
