"""HunterSkill_145 钻研: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_145"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillDiligentAttack_5_Add": {
        "效果": "攻击力加算（5 分钟档）",
        "作用于": "攻击力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
    },
    "getSkillDiligentAttack_10_Add": {
        "效果": "攻击力加算（10 分钟档）",
        "作用于": "攻击力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
    },
    "getSkillDiligentAttack_20_Add": {
        "效果": "攻击力加算（20 分钟档）",
        "作用于": "攻击力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
    },
    "getSkillDiligentAttack_30_Add": {
        "效果": "攻击力加算（30 分钟档）",
        "作用于": "攻击力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
    },
    "getSkillDiligentDefense_5_Add": {
        "效果": "防御力加算（5 分钟档）",
        "作用于": "防御力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
    },
    "getSkillDiligentDefense_10_Add": {
        "效果": "防御力加算（10 分钟档）",
        "作用于": "防御力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
    },
    "getSkillDiligentDefense_20_Add": {
        "效果": "防御力加算（20 分钟档）",
        "作用于": "防御力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
    },
    "getSkillDiligentDefense_30_Add": {
        "效果": "防御力加算（30 分钟档）",
        "作用于": "防御力",
        "计算": "加算，并入汇总",
        "条件": "任务开始后经过的时间达到这一档时（档位推测为分钟：游戏说明称 30 分钟后达到上限）",
        "单位": "点",
        "依据": "cHunterSkill.update、cHunterSkill.calcAttackAdd（按技能等级）",
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
