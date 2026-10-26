"""HunterSkill_111 攻势: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_111"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillOffensiveAttackAdd": {
        "效果": "基础攻击力加算",
        "作用于": "命中时的攻击力",
        "计算": "加算（SkillData 槽 0），并入命中攻击力加算",
        "条件": "对陷入毒或麻痹状态的大型怪物（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcHitAttackAdd",
    },
    "getSkillOffensiveCriticalAdd": {
        "效果": "会心率加算",
        "作用于": "命中时的会心率",
        "计算": "加算（SkillData 槽 1），并入命中会心率",
        "条件": "对陷入毒或麻痹状态的大型怪物（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.getCalcHitCriticalAdd",
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
