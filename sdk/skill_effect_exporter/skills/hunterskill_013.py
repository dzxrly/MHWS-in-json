"""HunterSkill_013 爆破属性强化: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_013"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBlastAttackRate": {
        "效果": "爆破累积值倍率",
        "作用于": "武器的爆破累积值",
        "计算": "乘算（SkillData 槽 0 × 0.01），并入异常值倍率汇总；先乘后加",
        "单位": "倍",
        "依据": "cHunterSkill.calcElemBlastRate",
    },
    "getSkillBlastAttackAdd": {
        "效果": "爆破累积值加算",
        "作用于": "武器的爆破累积值",
        "计算": "加算（SkillData 槽 1），并入异常值加算汇总",
        "单位": "点（内部值，游戏内显示为其 10 倍）",
        "依据": "cHunterSkill.calcElemBlastAdd",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterAttackPower",
        "calcAttrPower",
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 4539 种等级/参数情形（路径记录：完成 36）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
