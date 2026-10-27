"""HunterSkill_073 风压耐性: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_073"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillResistWind_S": {
        "效果": "风压【小】影响倍率",
        "作用于": "风压【小】硬直的持续时间 _DurationRate",
        "计算": "设为该值（SkillData 槽 0 × 0.01）；为 0 时不受影响",
        "条件": "受到风压【小】时",
        "单位": "倍",
        "依据": "cDamageWindStartS.doEnter、cDamageWindStartSS.doEnter",
    },
    "getSkillResistWind_L": {
        "效果": "风压【大】影响倍率",
        "作用于": "风压【大】的硬直",
        "计算": "倍率（SkillData 槽 1 × 0.01）；为 0 时不受影响",
        "条件": "受到风压【大】时",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillWind",
    },
    "getSkillResistWind_Dragon": {
        "效果": "龙风压影响倍率",
        "作用于": "龙风压的硬直",
        "计算": "倍率（SkillData 槽 2 × 0.01）；为 0 时不受影响，为 1 时与无技能相同",
        "条件": "受到龙风压时",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillWind",
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
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 96 种等级/参数情形（路径记录：分支超限 2）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
