"""HunterSkill_076 回避距离提升: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_076"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getDodgeDistRate": {
        "效果": "回避距离倍率",
        "作用于": "回避动作的移动距离",
        "计算": "乘算；按回避动作取不同数据（以技能等级为下标）",
        "条件": "回避时",
        "单位": "倍",
        "依据": (
            "cHunterSkill.getDodgeDistRate。双刀 cJustDodgeBase.doEnter 在 _IsFromBuff 分支检查 "
            "isWearActiveMantle(A_SKILL_004)，衣装生效时由 cDodge.doEnter 传入类型 5。"
            "狩猎笛的类型 9 读取 _DodgeDistNormalData，抵消之曲的实际位移是否使用该倍率待核实"
        ),
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
