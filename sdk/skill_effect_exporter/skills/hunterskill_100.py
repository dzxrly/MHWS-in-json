"""HunterSkill_100 火场怪力: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_100"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillKaziba_AttackRate": {
        "效果": "攻击力倍率",
        "作用于": "当前攻击力",
        "计算": "乘算（SkillData 槽 0）",
        "条件": "体力在最大值的 35% 以下时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterAttackPower.calcCurrentAttackPower",
    },
    "getSkillKaziba_DefenseAdd": {
        "效果": "防御力加算",
        "作用于": "防御力",
        "计算": "加算（SkillData 槽 1），并入防御力加算汇总",
        "条件": "体力在最大值的 35% 以下时（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcDefenseAdd",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cNpcHunterMusicSkillConductor",
        "checkCondition",
        f"{GAME_VERSION} 全量求值 190 种情形（路径：完成 10、指令超限 2）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
