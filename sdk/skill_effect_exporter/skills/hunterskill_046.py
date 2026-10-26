"""HunterSkill_046 砥石使用高速化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_046"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillToishiHighSpeedCount": {
        "效果": "省略打磨次数",
        "作用于": "使用砥石的打磨循环次数",
        "计算": "打磨次数减去该值",
        "条件": "使用砥石时",
        "单位": "次",
        "依据": "cPorterRideUseItemToishi.doEnter",
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
