"""HunterSkill_218 刃鳞增装: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_218"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkill218AttackRate_Gun": {
        "效果": "攻击力倍率（弩炮）",
        "作用于": "攻击力",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
    },
    "getSkill218AttackRate_Bow": {
        "效果": "攻击力倍率（弓）",
        "作用于": "攻击力",
        "计算": "乘算",
        "条件": "调用处未追踪到",
        "单位": "倍",
    },
    "beginSkill217or→cHunterWpGunHandling.<Skill218AdditionalShellMaxNum>k__BackingField：_Skill218or217AddDataPack": {
        "效果": "追加弹数上限",
        "作用于": "弩炮状态 Skill218AdditionalShellMaxNum",
        "计算": "设为该值（按武器取不同数据）",
        "条件": "技能效果开始时",
        "单位": "发",
        "依据": "cHunterWpGunHandling.beginSkill217or218",
    },
    "beginSkill217or→cHunterWpGunHandling._Skill218or217Timer：_Skill217or218_MaxTime": {
        "效果": "效果持续时间",
        "作用于": "弩炮状态 _Skill218or217Timer",
        "计算": "设为该值",
        "条件": "技能效果开始时",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterWpGunHandling.beginSkill217or218",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterWpGunHandling",
        "doOnHit_AttackPre",
        f"{GAME_VERSION} 全量求值 208 种情形（路径：完成 59、空引用 1、未列出 1）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
