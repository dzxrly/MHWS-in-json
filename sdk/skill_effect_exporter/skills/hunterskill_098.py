"""HunterSkill_098 广域化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_098"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillItemWideEffectiveRate": {
        "效果": "同伴获得的效果比例",
        "作用于": "道具效果对周围同伴的强度",
        "计算": "乘算",
        "条件": "使用对应道具时",
        "单位": "倍",
        "依据": "mcHunterItem.checkNotUseItem_ItemWide（按技能等级）",
    },
    "getSkillItemWideEffectiveRadius": {
        "效果": "效果范围半径",
        "作用于": "道具效果影响同伴的范围",
        "计算": "设为该值",
        "条件": "使用对应道具时",
        "单位": "距离（游戏内部单位）",
        "依据": "mcHunterItem.checkNotUseItem_ItemWide（按技能等级）",
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
