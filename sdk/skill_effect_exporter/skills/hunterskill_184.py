"""HunterSkill_184 护锁刃龙之命脉: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_184"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBloodJoyAdd": {
        "效果": "体力回复量加算",
        "作用于": "破坏伤口时的体力回复量",
        "计算": "加算",
        "条件": "破坏大型怪物的伤口时（游戏说明）",
        "单位": "点",
    },
    "calcBloodJoyHeal：PlayerSkillParam._BloodJoyData": {
        "效果": "体力回复量",
        "作用于": "破坏伤口时的体力回复量",
        "计算": "返回回复量",
        "条件": "破坏大型怪物的伤口时（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcBloodJoyHeal",
        "情形": {
            "_BloodJoyData": "参数大于 5 时（参数取自游戏消息，含义未核实）",
            "5 >= 参数1:Int32": "",
            "参数1:Int32 < 2": "参数小于 2 时（参数取自游戏消息，含义未核实）",
        },
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
