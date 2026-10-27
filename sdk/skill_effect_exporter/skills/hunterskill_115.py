"""HunterSkill_115 巧击: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_115"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillTechnicalAttack_AttackAdd": {
        "效果": "基础攻击力加算",
        "作用于": "基础攻击力",
        "计算": "加算（SkillData 槽 0），并入攻击力加算汇总",
        "条件": "回避时机与怪物攻击重合后的一定时间内（游戏说明）",
        "单位": "点",
        "依据": "cHunterSkill.calcAttackAdd",
    },
    "beginTechnicalAttack→_TechnicalAttack_Info._Timer：_TechnicalAttack_MaxActiveTime": {
        "效果": "效果持续时间",
        "作用于": "技能状态 _TechnicalAttack_Info._Timer（calcAttackAdd 在它大于 0 时计入效果）",
        "计算": "设为该值（同时写入最大值）",
        "条件": "回避时机与怪物攻击重合时开始计时（游戏说明）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.beginTechnicalAttack",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions of this skill the scan cannot tie to it: (type, method, the
# reviewed evidence), checked against the code of config.GAME_VERSION.
DECLARED_METHODS = [
    (
        "app.cHunterSkill",
        "beginTechnicalAttack",
        "beginTechnicalAttack 操作状态对象 _HunterSkillParamInfo._TechnicalAttack_Info（cHunterSkillParamInfo 构造时写入 _Skill = HunterSkill_115），"
        "把 PlayerSkillParam._TechnicalAttack_MaxActiveTime 写入它的 _Timer 与 _MaxTimer；"
        "经 HunterCharacter.doHitMikiri → cHunterSkill.damageMikiriSuccess 调用，"
        f"但它以立即数读取的只有 HunterSkill_215（千刃龙的斗志）的等级，扫描只把它归到那个技能（{GAME_VERSION}）",
    ),
]


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.HunterCharacter",
        "beginDodgeNoHit",
        f"{GAME_VERSION} --all-links 复核 1 个常规链路范围，结果记录 85 种等级/参数情形（路径记录：完成 3、抛出异常 1）；已记录路径未取得本技能可显示数值，超限与截断等边界继续保留。常规提取只记录链路，--all-links 时照常求值。",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers,
    plus the functions declared above."""
    links = context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)
    for type_name, method, reason in DECLARED_METHODS:
        links += context.extract_method(SKILL_ID, type_name, method, reason)
    return links


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
