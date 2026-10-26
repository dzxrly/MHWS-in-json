"""HunterSkill_202 浸水刃纹: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_202"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBubbleToishiCriticalAdd_Water": {
        "效果": "淋湿时会心率加算",
        "作用于": "会心率",
        "计算": "加算（SkillData 槽 0），并入会心率汇总",
        "条件": "身体淋湿时（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.getCalcCriticalAdd",
    },
    "getSkillBubbleToishiCriticalAdd_Bubble": {
        "效果": "泡沫状态会心率加算",
        "作用于": "会心率",
        "计算": "加算（SkillData 槽 1），并入会心率汇总",
        "条件": "泡沫状态时（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.getCalcCriticalAdd",
    },
    "updateAfter→_HunterSkillParamInfo._BubbleToishiContinueTime：_BubbleToishiMaxContinueTime": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _BubbleToishiContinueTime",
        "计算": "设为该值",
        "条件": "逐帧更新中写入",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.updateAfter",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions evaluated for this skill beyond the shared steps: (type, method,
# the reviewed evidence, parameter fields to focus on), checked against the
# code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "updateAfter",
        "cHunterSkill.updateAfter 在 _BubbleToishiBit 置位时把 PlayerSkillParam._BubbleToishiMaxContinueTime 写入 "
        "_HunterSkillParamInfo._BubbleToishiContinueTime；updateAfter 是许多技能共用的逐帧函数，"
        f"共通的参数字段步骤同时追踪其他字段的读取点，窄聚焦只在少数路径上到达这次写入，因此只聚焦这个字段（{GAME_VERSION}）",
        ("_BubbleToishiMaxContinueTime",),
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers,
    plus the functions declared above, focused on the named fields."""
    links = context.extract_skill(SKILL_ID)
    for declared in DECLARED_METHODS:
        links += context.extract_method(SKILL_ID, *declared)
    return links


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
