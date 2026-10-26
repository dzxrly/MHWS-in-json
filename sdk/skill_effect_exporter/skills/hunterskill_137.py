"""HunterSkill_137 昆虫标本达人: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_137"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillInsectMasterRate": {
        "效果": "技能开关",
        "作用于": "昆虫型小型怪物被讨伐后留下尸体",
        "计算": "为 1 时生效",
        "条件": "以攻击讨伐昆虫型小型怪物时（游戏说明）",
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
