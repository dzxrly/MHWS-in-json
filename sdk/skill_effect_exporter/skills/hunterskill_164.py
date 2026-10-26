"""HunterSkill_164 皮革制品之柔韧: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_164"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillCollectionMasterMotSpeedRate": {
        "效果": "采集动作速度倍率",
        "作用于": "采集、采掘动作的动作速度",
        "计算": "乘算",
        "条件": "采集、采掘时",
        "单位": "倍",
        "依据": "cMining.doEnter、cGasagoso.doEnter、cPorterRideMining.doEnter",
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
