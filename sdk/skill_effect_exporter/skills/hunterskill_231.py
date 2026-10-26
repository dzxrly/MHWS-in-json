"""HunterSkill_231 炎之大厨: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_231"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "beginMeatGrillMaster→_MeatGrillMasterInfo._Timer：_MeatGrillMasterData": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _MeatGrillMasterInfo._Timer",
        "计算": "设为该值，按烤肉熟度取不同数据",
        "条件": "烤肉完成时",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginMeatGrillMaster",
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
