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
        "作用于": "怪物体力",
        "计算": "每次触发追加表中点数的无属性伤害",
        "条件": "攻击积蓄达到阈值时",
        "单位": "点",
        "依据": (
            "cHunterSkill.getSkillStabbingAddDamage 按 EnvironmentManager.CurrentRank 取值。"
            "下位（STORY）读 SkillData 槽 1，上位（EX）读 _StabbingData。"
            "未传入已初始化的怪物上下文时也读槽 1。"
            "cEnemyBadConditionSkillStabbing.onActivate 将该值直接传给 EnemyCharacter.requestDamage"
        ),
        "情形": {
            "_StabbingData": "上位",
            "SkillData 槽1": "下位",
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
