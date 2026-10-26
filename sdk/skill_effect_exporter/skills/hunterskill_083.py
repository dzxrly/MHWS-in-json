"""HunterSkill_083 毒耐性: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_083"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillPoisonResistanceDamageIntervalTimeRate": {
        "效果": "中毒伤害间隔倍率",
        "作用于": "中毒时受到伤害的间隔时间",
        "计算": "乘算（间隔变长，受伤次数减少）；Lv3 不会中毒",
        "条件": "中毒时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillPoison（按技能等级）",
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
