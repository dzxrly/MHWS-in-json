"""HunterSkill_035 炮术: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_035"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillArtilleryAttackAddRateWp07Shot": {
        "效果": "铳枪炮击攻击力倍率",
        "作用于": "命中时的攻击力",
        "计算": "乘算：1 + SkillData 槽 0 × 0.01",
        "条件": "铳枪炮击命中时",
        "单位": "倍",
        "依据": "cHunterSkill.calcHitAttackRate",
    },
    "getSkillArtilleryWp07RyuugekiTimerRate": {
        "效果": "龙击炮蓄能速度倍率",
        "作用于": "龙击炮的蓄能速度 _ChargeSpeedRate",
        "计算": "设为该值（SkillData 槽 1 × 0.01）",
        "条件": "龙击炮待机时",
        "单位": "倍",
        "依据": "cRyuugekiIdle.doEnter",
    },
    "getSkillArtilleryFireAttackAddWp07Shot": {
        "效果": "铳枪炮击火属性值加算",
        "作用于": "命中时攻击数据的属性值 _AttrValue",
        "计算": "加算（SkillData 槽 2）",
        "条件": "铳枪炮击命中时",
        "单位": "点（内部值，游戏内显示为其 10 倍）",
        "依据": "cHunterWp07Handling.doOnHit_AttackPre",
    },
    "getSkillArtilleryAttackRateWp09Grenade": {
        "效果": "盾斧榴弹瓶攻击力倍率",
        "作用于": "命中时的攻击力",
        "计算": "乘算（SkillData 槽 3 × 0.01）",
        "条件": "盾斧榴弹瓶的爆炸命中时",
        "单位": "倍",
        "依据": "cHunterSkill.calcHitAttackRate",
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
