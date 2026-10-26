"""HunterSkill_023 强化持续: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_023"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillPowerProlongeTimeRate": {
        "效果": "强化状态持续时间倍率",
        "作用于": "武器强化状态的持续时间（如双刀见切增益、盾斧强化计时）",
        "计算": "设定时乘算；逐帧递减时除以本倍率",
        "条件": "对应强化状态中",
        "单位": "倍",
        "依据": "cHunterWp02Handling.doMikiriSuccess、cHunterWp09Handling.doUpdateReserve",
    },
    "getSkillPowerProlongeExEmote00TimeRate": {
        "效果": "强化状态持续时间倍率（ExEmote00）",
        "作用于": "ExEmote00 相关强化状态的持续时间",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
    },
    "getSkillPowerProlongeDarkBladeTimeRate": {
        "效果": "强化状态持续时间倍率（DarkBlade）",
        "作用于": "DarkBlade 相关强化状态的持续时间",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
    },
    "getSkillDarkBladeAttackUpTime": {
        "效果": "DarkBlade 攻击力提升时间",
        "作用于": "DarkBlade 状态的攻击力提升持续时间",
        "计算": "设为该值",
        "条件": "调用处未追踪到",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginSkillDarkBlade（按技能等级）",
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
