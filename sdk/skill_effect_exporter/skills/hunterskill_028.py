"""HunterSkill_028 攻击守势: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_028"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillKnightAttackRate": {
        "效果": "攻击力倍率",
        "作用于": "攻击力",
        "计算": "乘算（SkillData 槽 0 × 0.01），并入攻击力倍率汇总",
        "条件": "技能发动时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcAttackRate",
    },
    "update→_KnightInfo.<JustGuardTimer>k__BackingField：_KnightData": {
        "效果": "发动判定计时",
        "作用于": "技能状态 _KnightInfo.JustGuardTimer",
        "计算": "设为该值",
        "条件": "逐帧更新中写入；计时用途未核实",
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
