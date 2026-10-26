"""HunterSkill_056 会心击【特殊】: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_056"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillAttrCriticalRate": {
        "效果": "会心时异常累积倍率",
        "作用于": "会心攻击时施加的毒、麻痹、睡眠、爆破累积值",
        "计算": "乘算",
        "条件": "会心攻击时（游戏说明）",
        "单位": "倍",
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
