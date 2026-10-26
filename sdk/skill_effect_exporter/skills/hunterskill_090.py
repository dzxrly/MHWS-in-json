"""HunterSkill_090 地质学: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_090"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillGeology_AddBone": {
        "效果": "骸骨采集点道具额外取得数",
        "作用于": "骸骨采集点道具的取得数",
        "计算": "加算",
        "条件": "采集时",
        "单位": "个",
    },
    "getSkillGeology_AddTokusan": {
        "效果": "特产采集点道具额外取得数",
        "作用于": "特产采集点道具的取得数",
        "计算": "加算",
        "条件": "采集时",
        "单位": "个",
    },
    "getSkillGeology_AddCrystal": {
        "效果": "矿石采掘点道具额外取得数",
        "作用于": "矿石采掘点道具的取得数",
        "计算": "加算",
        "条件": "采集时",
        "单位": "个",
        "依据": "cHunterStatus.getItemPopAddValue",
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
