"""HunterSkill_198 首发迅击: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_198"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillFirstShotReloadSpeedRate": {
        "效果": "装填动作速度倍率",
        "作用于": "装填类动作的动作速度 _MotionSpeed",
        "计算": "乘算",
        "条件": "弩炮装填、装填回避、跳跃攻击等动作开始时",
        "单位": "倍",
        "依据": "cReloadBase.doEnter、cReloadStepDodgeBase.doEnter、cJumpAttack.doEnter、cPorterRideReloadBase.doEnter",
    },
    "getSkillFirstShotLightAttackAdd": {
        "效果": "满足条件的弹药攻击力加算（轻弩）",
        "作用于": "命中时的攻击力",
        "计算": "加算",
        "条件": "技能发动中，且命中的弹丸对象中一个未命名的状态值为 0（含义未核实）",
        "单位": "点",
        "依据": "cHunterWpGunHandling.getOnHitAttackPowerAdd（弹丸对象+0x90 == 0）",
    },
    "getSkillFirstShotHeavyAttackAdd": {
        "效果": "满足条件的弹药攻击力加算（重弩）",
        "作用于": "命中时的攻击力",
        "计算": "加算",
        "条件": "与轻弩相同（重弩的调用处未单独追踪）",
        "单位": "点",
    },
    "getSkillFirstShotLightAttrRate": {
        "效果": "满足条件的弹药属性倍率（轻弩）",
        "作用于": "属性值",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
    },
    "getSkillFirstShotHeavyAttrRate": {
        "效果": "满足条件的弹药属性倍率（重弩）",
        "作用于": "属性值",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
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
