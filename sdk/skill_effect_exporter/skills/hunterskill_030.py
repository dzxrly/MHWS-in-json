"""HunterSkill_030 拔刀术【力】: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_030"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBattoPowerStunadd": {
        "效果": "拔刀攻击眩晕值加算",
        "作用于": "拔刀攻击的眩晕值",
        "计算": "加算；按武器取不同数据",
        "条件": "拔刀攻击（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.startBttoWaza（按技能等级）",
    },
    "getSkillBattoPowerAttackAdd": {
        "效果": "拔刀攻击基础攻击力加算",
        "作用于": "拔刀攻击的基础攻击力",
        "计算": "加算",
        "条件": "拔刀攻击（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.startBttoWaza（按技能等级）",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterSkill",
        "update",
        f"{GAME_VERSION} 全量求值 84 种情形（路径：完成 30）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
