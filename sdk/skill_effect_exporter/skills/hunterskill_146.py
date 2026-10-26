"""HunterSkill_146 锁刃刺击: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_146"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillStabbingScarRate": {
        "效果": "造成创伤倍率",
        "作用于": "怪物伤口积蓄的伤害",
        "计算": "乘算",
        "条件": "攻击大型怪物时",
        "单位": "倍",
        "依据": "cEnemyStockDamage.detailCalcDamageRate_PlOt",
    },
    "getSkillStabbingAddDamage": {
        "效果": "追加无属性伤害",
        "作用于": "累积伤害后追加的无属性伤害",
        "计算": "设为该值（大于 0 时发动）",
        "条件": "以攻击累积伤害后（游戏说明）",
        "单位": "点",
        "依据": "cEnemyBadConditionSkillStabbing.onActivate",
        "情形": {
            "_StabbingData": "环境等级 CurrentRank 不为 1 时（读取 _StabbingData；等级含义未核实）",
            "SkillData 槽1": "环境等级 CurrentRank 为 1 时（读取 SkillData 槽 1；等级含义未核实）",
        },
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
