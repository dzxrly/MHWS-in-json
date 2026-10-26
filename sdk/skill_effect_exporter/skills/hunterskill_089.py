"""HunterSkill_089 植生学: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_089"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBotany_AddGrass": {
        "效果": "草系消耗道具额外取得数",
        "作用于": "草系消耗道具的取得数",
        "计算": "加算",
        "条件": "采集时",
        "单位": "个",
    },
    "getSkillBotany_AddSeed": {
        "效果": "果实、种子系消耗道具额外取得数",
        "作用于": "果实、种子系消耗道具的取得数",
        "计算": "加算",
        "条件": "采集时",
        "单位": "个",
    },
    "getSkillBotany_AddInsect": {
        "效果": "虫系消耗道具额外取得数",
        "作用于": "虫系消耗道具的取得数",
        "计算": "加算",
        "条件": "采集时",
        "单位": "个",
    },
    "getSkillBotany_AddMushroom": {
        "效果": "菇系消耗道具额外取得数",
        "作用于": "菇系消耗道具的取得数",
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
