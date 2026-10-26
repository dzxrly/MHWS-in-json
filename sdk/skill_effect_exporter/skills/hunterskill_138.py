"""HunterSkill_138 整备: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_138"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillMaintenanceRate": {
        "效果": "冷却时间倍率",
        "作用于": "装衣等主动技能的冷却时间",
        "计算": "冷却速度设为 1 ÷ 本倍率（SkillData 槽 0 × 0.01）",
        "条件": "冷却中",
        "单位": "倍",
        "依据": "cHunterSkill.getActiveSkillCoolTimeRate、mcActiveSkillController.calcCoolDownRate",
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
