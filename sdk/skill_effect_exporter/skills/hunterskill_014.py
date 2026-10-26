"""HunterSkill_014 匠: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_014"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillTakumiKireajiLevelUpRate": {
        "效果": "锋利度延长倍率",
        "作用于": "武器锋利度槽的延长",
        "计算": "倍率；如何换算为游戏说明中的 +10～+50 锋利度未追踪到",
        "条件": "（游戏说明）延长锋利度槽，不超过上限",
        "单位": "倍",
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
