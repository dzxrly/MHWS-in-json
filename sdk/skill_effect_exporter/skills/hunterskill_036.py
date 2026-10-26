"""HunterSkill_036 炮弹装填: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_036"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillReloadUpMotionSpeed": {
        "效果": "装填动作速度倍率",
        "作用于": "装填（充能）动作的动作速度",
        "计算": "乘算（SkillData 槽 0 × 0.01）",
        "条件": "铳枪装填、盾斧充能动作开始时",
        "单位": "倍",
        "依据": "cSwordEnergyCharge.doEnter、cSwordEnergyChargeFail.doEnter",
    },
    "isSkillReloadUpAddAmmo": {
        "效果": "装填数 +1",
        "作用于": "铳枪装填数",
        "计算": "为“是”时装填数 +1",
        "条件": "Lv2 起（游戏说明）",
        "单位": "是/否",
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
