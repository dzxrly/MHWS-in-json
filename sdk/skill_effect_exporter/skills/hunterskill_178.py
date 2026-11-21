"""HunterSkill_178 狱焰蛸之反叛: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_178"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillViolentAddDamage": {
        "效果": "追加伤害基础值",
        "作用于": "攻击时额外造成的伤害",
        "计算": "按上位或下位取基础值，实际追加伤害随命中部位的肉质变化",
        "条件": "“怨恨”技能发动时（游戏说明）",
        "单位": "点",
        "依据": (
            "cHunterSkill.calcSkillAdditionalDamage 按 EnvironmentManager.CurrentRank "
            "向 getSkillViolentAddDamage 传参。下位读 SkillData 槽 0，上位读 _ViolentData。"
            "缺少怪物上下文时也读槽 0。"
        ),
        "情形": {
            "参数1=true": "上位",
            "参数1=false": "下位",
        },
    }
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = [f"{GAME_VERSION}：装备 2 件发动“恨击Ⅰ”，装备 4 件强化为“恨击Ⅱ”。"]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
