"""HunterSkill_058 挑战者: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_058"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillChallengerAttackAdd": {
        "效果": "攻击力加算",
        "作用于": "基础攻击力",
        "计算": "加算（SkillData 槽 0），并入攻击力加算汇总",
        "条件": "技能发动时（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcAttackAdd",
    },
    "getSkillChallengerCriticalAdd": {
        "效果": "会心率加算",
        "作用于": "会心率",
        "计算": "加算（SkillData 槽 1），并入会心率汇总",
        "条件": "技能发动时（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.getCalcCriticalAdd",
    },
    "update→_HunterSkillParamInfo._ChallengerLagTimer：_Challenger_MaxLagTimer": {
        "效果": "发动延迟时间",
        "作用于": "技能状态 _ChallengerLagTimer",
        "计算": "设为该值",
        "条件": "逐帧更新中写入；与另一行的区别在于所处情形（字段名中的 InTent 含义未核实）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.update",
    },
    "update→_HunterSkillParamInfo._ChallengerLagTimer：_Challenger_MaxInTentLagTimer": {
        "效果": "发动延迟时间（InTent）",
        "作用于": "技能状态 _ChallengerLagTimer",
        "计算": "设为该值",
        "条件": "逐帧更新中写入；字段名中的 InTent 含义未核实",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.update",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
