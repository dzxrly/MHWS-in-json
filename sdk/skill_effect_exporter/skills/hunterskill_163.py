"""HunterSkill_163 甲虫之拟态: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_163"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHidingLostRate": {
        "效果": "目标丢失倍率",
        "作用于": "大型怪物丢失猎人的判定",
        "计算": "乘算",
        "条件": "蹲下移动时（游戏说明）；调用处未追踪到",
        "单位": "倍",
    },
    "getSkillHidingMaxCount": {
        "效果": "隐蔽最大次数",
        "作用于": "隐蔽效果的次数上限",
        "计算": "设为该值",
        "条件": "调用处未追踪到",
        "单位": "次",
        "依据": "EnemyUtil.setOccludeBitFromHunter（按技能等级）",
    },
    "getSkillHidingFeelRate": {
        "效果": "察觉值倍率",
        "作用于": "大型怪物对猎人的察觉值",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
        "依据": "EnemyUtil.setOccludeBitFromHunter（按技能等级）",
    },
    "getSkillHidingSightBeginSecRate": {
        "效果": "进入视野判定时间倍率",
        "作用于": "怪物视野判定开始的秒数",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
        "依据": "EnemyUtil.setOccludeBitFromHunter（按技能等级）",
    },
    "getSkillHidingCrouchMotSpeedRate": {
        "效果": "蹲下移动动作速度倍率",
        "作用于": "蹲下行走、奔跑、转身的动作速度",
        "计算": "乘算",
        "条件": "蹲下移动时",
        "单位": "倍",
        "依据": "cSquatWalk.doEnter、cSquatRun.doEnter、cSquatRunTurn.doEnter、cSquatIdleTurn.doEnter",
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
