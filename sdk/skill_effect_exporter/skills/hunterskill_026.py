"""HunterSkill_026 格挡性能: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_026"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGuardAbility_StaminaRate": {
        "效果": "格挡耐力消耗倍率",
        "作用于": "格挡时的耐力消耗",
        "计算": "乘算",
        "条件": "格挡时（游戏说明）",
        "单位": "倍",
    },
    "getskillGuardAbility_MaxGuardPowerAdd": {
        "效果": "最大格挡性能加算",
        "作用于": "格挡反应的判定",
        "计算": "加算",
        "条件": "格挡时",
        "单位": "点",
        "依据": "cHunterStockDamage.calcGuardReaction",
    },
    "getSkillGuardAbility_GuardPowerAdd": {
        "效果": "格挡性能加算",
        "作用于": "格挡反应的判定（与所受攻击的强度比较）",
        "计算": "加算到格挡性能（SkillData 槽 0）",
        "条件": "格挡时",
        "单位": "点",
        "依据": "cHunterStockDamage.calcGuardReaction",
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
