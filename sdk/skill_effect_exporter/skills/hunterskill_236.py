"""HunterSkill_236 暗黑骑士之证: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_236"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDarkWaveAttrRate": {
        "效果": "属性值倍率",
        "作用于": "属性值",
        "计算": "乘算",
        "条件": "体力槽有红色部分时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.updateAfter（按技能等级）",
    },
    "getSkillAccHealValue": {
        "效果": "体力回复量",
        "作用于": "体力",
        "计算": "回复该值；按武器取不同数据，固定读取 Lv4 的数据",
        "条件": "处于 DK_COUNTER_BUFF 状态时命中怪物：距上次计数不足 PlayerSkillParam._AccHealData[4]（0.5 秒）的命中不计，"
        "满 _AccHealData[3]（1 次）回复一次；处于 FORCE_ACC_HEAL_LOW 状态时改用弓弩一档的数值；EX_FIELD 状态下不计数",
        "单位": "点",
        "依据": "cHunterSkill.evHit_AttackPostProcess（固定读取 Lv4）",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []

# (type, method, reviewed evidence): functions the scan cannot tie to this skill.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "getSkillAccHealValue",
        "getSkillAccHealValue(武器, 布尔) 在布尔参数为真时以技能 0xF1 与固定等级参数 5 调用 getSkillValue，"
        "读到本技能 Lv4 的 SkillData；为假时读锁刃龙之饥饿。两次调用共用一个调用点，扫描只记下后者的技能。"
        "evHit_AttackPostProcess 在 STATUS_FLAG DK_COUNTER_BUFF 成立时按同样方式回复体力"
        f"（{GAME_VERSION}）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers,
    and of the functions declared above."""
    links = context.extract_skill(SKILL_ID)
    for type_name, method, reason in DECLARED_METHODS:
        links += context.extract_method(SKILL_ID, type_name, method, reason)
    return links


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
