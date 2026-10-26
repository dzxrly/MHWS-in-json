"""HunterSkill_004 达人艺: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_004"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillCriticalNoKireRunning": {
        "效果": "会心时不消耗锋利度判定",
        "作用于": "会心攻击时的锋利度消耗",
        "计算": "以 SkillData 槽 0 为百分比概率随机判定；结果为“是”时本次不消耗",
        "条件": "会心攻击时",
        "单位": "是/否",
        "依据": "cHunterSkill.checkSkillReduceKireaji",
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
