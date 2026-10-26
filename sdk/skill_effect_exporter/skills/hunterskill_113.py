"""HunterSkill_113 因祸得福: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_113"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDisasterAttrRate": {
        "效果": "属性值倍率",
        "作用于": "武器的属性值",
        "计算": "乘算（SkillData 槽 2 × 0.01），并入属性值倍率汇总",
        "条件": "解除状态异常或属性异常后的一定时间内（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcElemFireRate 等",
    },
    "getSkillDisasterCondRate": {
        "效果": "异常累积值倍率",
        "作用于": "武器的状态异常累积值",
        "计算": "乘算（SkillData 槽 1 × 0.01），并入异常值倍率汇总",
        "条件": "解除状态异常或属性异常后的一定时间内（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcElemPoisonRate 等",
    },
    "beginDisaster→_DisasterInfo._Timer：_Disaster_MaxActiveTime": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _DisasterInfo._Timer（calcElem*Rate 在它大于 0 时计入效果）",
        "计算": "设为该值（同时写入最大值）",
        "条件": "解除状态异常或属性异常时开始计时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginDisaster",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill the scan cannot tie to it: (type, method, the
# reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "beginDisaster",
        "beginDisaster 操作状态对象 _HunterSkillParamInfo._DisasterInfo（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_113），"
        f"把 PlayerSkillParam._Disaster_MaxActiveTime 写入它的 _Timer 与 _MaxTimer；技能来自该对象的 _Skill 而不是立即数，扫描无法对应（{GAME_VERSION}）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers,
    plus the functions declared above."""
    links = context.extract_skill(SKILL_ID)
    for type_name, method, reason in DECLARED_METHODS:
        links += context.extract_method(SKILL_ID, type_name, method, reason)
    return links


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
