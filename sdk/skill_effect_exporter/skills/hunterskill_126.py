"""HunterSkill_126 猎人生活: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_126"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHunterLifeMeatGrillBurnTime": {
        "效果": "烤焦时间",
        "作用于": "烤肉的烤焦时刻",
        "计算": "烤肉计时达到该值时烤焦",
        "条件": "烤肉时",
        "单位": "时间（游戏内部单位）",
        "依据": "mcMeatGrill.updateMain、mcOldMeatGrill.updateMain",
    },
    "getSkillHunterLifeMeatGrillMusicGameInputCD": {
        "效果": "烤肉输入冷却",
        "作用于": "烤肉小游戏的输入冷却时间",
        "计算": "设为该值",
        "条件": "烤肉时",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillHunterLifeMeatGrillMusicGameJustTiming": {
        "效果": "烤肉判定时机",
        "作用于": "烤肉小游戏的判定时机",
        "计算": "设为该值",
        "条件": "烤肉时",
        "单位": "时间（游戏内部单位）",
    },
    "getSkillHunterLifeEggMoveTransRate": {
        "效果": "搬运移动距离倍率",
        "作用于": "搬蛋时滑行、攀爬的移动量",
        "计算": "乘算",
        "条件": "搬运蛋等物品时",
        "单位": "倍",
        "依据": "cEggSliding.doEnter、cEggClimbWallMove.doEnter",
        "情形": {
            "参数1=true": "爬墙搬运时（读取 Wall 数据）",
            "参数1=false": "平地搬运时（读取 Move 数据）",
        },
    },
    "getSkillHunterLifeEggMoveMotSpeedRate": {
        "效果": "搬运动作速度倍率",
        "作用于": "搬蛋时的动作速度",
        "计算": "乘算",
        "条件": "搬运蛋等物品时",
        "单位": "倍",
        "依据": "cEggSliding.doEnter、cEggSlidingSign.doEnter、cEggClimbWallMove.doEnter",
        "情形": {
            "参数1=true": "爬墙搬运时（读取 Wall 数据）",
            "参数1=false": "平地搬运时（读取 Move 数据）",
        },
    },
    "getSkillHunterLifeCableMoveTransRate": {
        "效果": "钩索移动距离倍率",
        "作用于": "钩索移动的移动量",
        "计算": "乘算",
        "条件": "使用钩索移动时",
        "单位": "倍",
        "依据": "cExGm00Move.doEnter",
    },
    "getSkillHunterLifeCableMoveMotSpeedRate": {
        "效果": "钩索移动动作速度倍率",
        "作用于": "钩索移动、冲刺的动作速度",
        "计算": "乘算",
        "条件": "使用钩索移动时",
        "单位": "倍",
        "依据": "cExGm00Move.doEnter、cExGm00Dash.doEnter",
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
