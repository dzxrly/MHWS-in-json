"""HunterSkill_195 无我之境: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_195"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillMugaGaugeAdd": {
        "效果": "克服值增加倍率加算",
        "作用于": "狂龙病克服值 _OvercomePoint 的增加量",
        "计算": "增加量 × (1 + 本数值)",
        "条件": "感染狂龙病毒时，攻击命中、回避等增加克服值时",
        "单位": "倍（加到 1 上）",
        "依据": "cFrenzy.onAttackHit、cFrenzy.onDodgeAction、cFrenzy.doUpdate、cFrenzy.addOvercomePoint",
    },
    "getSkillMugaCriticalAdd": {
        "效果": "克服状态会心率加算",
        "作用于": "会心率",
        "计算": "加算",
        "条件": "克服状态时（游戏说明）",
        "单位": "%",
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
