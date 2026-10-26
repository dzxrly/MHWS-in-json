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
        f"{GAME_VERSION} 全量求值 640 种情形（路径：完成 592、未列出 8）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
