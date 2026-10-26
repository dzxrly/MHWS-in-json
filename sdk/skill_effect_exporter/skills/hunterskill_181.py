"""HunterSkill_181 铠龙之守护: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_181"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHeavyArmorBlessRate": {
        "效果": "所受伤害倍率",
        "作用于": "所受伤害",
        "计算": "乘算",
        "条件": "体力全满时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.updateBuffEffect（按技能等级）",
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
