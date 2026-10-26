"""HunterSkill_019 弹道强化: extraction steps, meanings of its shown effect values, notes."""

SKILL_ID = "HunterSkill_019"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBallisticBeginWideRate_Gun": {
        "效果": "最佳距离起点倍率",
        "作用于": "弹种参数中的最佳距离起点（弩炮）",
        "计算": "乘算；瞄准距离 < 1.11 × 本倍率 × 起点时判为过近",
        "条件": "弩炮瞄准时",
        "单位": "倍",
        "依据": "cHunterWpGunHandling.updateAimRange",
    },
    "getSkillBallisticEndWideRate_Gun": {
        "效果": "最佳距离终点倍率",
        "作用于": "弹种参数中的最佳距离终点（弩炮）",
        "计算": "乘算；瞄准距离 > 0.9 × 本倍率 × 终点时判为过远",
        "条件": "弩炮瞄准时",
        "单位": "倍",
        "依据": "cHunterWpGunHandling.updateAimRange",
    },
    "getSkillBallisticBeginWideRate_Bow": {
        "效果": "最佳距离起点倍率",
        "作用于": "射击参数中的最佳距离起点（弓）",
        "计算": "乘算；瞄准距离 < 1.11 × 本倍率 × 起点时判为过近",
        "条件": "弓瞄准时",
        "单位": "倍",
        "依据": "cHunterWp11Handling.updateAimRange",
    },
    "getSkillBallisticEndWideRate_Bow": {
        "效果": "最佳距离终点倍率",
        "作用于": "射击参数中的最佳距离终点（弓）",
        "计算": "乘算；瞄准距离 > 0.9 × 本倍率 × 终点时判为过远",
        "条件": "弓瞄准时",
        "单位": "倍",
        "依据": "cHunterWp11Handling.updateAimRange",
    },
    "getOnHitAttackPowerAdd：PlayerSkillParam._Ballistic_Wp12AttackAdd、PlayerSkillParam._Ballistic_Wp13AttackAdd": {
        "效果": "最佳距离命中攻击力加算",
        "作用于": "命中时的攻击力（弩炮）",
        "计算": "加算",
        "条件": "Lv3 起；命中的攻击数据中一个未命名的标志为 1（推测为在最佳距离命中，未核实）",
        "单位": "点",
        "依据": "cHunterWpGunHandling.getOnHitAttackPowerAdd（AttackData+0x150 == 1）",
    },
    "getOnHitAttackPowerAdd：PlayerSkillParam._Ballistic_Wp11AttackAdd": {
        "效果": "最佳距离命中攻击力加算",
        "作用于": "命中时的攻击力（弓）",
        "计算": "加算",
        "条件": "Lv3 起；命中的攻击数据中一个未命名的标志为 1（推测为在最佳距离命中，未核实）",
        "单位": "点",
        "依据": "cHunterWp11Handling.getOnHitAttackPowerAdd（AttackData+0x150 == 1）",
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
