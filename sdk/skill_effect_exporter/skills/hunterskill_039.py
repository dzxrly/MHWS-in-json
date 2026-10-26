"""HunterSkill_039 贯穿弹·龙之箭强化: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_039"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGunnerAmmo_Penetrate_Rate": {
        "效果": "贯穿弹攻击力倍率",
        "作用于": "攻击力",
        "计算": "乘算",
        "条件": "弩炮贯穿弹、弓的龙之箭和龙之千矢命中时（游戏说明）",
        "单位": "倍",
    }
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterWpGunHandling",
        "doOnHit_AttackPre",
        f"{GAME_VERSION} 全量求值 208 种情形（路径：完成 67、空引用 1、未列出 2）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
