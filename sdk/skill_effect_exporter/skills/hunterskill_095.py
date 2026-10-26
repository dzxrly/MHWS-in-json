"""HunterSkill_095 炸弹客: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_095"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBombMaster": {
        "效果": "炸弹威力倍率",
        "作用于": "炸弹等设置物的攻击倍率",
        "计算": "乘算",
        "条件": "炸弹类攻击命中时",
        "单位": "倍",
        "依据": "cHunterStatus.calcFixingAttackRate、GimmickUtil.getAttackRate",
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
