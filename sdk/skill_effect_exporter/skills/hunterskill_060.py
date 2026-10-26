"""HunterSkill_060 怨恨: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_060"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillResentmentAttackAdd": {
        "效果": "基础攻击力加算",
        "作用于": "基础攻击力",
        "计算": "加算（SkillData 槽 0），并入攻击力加算汇总",
        "条件": "体力槽有红色部分时（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcAttackAdd",
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
