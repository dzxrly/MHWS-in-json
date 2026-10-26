"""HunterSkill_074 耐震: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_074"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillResistQuake_SS": {
        "效果": "震动【极小】影响倍率",
        "作用于": "震动【极小】硬直的持续时间 _DurationRate",
        "计算": "设为该值；为 0 时不受影响",
        "条件": "受到震动【极小】时",
        "单位": "倍",
        "依据": "cDamageQuakeSS.doEnter",
    },
    "getSkillResistQuake_S": {
        "效果": "震动【小】影响倍率",
        "作用于": "震动【小】硬直的持续时间 _DurationRate",
        "计算": "设为该值；为 0 时不受影响",
        "条件": "受到震动【小】时",
        "单位": "倍",
        "依据": "cDamageQuakeS.doEnter",
    },
    "getSkillResistQuake_L": {
        "效果": "震动【大】影响倍率",
        "作用于": "震动【大】的硬直",
        "计算": "倍率（SkillData 槽 2 × 0.01）；为 0 时不受影响，为 1 时与无技能相同",
        "条件": "受到震动【大】时",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillResistQuake",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cPorterStockDamage",
        "checkArmorSkill",
        f"{GAME_VERSION} 全量求值 96 种情形（路径：指令超限 2）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
