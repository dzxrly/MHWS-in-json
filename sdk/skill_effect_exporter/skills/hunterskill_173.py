"""HunterSkill_173 护龙之守护: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_173"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGuardianAreaEnergyAttackBlessRate": {
        "效果": "特殊伤害倍率",
        "作用于": "受到的特殊（能量）伤害",
        "计算": "乘算",
        "条件": "位于龙都遗迹时（游戏说明）",
        "单位": "倍",
    },
    "getSkillGuardianAreaAttrBlessRate": {
        "效果": "属性伤害倍率",
        "作用于": "受到的属性伤害（计入属性耐性后）",
        "计算": "乘算",
        "条件": "位于龙都遗迹时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterStockDamage.calcAttrDamageValue",
    },
    "beginSkillGuardianArea→_GuardianAreaInfo._Timer：_GuardianAreaData": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _GuardianAreaInfo._Timer（calcAttrDamageValue、applyDamage 在它大于 0 时计入效果）",
        "计算": "设为该值（同时写入最大值）",
        "条件": "位于龙都遗迹时开始计时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginSkillGuardianArea",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill the scan cannot tie to it: (type, method, the
# reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "beginSkillGuardianArea",
        "beginSkillGuardianArea 操作状态对象 _HunterSkillParamInfo._GuardianAreaInfo（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_173），"
        f"把 PlayerSkillParam._GuardianAreaData 的数值写入它的 _Timer 与 _MaxTimer；技能来自该对象的 _Skill 而不是立即数，扫描无法对应（{GAME_VERSION}）",
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
