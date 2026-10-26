"""HunterSkill_167 叠鳞之工艺: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_167"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHunkiActiveSkillTime": {
        "效果": "效果持续时间",
        "作用于": "耐力消耗减少的持续时间",
        "计算": "设为该值",
        "条件": "体力降至 40% 或以下时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.updateAfter（按技能等级）",
    },
    "getSkillHunkiStamitaRate": {
        "效果": "耐力消耗倍率",
        "作用于": "耐力消耗",
        "计算": "乘算",
        "条件": "效果持续时间内（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.updateAfter（按技能等级）",
    },
    "endSkill→cHunkiInfo._CoolTime：_Hunki_MaxCoolTime": {
        "效果": "效果结束后的冷却时间",
        "作用于": "技能状态 _HunkiInfo._CoolTime",
        "计算": "设为该值",
        "条件": "效果结束时；冷却时间的用途未核实",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkillParamInfo.cHunkiInfo.endSkill",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill the scan cannot tie to it: (type, method, the
# reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkillParamInfo.cHunkiInfo",
        "endSkill",
        "cHunkiInfo.endSkill 重写 cInfo.endSkill（虚函数表槽 7），EXE 中没有对它的直接调用，扫描找不到调用处；"
        "cHunkiInfo 是状态对象 _HunterSkillParamInfo._HunkiInfo 的类型（构造时写入 _Skill = HunterSkill_140，"
        f"SkillToGroupSkill 把它换回本组合技能），endSkill 把 PlayerSkillParam._Hunki_MaxCoolTime 写入 _CoolTime（{GAME_VERSION}）",
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
