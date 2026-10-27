"""HunterSkill_022 集中: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_022"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillConcentrationChargeTimeRate": {
        "效果": "蓄力时间倍率",
        "作用于": "蓄力所需时间",
        "计算": "乘算；蓄力类动作的动作速度设为 1 ÷ 本倍率",
        "条件": "蓄力动作中",
        "单位": "倍",
        "依据": "cSuperChargeStartToLoop.doUpdate、cSuperChargeMove.doUpdate、cHunterWp00Handling.get_ChargeTimeRate",
    },
    "getSkillConcentrationChargeTimeSpeedRate": {
        "效果": "蓄力速度倍率",
        "作用于": "蓄力类动作的动作速度",
        "计算": "乘算（即蓄力时间倍率的倒数）",
        "条件": "蓄力动作中",
        "单位": "倍",
        "依据": "cSuperChargeStartToLoop.doUpdate、cHunterWp00Handling.get_ChargeTimeRate",
    },
    "getSkillConcentrationGaugeUpRate": {
        "效果": "武器槽上升倍率",
        "作用于": "武器特有槽的增加量（如重弩能量、轻弩槽、斩击斧觉醒槽）",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "槽增加时",
        "单位": "倍",
        "依据": "cHunterWp12Handling.addEnergy、cHunterWp13Handling.get__SkillConcentrationGaugeUpRate、cHunterWp08Handling.getAwakeRate",
    },
    "getSkillConcentrationWp03KijinChargeMotionSpeedRate": {
        "效果": "太刀气刃蓄力动作速度倍率",
        "作用于": "太刀气刃蓄力动作的动作速度",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterWp13Handling",
        "doOnHit_AttackPre",
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 612 种等级/参数情形（路径记录：完成 67）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
