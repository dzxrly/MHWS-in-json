"""HunterSkill_203 白炽龙之脉动: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_203"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillAutoRecoverIntervalTime": {
        "效果": "自动回复间隔",
        "作用于": "持续回复体力的间隔时间",
        "计算": "每隔该时间回复一次",
        "条件": "持续回复直至体力槽上限（游戏说明）",
        "单位": "时间（游戏内部单位）",
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
