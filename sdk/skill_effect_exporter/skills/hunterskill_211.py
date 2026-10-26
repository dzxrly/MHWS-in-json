"""HunterSkill_211 饭团: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_211"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillExEmote00_AttackUpRate": {
        "效果": "豪鬼专用动作攻击力倍率",
        "作用于": "豪鬼专用动作命中时的攻击力倍率",
        "计算": "乘算，与其他命中倍率相乘后不超过 5",
        "条件": "豪鬼专用动作命中时",
        "单位": "倍",
        "依据": "cHunterAttackPower.calcOnHitAttackPower",
    },
    "getSkillExEmote00_StunRate": {
        "效果": "豪鬼专用动作眩晕倍率",
        "作用于": "豪鬼专用动作的眩晕值",
        "计算": "乘算",
        "条件": "豪鬼专用动作命中时（游戏说明）",
        "单位": "倍",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
