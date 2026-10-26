"""HunterSkill_114 连击: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_114"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "calcContinuousAttackAddAttack": {
        "效果": "基础攻击力加算",
        "作用于": "基础攻击力",
        "计算": "加算，按武器取不同数据，并入攻击力加算汇总",
        "条件": "攻击连续命中时",
        "单位": "点",
        "依据": "cHunterSkill.calcContinuousAttackAddAttack",
        "情形": {
            "_ContinuousAttackExEmote00Data": "使用特殊动作 ExEmote00 的数据时（标志 IsUseExEmoteData 等，推测为特殊动作中）",
            "_ContinuousAttackWp": "使用武器自身的数据时",
            "_HitCount < 5": "连续命中不足 5 次",
            "_HitCount >= 5": "连续命中 5 次及以上",
        },
    },
    "calcContinuousAttackAddElem": {
        "效果": "属性值加算",
        "作用于": "武器的属性值",
        "计算": "加算，按武器取不同数据，并入属性值加算汇总",
        "条件": "攻击连续命中时",
        "单位": "点（内部值，推测游戏内显示为其 10 倍）",
        "依据": "cHunterSkill.calcContinuousAttackAddElem",
        "情形": {
            "_HitCount < 5": "连续命中不足 5 次",
            "_HitCount >= 5": "连续命中 5 次及以上",
            "_ContinuousAttackExEmote00Data": "使用特殊动作 ExEmote00 的数据时",
            "_ContinuousAttackWp": "使用武器自身的数据时",
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
