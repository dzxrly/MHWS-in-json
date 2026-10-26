"""HunterSkill_183 黑蚀龙之力: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_183"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillKyoryuInfectAttackAdd": {
        "效果": "感染时攻击力加算",
        "作用于": "攻击力",
        "计算": "加算",
        "条件": "Lv4，感染狂龙病毒时（游戏说明）",
        "单位": "点",
    },
    "getSkillKyoryuOverComeAttackAdd": {
        "效果": "克服后攻击力加算",
        "作用于": "攻击力",
        "计算": "加算",
        "条件": "Lv4，克服狂龙症后（游戏说明）",
        "单位": "点",
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
