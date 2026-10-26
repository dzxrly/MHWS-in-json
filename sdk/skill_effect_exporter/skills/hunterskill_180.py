"""HunterSkill_180 火龙之力: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_180"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillScorchingHeatHitRate": {
        "效果": "追加火属性伤害概率",
        "作用于": "攻击命中时追加火属性伤害的判定",
        "计算": "按百分比概率随机判定（推测）",
        "条件": "攻击命中时（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.calcSkillAdditionalDamage（按技能等级）",
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
