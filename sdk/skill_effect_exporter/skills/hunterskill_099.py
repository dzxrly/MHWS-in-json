"""HunterSkill_099 满足感: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_099"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillManzokuNoUseRate": {
        "效果": "不消耗概率",
        "作用于": "饮食类道具的消耗",
        "计算": "按比例随机判定（SkillData 槽 0 × 0.01），成立时不消耗",
        "条件": "使用饮食类道具时",
        "单位": "比例（0.1 即 10%）",
        "依据": "cHunterExtendPlayer.onSuccessItem",
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
