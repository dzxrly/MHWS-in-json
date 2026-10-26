"""HunterSkill_237 欧米茄共鸣: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_237"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillShieldOptionValue_ToPl": {
        "效果": "合成盾效果数值（猎人）",
        "作用于": "“合成盾”对猎人的效果",
        "计算": "未追踪到调用处",
        "条件": "Lv4 起提升（游戏说明）",
        "单位": "",
    },
    "getSkillShieldOptionTime_ToPl": {
        "效果": "合成盾持续时间（猎人）",
        "作用于": "“合成盾”对猎人的持续时间",
        "计算": "设为该值（推测）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillCooperationValue_ToPl": {
        "效果": "协作程序效果数值（猎人）",
        "作用于": "“协作程序”对猎人的效果",
        "计算": "未追踪到调用处",
        "单位": "",
    },
    "getSkillCooperationTime_ToPl": {
        "效果": "协作程序持续时间（猎人）",
        "作用于": "“协作程序”对猎人的持续时间",
        "计算": "设为该值（推测）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillShieldOptionTime_ToNpc": {
        "效果": "合成盾持续时间（随从与支援猎人）",
        "作用于": "“合成盾”对随从与支援猎人的持续时间",
        "计算": "设为该值（推测）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillCooperationTime_ToNpc": {
        "效果": "协作程序持续时间（随从与支援猎人）",
        "作用于": "“协作程序”对随从与支援猎人的持续时间",
        "计算": "设为该值（推测）",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillResonanceFarAttackAdd": {
        "效果": "共鸣：远 攻击力加算",
        "作用于": "攻击力",
        "计算": "加算",
        "条件": "“共鸣：远”发动且满足条件时（游戏说明）",
        "单位": "点",
    },
    "getSkillResonanceNearCriticalAdd": {
        "效果": "共鸣：近 会心率加算",
        "作用于": "会心率",
        "计算": "加算",
        "条件": "“共鸣：近”发动且满足条件时（游戏说明）",
        "单位": "%",
    },
    "beginResonanceNearCriticalAdd→_ResonanceInfo._NearTimer：_ResonanceData": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _ResonanceInfo._NearTimer（getCalcCriticalAdd 在它大于 0 时计入效果）；“共鸣：远”的 _FarTimer（calcAttackAdd 用）由 beginResonanceFarAttackAdd 写入同一数值",
        "计算": "设为该值（同时写入最大值）",
        "条件": "“共鸣：近”发动时开始计时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginResonanceNearCriticalAdd",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill the scan cannot tie to it: (type, method, the
# reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "beginResonanceNearCriticalAdd",
        "beginResonanceNearCriticalAdd 操作状态对象 _HunterSkillParamInfo._ResonanceInfo（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_241，"
        f"SkillToGroupSkill 把它换回本系列技能），把 PlayerSkillParam._ResonanceData 的数值写入它的 _NearTimer；技能来自该对象的 _Skill 而不是立即数，扫描无法对应（{GAME_VERSION}）",
    ),
    (
        "app.cHunterSkill",
        "beginResonanceFarAttackAdd",
        "beginResonanceFarAttackAdd 操作状态对象 _HunterSkillParamInfo._ResonanceInfo（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_241，"
        f"SkillToGroupSkill 把它换回本系列技能），把 PlayerSkillParam._ResonanceData 的数值写入它的 _FarTimer；技能来自该对象的 _Skill 而不是立即数，扫描无法对应（{GAME_VERSION}）",
    ),
]


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterSkill",
        "update",
        f"{GAME_VERSION} 全量求值 56 种情形（路径：完成 32）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers,
    plus the functions declared above."""
    links = context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)
    for type_name, method, reason in DECLARED_METHODS:
        links += context.extract_method(SKILL_ID, type_name, method, reason)
    return links


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
