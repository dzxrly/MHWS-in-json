"""HunterSkill_168 毛皮之昂扬: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_168"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillFortitudeAttackRate": {
        "效果": "攻击力倍率",
        "作用于": "攻击力",
        "计算": "乘算，并入攻击力倍率汇总",
        "条件": "任务中力尽倒下后（最多 2 次）（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcAttackRate、cHunterSkill.onBaseActionExit（按技能等级）",
    },
    "getSkillFortitudeDefenseRate": {
        "效果": "防御力倍率",
        "作用于": "防御力",
        "计算": "乘算",
        "条件": "任务中力尽倒下后（最多 2 次）（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.onBaseActionExit（按技能等级）",
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
