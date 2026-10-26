"""HunterSkill_136 闪光强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_136"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillStunFlashRate": {
        "效果": "闪光效果倍率",
        "作用于": "怪物受闪光影响的相关数值（具体字段未命名）",
        "计算": "设为该值（不为 1 时生效）",
        "条件": "怪物受到猎人主动引发的闪光时",
        "单位": "倍",
        "依据": "cDamage.doEnter",
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
