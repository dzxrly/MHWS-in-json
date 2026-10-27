"""HunterSkill_075 回避性能: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_075"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getDodgeNoHitTime": {
        "效果": "回避无敌时间",
        "作用于": "回避动作的无敌时间",
        "计算": "设为该值；按回避动作取不同数据",
        "条件": "回避时",
        "单位": "时间（游戏内部单位）",
    }
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterSkill",
        "getNpcDodgeNoHitTime",
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 85 种等级/参数情形（路径记录：完成 279、截断 8）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
