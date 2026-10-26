"""HunterSkill_040 散弹·刚射强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_040"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGunnerAmmo_ShotGun_Rate": {
        "效果": "散弹攻击力倍率",
        "作用于": "命中时攻击数据的攻击力 _Attack",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "弩炮散弹、弓的刚射和迅雷闪击命中时",
        "单位": "倍",
        "依据": "cHunterWp11Handling.doOnHit_AttackPre",
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
