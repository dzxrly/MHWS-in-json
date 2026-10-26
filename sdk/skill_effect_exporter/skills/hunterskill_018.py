"""HunterSkill_018 心眼: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_018"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillShingan_AttackRate": {
        "效果": "坚硬部位攻击力倍率",
        "作用于": "命中时的攻击力",
        "计算": "乘算（SkillData 槽 1 × 0.01），并入命中攻击力倍率",
        "条件": "命中部位肉质 ≤ 阈值 _Shingan_MeatThreshold（44）时",
        "单位": "倍",
        "依据": "cHunterSkill.calcHitAttackRate",
    },
    "getSkillShinganPercent": {
        "效果": "不被弹开概率",
        "作用于": "攻击被弹开的判定",
        "计算": "以 SkillData 槽 0 为百分比概率随机判定，成立时不被弹开",
        "条件": "攻击会被弹开时",
        "单位": "%",
        "依据": "Weapon.isAttackRecoilForSkill",
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
