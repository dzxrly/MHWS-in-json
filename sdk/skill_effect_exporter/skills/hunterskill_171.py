"""HunterSkill_171 霸主之愤慨: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_171"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillKatsuAttackAdd": {
        "效果": "攻击力加算",
        "作用于": "攻击力",
        "计算": "加算",
        "条件": "陷入状态异常时（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.updateAfter（按技能等级）",
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
