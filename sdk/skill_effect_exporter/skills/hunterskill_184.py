"""HunterSkill_184 护锁刃龙之命脉: extraction steps, meanings of its shown effect values, notes."""

from .. import config

SKILL_ID = "HunterSkill_184"
BREAK_COUNTS = range(1, 6)

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBloodJoyAdd": {
        "效果": "首处伤口基础回复量",
        "作用于": "猎人的体力",
        "计算": "作为首处伤口的基础回复量，已计入各档体力回复量",
        "条件": "破坏大型怪物的伤口时",
        "单位": "点",
        "依据": "cHunterSkill.getSkillBloodJoyAdd → cHunterSkill.calcBloodJoyHeal",
    },
    "calcBloodJoyHeal：PlayerSkillParam._BloodJoyData": {
        "效果": "体力回复量",
        "作用于": "猎人的体力",
        "计算": "按本次结算破坏的伤口数取基础回复量，再乘体力回复量提升的倍率",
        "条件": "破坏大型怪物的伤口时",
        "单位": "点",
        "依据": "HunterCharacter.receiveGameMessage 传入 BreakCount → cHunterSkill.calcBloodJoyHeal → 回复体力",
        "情形": {
            **{f"参数1={count}": f"本次破坏 {count} 处伤口" for count in range(1, 5)},
            "参数1=5": "本次破坏 5 处及以上伤口",
        },
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = [
    f"{config.GAME_VERSION}：装备 2 件发动“破坏冲动Ⅰ”，装备 4 件强化为“破坏冲动Ⅱ”。"
    "按本次结算中该猎人破坏的大型怪物伤口数取回复量，5 处及以上使用同一档。"
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(
        skill_id=SKILL_ID,
        argument_values={
            (config.HUNTER_SKILL, "calcBloodJoyHeal"): {
                0: [(str(count), count) for count in BREAK_COUNTS]
            }
        },
    )


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID)
