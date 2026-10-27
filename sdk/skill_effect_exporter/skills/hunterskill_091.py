"""HunterSkill_091 破坏王: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_091"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBreakKingPartsAttackRate": {
        "效果": "部位破坏积蓄倍率",
        "作用于": "怪物部位破坏的伤害积蓄",
        "计算": "乘算（大于 1 时生效）",
        "条件": "攻击大型怪物部位时",
        "单位": "倍",
        "依据": "cEnemyStockDamage.calcDamageRate_Pl",
    },
    "getSkillBreakKingScarAttackRate": {
        "效果": "破坏伤口伤害倍率",
        "作用于": "破坏伤口时造成的伤害",
        "计算": "乘算；弩炮写入发射的弹丸 BreakKingRate",
        "条件": "集中弱点攻击破坏伤口时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterWeaponHandlingBase.calcScarBreakDamageRateExEmote、cHunterWpGunHandling.setupShellPlGun",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterWpGunHandling",
        "onCreateShotGunShell",
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 60 种等级/参数情形（路径记录：完成 380）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
    (
        "app.cHunterWpGunHandling",
        "shootShell",
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 74 种等级/参数情形（路径记录：完成 5）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
