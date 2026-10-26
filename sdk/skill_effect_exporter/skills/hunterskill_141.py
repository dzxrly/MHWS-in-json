"""HunterSkill_141 毒伤害强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_141"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillPoisonDamagePowerRate": {
        "效果": "中毒时间倍率",
        "作用于": "怪物中毒状态的持续时间",
        "计算": "乘算",
        "条件": "使怪物中毒时（游戏说明）",
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
