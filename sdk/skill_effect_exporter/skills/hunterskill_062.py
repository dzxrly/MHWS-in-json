"""HunterSkill_062 弱点特效: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_062"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillWeakAttackHitCriticalAdd": {
        "效果": "有效部位会心率加算",
        "作用于": "命中时的会心率",
        "计算": "加算（SkillData 槽 0），并入命中会心率",
        "条件": "攻击对该部位颇为有效时（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.getCalcHitCriticalAdd",
    },
    "getSkillWeakAttackScarHitCriticalAdd": {
        "效果": "伤口会心率追加",
        "作用于": "命中时的会心率",
        "计算": "再加算（SkillData 槽 1，加在有效部位加算之上）",
        "条件": "攻击伤口时（游戏说明）",
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
