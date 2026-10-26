"""HunterSkill_174 前辈之指引: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_174"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillEexplorerLuck_AddRate": {
        "效果": "活跃化采集点发生率",
        "作用于": "活跃化采集点的发生率（游戏说明）",
        "计算": "调用处未追踪到",
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
