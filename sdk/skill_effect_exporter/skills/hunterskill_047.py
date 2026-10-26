"""HunterSkill_047 高速变形: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_047"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillWpTransformSpeedUpMotionSpeedRate": {
        "效果": "变形动作速度倍率",
        "作用于": "斩斧、盾斧变形动作的动作速度",
        "计算": "设为该值（SkillData 槽 0 × 0.01）",
        "条件": "变形动作中",
        "单位": "倍",
        "依据": "cAxeToSwordDoubleSlash.doUpdate、cSwordToAxeStepUpToSlash.doUpdate",
    },
    "getSkillWpTransformSpeedUpAttackRate": {
        "效果": "变形攻击攻击力倍率",
        "作用于": "命中时的攻击力",
        "计算": "乘算（SkillData 槽 1 × 0.01），并入命中攻击力倍率",
        "条件": "变形攻击命中时",
        "单位": "倍",
        "依据": "cHunterSkill.calcHitAttackRate",
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
