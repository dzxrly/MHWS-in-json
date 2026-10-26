"""HunterSkill_097 道具使用强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_097"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillItemUsePowerUpTimeRate": {
        "效果": "道具效果时间倍率",
        "作用于": "部分道具的效果时间",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "使用对应道具时",
        "单位": "倍",
        "依据": "mcHunterItem.notUseItem",
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
