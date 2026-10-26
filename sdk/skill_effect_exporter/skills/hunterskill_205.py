"""HunterSkill_205 霸主之魂: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_205"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillSuperGuts_NoUsedAttackRate": {
        "效果": "触发前攻击力倍率",
        "作用于": "攻击力",
        "计算": "乘算",
        "条件": "减轻致命伤害的效果尚未触发时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.update（按技能等级）",
    },
    "getSkillSuperGuts_NoUsedDefenseRate": {
        "效果": "触发前防御力倍率",
        "作用于": "防御力",
        "计算": "乘算（低于 1，降低防御力）",
        "条件": "减轻致命伤害的效果尚未触发时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.update（按技能等级）",
    },
    "getSkillSuperGuts_UsedDefenseRate": {
        "效果": "触发后防御力倍率",
        "作用于": "防御力",
        "计算": "乘算",
        "条件": "减轻致命伤害的效果触发后（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.update（按技能等级）",
    },
    "getSkillSuperGuts_UsedAttrAdd": {
        "效果": "触发后属性耐性加算",
        "作用于": "属性耐性",
        "计算": "加算",
        "条件": "减轻致命伤害的效果触发后（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.update（按技能等级）",
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
