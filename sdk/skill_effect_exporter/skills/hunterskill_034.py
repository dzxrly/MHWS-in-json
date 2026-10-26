"""HunterSkill_034 吹笛名人: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_034"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHueMasterSkillTimeAdd": {
        "效果": "旋律效果时间加算",
        "作用于": "狩猎笛旋律效果的持续时间",
        "计算": "数据为 0；实际按技能等级在旋律弹的设置中处理",
        "单位": "时间（游戏内部单位）",
        "依据": "mcShellPlWp05.onSetup、mcShellPlWp05Hibiki.onSetup（按技能等级）",
    },
    "getSkillHueMasterHealAdd": {
        "效果": "旋律回复量加算",
        "作用于": "狩猎笛旋律的体力回复量",
        "计算": "数据为 0；实际按技能等级在旋律弹的设置中处理",
        "单位": "点",
        "依据": "mcShellPlWp05.onSetup（按技能等级）",
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
