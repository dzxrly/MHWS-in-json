"""HunterSkill_239 巨戟龙的默示录: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_239"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillChallengerAttrAttrAdd": {
        "效果": "属性值加算",
        "作用于": "属性值",
        "计算": "加算",
        "条件": "战斗中的大型怪物发怒时（游戏说明）",
        "单位": "点",
    },
    "calcChallengerAttrAttrRate：SkillData[HunterSkill_239]._value[0]": {
        "效果": "属性值倍率",
        "作用于": "属性值",
        "计算": "乘算",
        "条件": "战斗中的大型怪物发怒时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcChallengerAttrAttrRate",
    },
    "update→_HunterSkillParamInfo._ChallengerAttrLagTimer：_ChallengerAttr_MaxInTentLagTimer": {
        "效果": "发动延迟时间（InTent）",
        "作用于": "技能状态 _ChallengerAttrLagTimer",
        "计算": "设为该值",
        "条件": "逐帧更新中写入；字段名中的 InTent 含义未核实",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.update",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterHealth",
        "requestDamage",
        f"{GAME_VERSION} --all-links 复核 2 个常规链路范围，结果记录 128 种等级/参数情形（路径记录：完成 2176、截断 17）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
