"""HunterSkill_072 耳塞: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_072"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillEarPlugRate_S": {
        "效果": "咆哮【小】影响倍率",
        "作用于": "咆哮【小】的硬直",
        "计算": "倍率（SkillData 槽 0 × 0.01）；为 0 时不受影响",
        "条件": "受到咆哮【小】时",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillEarPlug",
    },
    "getSkillEarPlugRate_L": {
        "效果": "咆哮【大】影响倍率",
        "作用于": "咆哮【大】的硬直",
        "计算": "倍率（SkillData 槽 1 × 0.01）；为 0 时不受影响，为 1 时与无技能相同",
        "条件": "受到咆哮【大】时",
        "单位": "倍",
        "依据": "cHunterSkill.checkSkillEarPlug",
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
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 96 种等级/参数情形（路径记录：指令超限 2）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
