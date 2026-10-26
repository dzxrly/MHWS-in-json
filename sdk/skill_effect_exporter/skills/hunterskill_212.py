"""HunterSkill_212 海龙的涡雷: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_212"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDischargeCoolTime": {
        "效果": "再次发动冷却时间",
        "作用于": "追加雷属性伤害的冷却时间",
        "计算": "设为该值",
        "条件": "发动后",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginSkillDischarge（按技能等级）",
    },
    "getSkillDischargeCriticalTime": {
        "效果": "会心率提升持续时间",
        "作用于": "会心率提升的持续时间",
        "计算": "设为该值",
        "条件": "以攻击累积伤害后发动时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginSkillDischarge（按技能等级）",
    },
    "getSkillDischargeCriticalAdd": {
        "效果": "会心率加算",
        "作用于": "会心率",
        "计算": "加算",
        "条件": "效果持续时间内（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.beginSkillDischarge（按技能等级）",
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
