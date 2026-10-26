"""HunterSkill_177 波衣龙之守护: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_177"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillMantleStrengtheningDefenseAdd": {
        "效果": "防御力加算",
        "作用于": "防御力",
        "计算": "加算",
        "条件": "使用特殊装备（装衣）后的一定时间内（游戏说明）",
        "单位": "点",
    },
    "getSkillMantleStrengtheningDefenseAttrAdd": {
        "效果": "属性耐性加算",
        "作用于": "火、水、雷、冰、龙耐性",
        "计算": "加算",
        "条件": "Lv4，使用特殊装备后的一定时间内（游戏说明）",
        "单位": "点",
    },
    "beginMantleStrengthening→_MantleStrengtheningInfo._Timer：_MantleStrengthening_MaxActiveTime": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _MantleStrengtheningInfo._Timer（calcDefenseAdd、calcAttrDefenseAdd 在它大于 0 时计入效果）",
        "计算": "设为该值（同时写入最大值）",
        "条件": "使用特殊装备（装衣）时开始计时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginMantleStrengthening",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill whose values the shared steps do not reach: (type,
# method, the reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "beginMantleStrengthening",
        "beginMantleStrengthening 操作状态对象 _HunterSkillParamInfo._MantleStrengtheningInfo（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_153，"
        "SkillToGroupSkill 把它换回本系列技能），把 PlayerSkillParam._MantleStrengthening_MaxActiveTime 写入它的 _Timer 与 _MaxTimer；"
        f"调用处 mcActiveSkillController.startASkillEffectiveTimer 已归到本技能，但它的求值没有得到这个字段的数值（{GAME_VERSION}）",
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
