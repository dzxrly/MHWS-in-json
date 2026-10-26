"""HunterSkill_087 爆破异常耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_087"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBlastResistanceActiveTimeAdd": {
        "效果": "爆破延迟时间加算",
        "作用于": "爆破异常到爆炸前的时间（基础 25）",
        "计算": "加算",
        "条件": "陷入爆破异常时",
        "单位": "时间（游戏内部单位）",
        "依据": "cBlast.onActivate",
    },
    "getSkillBlastResistanceDamageRate": {
        "效果": "爆破伤害倍率",
        "作用于": "爆破时受到的伤害",
        "计算": "乘算；Lv3 不会陷入爆破异常",
        "条件": "爆破时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillBlast（按技能等级）",
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
