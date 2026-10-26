"""HunterSkill_020 钝器能手: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_020"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDonkiAttackRate": {
        "效果": "低锋利度攻击力倍率",
        "作用于": "命中时的攻击力",
        "计算": "乘算，并入命中攻击力倍率",
        "条件": "锋利度为黄色或以下（Lv3 为绿色或以下）时（游戏说明）",
        "单位": "倍",
        "依据": "cHunterSkill.calcHitAttackRate（按技能等级）",
    }
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
