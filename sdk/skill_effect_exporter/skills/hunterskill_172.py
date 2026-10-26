"""HunterSkill_172 护龙之脉动: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_172"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillRyunyuHealRedHealthRate": {
        "效果": "龙乳结晶附近红色体力回复速度倍率",
        "作用于": "红色体力的回复速度",
        "计算": "乘算",
        "条件": "接近龙乳结晶时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.updateBuffEffect（按技能等级）",
    },
    "getSkillRyunyuHealStaminaRate": {
        "效果": "龙乳结晶附近耐力回复速度倍率",
        "作用于": "耐力回复速度",
        "计算": "乘算",
        "条件": "接近龙乳结晶时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.updateBuffEffect（按技能等级）",
    },
    "getSkillRedHealthSpeedRate": {
        "效果": "红色体力回复速度倍率",
        "作用于": "红色体力的回复速度 _RedRecoverTimeRate",
        "计算": "乘算",
        "条件": "体力槽有红色部分时",
        "单位": "倍",
        "依据": "cHunterStatus.updateHealth",
    },
    "beginRyunyu→_RyunyuInfo._Timer：_RyunyuData": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _RyunyuInfo._Timer（getSkillRedHealthSpeedRate、updateStamina 在它大于 0 时计入效果）",
        "计算": "设为该值（同时写入最大值）",
        "条件": "接近龙乳结晶时开始计时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginRyunyu",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill the scan cannot tie to it: (type, method, the
# reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "beginRyunyu",
        "beginRyunyu 操作状态对象 _HunterSkillParamInfo._RyunyuInfo（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_149，"
        "SkillToGroupSkill 把它换回本组合技能），把 PlayerSkillParam._RyunyuData 的数值写入它的 _Timer 与 _MaxTimer；"
        f"技能来自该对象的 _Skill 而不是立即数，扫描无法对应（{GAME_VERSION}）",
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
