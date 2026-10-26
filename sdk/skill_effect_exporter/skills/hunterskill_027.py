"""HunterSkill_027 格挡强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_027"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGuardPowerDamageRate": {
        "效果": "格挡伤害倍率",
        "作用于": "格挡时所受伤害",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "格挡时；与 EnableGuard 倍率的分工未核实（游戏说明：满足条件时再减少伤害）",
        "单位": "倍",
        "依据": "cHunterStockDamage.calcGuardDamageRate",
    },
    "getSkillGuardPowerDamageRateEnableGuard": {
        "效果": "格挡伤害倍率（EnableGuard）",
        "作用于": "格挡时所受伤害",
        "计算": "乘算（SkillData 槽 1 × 0.01，再乘武器动作参数的减伤率）",
        "条件": "格挡时；与另一倍率的分工未核实",
        "单位": "倍",
        "依据": "cHunterStockDamage.calcGuardDamageRate",
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
