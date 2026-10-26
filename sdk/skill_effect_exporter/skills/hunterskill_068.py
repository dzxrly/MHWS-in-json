"""HunterSkill_068 精灵加护: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_068"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBlessActiveRate": {
        "效果": "加护发动概率",
        "作用于": "受到伤害时的减伤判定",
        "计算": "以本数值为百分比概率随机判定",
        "条件": "受到伤害时",
        "单位": "%",
        "依据": "cHunterStatus.calcRandomDamageRate",
    },
    "getSkillBlessDamageRate": {
        "效果": "加护伤害倍率",
        "作用于": "所受伤害",
        "计算": "乘算（SkillData 槽 1）",
        "条件": "加护发动时",
        "单位": "倍",
        "依据": "cHunterStatus.calcRandomDamageRate",
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
