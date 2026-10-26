"""HunterSkill_182 雪狮子王之斗志: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_182"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillMoraleTime": {
        "效果": "效果持续时间",
        "作用于": "“咆哮”后攻击力提升的持续时间",
        "计算": "设为该值",
        "条件": "使用肢体动作“咆哮”时（游戏说明）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillMoraleAttackAdd_ToPl": {
        "效果": "攻击力加算（猎人）",
        "作用于": "周围猎人的攻击力",
        "计算": "加算",
        "条件": "使用肢体动作“咆哮”后，持续时间内（游戏说明）",
        "单位": "点",
    },
    "getSkillMoraleAttackAdd_ToNpc": {
        "效果": "攻击力加算（随从与支援猎人）",
        "作用于": "随从与支援猎人的攻击力",
        "计算": "加算",
        "条件": "使用肢体动作“咆哮”后，持续时间内（游戏说明）",
        "单位": "点",
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
