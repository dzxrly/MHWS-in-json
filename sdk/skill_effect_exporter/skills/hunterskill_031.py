"""HunterSkill_031 纳刀术: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_031"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillWpOffMotionSpeedRate": {
        "效果": "收刀动作速度倍率",
        "作用于": "收刀动作的动作速度",
        "计算": "设为该值（SkillData 槽 0 × 0.01）",
        "条件": "收刀动作中",
        "单位": "倍",
        "依据": "cWpOff.doUpdate、cWpMoveOff.doUpdate",
    },
    "getSkillWpOffIaiMotionSpeedRate": {
        "效果": "居合收刀动作速度倍率",
        "作用于": "居合收刀动作的动作速度",
        "计算": "设为该值",
        "条件": "居合收刀动作中",
        "单位": "倍",
        "依据": "cIaiWpOff.doUpdate",
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
