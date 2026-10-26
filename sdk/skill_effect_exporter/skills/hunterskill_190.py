"""HunterSkill_190 属性吸收: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_190"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillElementConvertDamageRate": {
        "效果": "属性伤害相关倍率",
        "作用于": "受到属性攻击后效果中的属性伤害",
        "计算": "倍率；具体用法未追踪到",
        "条件": "受到属性攻击后发动时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcElementConvertAttrAdd（按技能等级）",
    },
    "getSkillElementConvertAttackRate": {
        "效果": "属性攻击值相关倍率",
        "作用于": "受到属性攻击后效果中的属性攻击值",
        "计算": "倍率；具体用法未追踪到",
        "条件": "受到属性攻击后发动时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcElementConvertAttrAdd（按技能等级）",
    },
    "calcElementConvertAddElem：PlayerSkillParam._ElementConvertWp00Data、PlayerSkillParam._ElementConvertWp01Data、PlayerSkillParam._ElementConvertWp02Data、PlayerSkillParam._ElementConvertWp03Data、PlayerSkillParam._ElementConvertWp04Data、PlayerSkillParam._ElementConvertWp05Data、PlayerSkillParam._ElementConvertWp06Data、PlayerSkillParam._ElementConvertWp07Data、PlayerSkillParam._ElementConvertWp08Data、PlayerSkillParam._ElementConvertWp09Data、PlayerSkillParam._ElementConvertWp10Data、PlayerSkillParam._ElementConvertWp11Data、PlayerSkillParam._ElementConvertWp12Data、PlayerSkillParam._ElementConvertWp13Data": {
        "效果": "属性值加算",
        "作用于": "武器的属性值",
        "计算": "加算，按武器取不同数据，并入属性值加算汇总",
        "条件": "受到属性攻击后发动时（游戏说明）",
        "单位": "点（内部值，推测游戏内显示为其 10 倍）",
        "依据": "cHunterSkill.calcElementConvertAddElem",
        "情形": {
            "_ElementConvertInfo._HitCount != ": "",
            "_ElementConvertInfo._HitCount == 1": "计数 _HitCount 为 1",
            "_ElementConvertInfo._HitCount == 2": "计数 _HitCount 为 2",
            "_ElementConvertInfo._HitCount == 3": "计数 _HitCount 为 3",
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
