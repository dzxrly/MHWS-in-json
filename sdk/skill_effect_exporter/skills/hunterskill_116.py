"""HunterSkill_116 急袭: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_116"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBehind_StealthAttackRate": {
        "效果": "攻击力倍率",
        "作用于": "攻击力",
        "计算": "乘算（SkillData 槽 0 × 0.01），并入攻击力倍率汇总",
        "条件": "成功奇袭大型怪物后的一定时间内（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcAttackRate",
    },
    "getSkillBehind_MaxTime": {
        "效果": "效果持续时间",
        "作用于": "攻击力提升的持续时间",
        "计算": "设为该值",
        "条件": "成功奇袭大型怪物后",
        "单位": "时间（游戏内部单位）",
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
