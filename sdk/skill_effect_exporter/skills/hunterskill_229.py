"""HunterSkill_229 能量石: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_229"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "beginSkillIamCoalMiner→_IamCoalMinerInfo._AttackAddValue：_IamCoalMinerData": {
        "效果": "攻击力加算",
        "作用于": "技能状态 _IamCoalMinerInfo._AttackAddValue",
        "计算": "设为该值；矿石稀有度越高提升越大（游戏说明），表中为此处读到的值",
        "条件": "采集矿石时",
        "单位": "点",
        "依据": "ItemUtil.sendSkilllamCoalMiner → cHunterSkill.beginSkillIamCoalMiner",
    }
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill the scan cannot tie to it: (type, method, the
# reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "beginSkillIamCoalMiner",
        "beginSkillIamCoalMiner 操作状态对象 _HunterSkillParamInfo._IamCoalMinerInfo（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_229），"
        "把 PlayerSkillParam._IamCoalMinerData 的数值写入它的 _Timer 与 _AttackAddValue；技能来自该对象的 _Skill 而不是立即数，扫描无法对应。"
        f"调用处 ItemUtil.sendSkilllamCoalMiner 先在物品表里查找矿石，这段查找让它的求值分支过多，直接求值本函数更简单（{GAME_VERSION}）",
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
