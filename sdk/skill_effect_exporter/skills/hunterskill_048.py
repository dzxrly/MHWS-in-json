"""HunterSkill_048 蓄力大师: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_048"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillChargeMasterAttrRate": {
        "效果": "蓄力攻击属性值倍率",
        "作用于": "命中时攻击数据的属性值 _AttrValue",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "蓄力攻击命中时（判断蓄力的条件在命中处理中，未完整追踪）",
        "单位": "倍",
        "依据": "cHunterWp03Handling.doOnHit_AttackPre、cHunterSkill.calcChargeMasterAttrRate、calcElem*Rate",
    },
    "getSkillChargeMasterCondRate": {
        "效果": "蓄力攻击异常累积倍率",
        "作用于": "命中时攻击数据的毒、麻痹、睡眠、爆破累积值",
        "计算": "乘算（SkillData 槽 2 × 0.01）",
        "条件": "蓄力攻击命中时（判断蓄力的条件在命中处理中，未完整追踪）",
        "单位": "倍",
        "依据": "cHunterWp03Handling.doOnHit_AttackPre、cHunterSkill.calcChargeMasterCondRate、calcElemPoisonRate",
    },
    "getSkillChargeMasterBowAttrRate": {
        "效果": "蓄力攻击属性值倍率（弓）",
        "作用于": "属性值（弓）",
        "计算": "乘算",
        "条件": "弓的蓄力射击；调用处未追踪到",
        "单位": "倍",
    },
    "getSkillChargeMasterBowCondRate": {
        "效果": "蓄力攻击异常累积倍率（弓）",
        "作用于": "状态异常累积值（弓）",
        "计算": "乘算",
        "条件": "弓的蓄力射击；调用处未追踪到",
        "单位": "倍",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.HunterCharacter",
        "makeActualAttackParam",
        f"{GAME_VERSION} --all-links 复核 2 个常规链路范围，结果记录 89 种等级/参数情形（路径记录：完成 64、分支超限 4）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
