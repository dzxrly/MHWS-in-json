"""HunterSkill_219 祭典巡礼: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_219"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = [
    f"{GAME_VERSION}：SkillData 中本技能 3 级打开 HunterSkill_093（剥取名人），但代码 HunterSkillDef.createSkillToGroupSkill 把 HunterSkill_220 映射到本技能，没有 HunterSkill_093 的映射。原生代码读取的是 HunterSkill_220 一侧。"
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
