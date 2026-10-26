"""HunterSkill_186 凶爪龙之力: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_186"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillContinuousAttackReinforceTimeAdd": {
        "效果": "连击持续时间加算",
        "作用于": "“连击”效果的有效时间",
        "计算": "加算",
        "条件": "“连击”效果发动时（游戏说明）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillContinuousAttackReinforceAttackAdd": {
        "效果": "基础攻击力加算",
        "作用于": "基础攻击力",
        "计算": "加算",
        "条件": "“连击”效果发动时（游戏说明）",
        "单位": "点",
    },
    "beginContinuousAttack→_ContinuousAttackInfo._IntervalTime：_ContinuousAttackIntervalTimer": {
        "效果": "连击间隔计时初值",
        "作用于": "技能状态 _ContinuousAttackInfo._IntervalTime",
        "计算": "设为该值",
        "条件": "“连击”开始时",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginContinuousAttack",
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
