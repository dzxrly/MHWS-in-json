"""HunterSkill_200 泡狐龙之力: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_200"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "forceActivate→cEx00._DurationTime：_BubbleDance_MaxActiveTime": {
        "效果": "泡沫状态【小】持续时间",
        "作用于": "泡沫状态的持续时间 cEx00._DurationTime",
        "计算": "设为该值",
        "条件": "回避数次后进入泡沫状态【小】时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "HunterBadConditions.cEx00.forceActivate",
    },
    "getDodgeNoHitTime": {
        "效果": "泡沫状态回避无敌时间",
        "作用于": "各回避动作的无敌时间",
        "计算": "回避性能等级加上 _BubbleDance_AddSkillLv 后，按回避动作取对应等级的无敌时间",
        "条件": "Lv4，泡沫状态中（游戏说明：强化泡沫状态下的回避能力）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.getDodgeNoHitTime（读取 PlayerSkillParam._BubbleDance_AddSkillLv）",
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
