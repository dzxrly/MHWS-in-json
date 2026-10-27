"""HunterSkill_086 昏厥耐性: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_086"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillStanResistanceMaxTimeRate": {
        "效果": "昏厥持续时间倍率",
        "作用于": "昏厥状态的持续时间（基础 10 或 5）",
        "计算": "乘算；为 0 时不会陷入",
        "条件": "陷入昏厥时",
        "单位": "倍",
        "依据": "cStun.onDamageActionBegin",
    }
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
