"""HunterSkill_063 力量解放: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_063"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillPowerAwakeStaminaRate": {
        "效果": "耐力消耗倍率",
        "作用于": "耐力消耗",
        "计算": "乘算",
        "条件": "技能发动时（游戏说明）",
        "单位": "倍",
    },
    "getSkillPowerAwakeCriticalAdd": {
        "效果": "会心率加算",
        "作用于": "会心率",
        "计算": "加算（SkillData 槽 0），并入会心率汇总",
        "条件": "技能发动时（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.getCalcCriticalAdd",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterHealth",
        "requestDamage",
        f"{GAME_VERSION} --all-links 复核 2 个常规链路范围，结果记录 320 种等级/参数情形（路径记录：完成 592、截断 8）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
