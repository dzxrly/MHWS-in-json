"""HunterSkill_055 飞燕: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_055"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillHienAttackRate": {
        "效果": "跳跃攻击攻击力倍率",
        "作用于": "命中时的攻击力",
        "计算": "乘算（SkillData 槽 0 × 0.01），并入命中攻击力倍率",
        "条件": "跳跃攻击命中时",
        "单位": "倍",
        "依据": "cHunterSkill.calcHitAttackRate",
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
        f"{GAME_VERSION} 全量求值 208 种情形（路径：完成 59、空引用 1、未列出 1）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
