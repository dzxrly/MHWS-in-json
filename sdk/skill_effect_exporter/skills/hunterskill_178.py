"""HunterSkill_178 狱焰蛸之反叛: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_178"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillViolentAddDamage": {
        "效果": "追加伤害",
        "作用于": "攻击时额外造成的伤害",
        "计算": "数值为“a / b”时随战斗状态不同",
        "条件": "“怨恨”技能发动时（游戏说明）",
        "单位": "点",
        "情形": {
            "参数1=true": "读取 _ViolentData 的情形（布尔参数含义未核实）",
            "参数1=false": "读取 SkillData 槽 0 的情形（布尔参数含义未核实）",
        },
    }
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
