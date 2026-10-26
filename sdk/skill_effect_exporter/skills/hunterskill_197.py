"""HunterSkill_197 强四射击: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_197"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillAssaultShotBowGunAttrRate": {
        "效果": "属性倍率（弩炮）",
        "作用于": "属性值",
        "计算": "乘算",
        "条件": "装填瓶后的第 4、第 6 发射击（游戏说明）；调用处未追踪到",
        "单位": "倍",
    },
    "getSkillAssaultShotBowAttrRate": {
        "效果": "属性倍率（弓）",
        "作用于": "属性值",
        "计算": "乘算",
        "条件": "装填瓶后的第 4、第 6 发射击（游戏说明）；调用处未追踪到",
        "单位": "倍",
    },
    "getSkillAssaultShotBowCriticalAdd": {
        "效果": "会心率加算",
        "作用于": "命中时的会心率",
        "计算": "加算（SkillData 槽 0）",
        "条件": "装填瓶后第 4 发及后续射击（游戏说明）",
        "单位": "%",
        "依据": "cHunterWpGunHandling.getOnHitCriticalRateAdd、cHunterWp11Handling.getOnHitCriticalRateAdd",
    },
    "getSkillAssaultShotBowAttackAdd": {
        "效果": "攻击力加算（弓）",
        "作用于": "命中时的攻击力",
        "计算": "加算（SkillData 槽 1）",
        "条件": "装填瓶后的第 4、第 6 发射击（游戏说明）",
        "单位": "点",
        "依据": "cHunterWp11Handling.getOnHitAttackPowerAdd",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterWp11Handling",
        "setupShellArrow",
        f"{GAME_VERSION} 全量求值 156 种情形（路径：完成 56）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
