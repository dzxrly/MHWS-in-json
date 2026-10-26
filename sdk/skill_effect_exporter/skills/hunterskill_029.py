"""HunterSkill_029 拔刀术【技】: extraction steps, meanings of its shown effect values, notes."""

from ..config import GAME_VERSION

SKILL_ID = "HunterSkill_029"

# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.
MEANINGS = {
    "getSkillBattoWazaCritiicalAdd": {
        "效果": "会心率加算",
        "作用于": "会心率",
        "计算": "加算（SkillData 槽 0），并入会心率汇总",
        "条件": "拔刀攻击（游戏说明）",
        "单位": "%",
        "依据": "cHunterSkill.getCalcCriticalAdd",
    },
    "startBttoWaza→_BattoWazaInfo._PreAttackTimer：_BattoWazaData": {
        "效果": "拔刀判定时间",
        "作用于": "技能状态 _BattoWazaInfo._PreAttackTimer",
        "计算": "设为该值",
        "条件": "开始拔刀动作时写入；计时结束前的攻击视为拔刀攻击（推测，未核实）",
        "单位": "时间（游戏内部单位）",
        "依据": "cHunterSkill.startBttoWaza",
    },
}

# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.
NOTES = []


# Functions using this skill that are recorded as links but not evaluated:
# (type, method, the evidence that they give the skill no shown value).
SKIPPED_FUNCTIONS = [
    (
        "app.cHunterSkill",
        "update",
        f"{GAME_VERSION} 全量求值 84 种情形（路径：完成 30）都没有得到来自本技能数据、可在表格显示的数值；只记录链路，不再求值（extract --all-links 时照常求值）",
    ),
]


def extract(context):
    """Links of the functions using this skill and of its accessors' callers."""
    return context.extract_skill(SKILL_ID, SKIPPED_FUNCTIONS)


def extract_parameters(context):
    """Parameter fields no path valued, focused where they are read."""
    return context.extract_parameters(SKILL_ID, SKIPPED_FUNCTIONS)
