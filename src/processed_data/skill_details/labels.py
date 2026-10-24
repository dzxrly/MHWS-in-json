"""Chinese labels for the simplified effect sheet.

Effect names are built from the getter's method name: the words are split, the
known ones translated through WORDS, and the skill's own codename words (which
the sheet already shows as the skill name) dropped through SKILL_WORDS. Words in
neither table are kept as they are so a missing translation stays visible.
EFFECT_NAMES overrides names the word-by-word reading gets wrong.
"""

import re

WEAPONS = {
    "LONG_SWORD": "大剑",
    "SHORT_SWORD": "单手剑",
    "TWIN_SWORD": "双刀",
    "TACHI": "太刀",
    "HAMMER": "大锤",
    "WHISTLE": "狩猎笛",
    "LANCE": "长枪",
    "GUN_LANCE": "铳枪",
    "SLASH_AXE": "斩击斧",
    "CHARGE_AXE": "盾斧",
    "ROD": "操虫棍",
    "BOW": "弓",
    "HEAVY_BOWGUN": "重弩",
    "LIGHT_BOWGUN": "轻弩",
}
# Weapon number in data and method names (Wp00..Wp13) to the weapon type label.
WEAPON_CODES = {f"Wp{i:02d}": name for i, name in enumerate(WEAPONS)}

DIMENSION_NAMES = {
    "武器": "武器",
    "TYPE": "武器",
    "SHELL_TYPE": "弹种",
    "弹种": "弹种",
    "BALLISTIC_ARROW_TYPE": "射击",
    "DODGE_TYPE": "回避动作",
    "KIREAJI_TYPE": "斩味",
}
# Keyed by the dimension names above.
ENUMS = {
    "武器": WEAPONS,
    "弹种": {
        "NORMAL": "通常弹",
        "PENETRATE": "贯穿弹",
        "SHOT_GUN": "散弹",
        "GRENADE": "榴弹",
        "MORTAR": "扩散弹",
        "SLASH": "斩裂弹",
        "RYUUGEKI": "龙击弹",
        "FIRE": "火炎弹",
        "WATER": "水冷弹",
        "ELEC": "电击弹",
        "ICE": "冰结弹",
        "DRAGON": "灭龙弹",
        "POISON": "毒弹",
        "PARALYSE": "麻痹弹",
        "SLEEP": "睡眠弹",
        "STAMINA": "减气弹",
        "HEAL": "回复弹",
        "KIJIN": "鬼人弹",
        "KOUKA": "硬化弹",
        "CAPTURE": "捕获用麻醉弹",
        "SET_BOMB": "设置炸弹",
    },
    "射击": {"NORMAL": "通常射击"},
    "回避动作": {
        "NORMAL": "翻滚",
        "STEP": "垫步",
        "WP01_BACK_STEP": "后跳",
        "WP02_JUST_DODGE": "精准回避",
        "WP02_KIJIN_DODGE": "鬼人化回避",
        "WP03_MIKIRI": "见切",
        "WP04_CHARGE_DODGE": "蓄力中回避",
        "WP10_AIR_DODGE": "空中回避",
        "WP10_JUMP_BACK": "后跳",
        "WP11_CHARGE_STEP": "蓄力垫步",
        "WP12_DODGE": "回避",
        "WP13_SLIDING": "滑步",
    },
    "斩味": {
        "RED": "红",
        "ORANGE": "橙",
        "YELLOW": "黄",
        "GREEN": "绿",
        "BLUE": "青",
        "WHITE": "白",
        "PURPLE": "紫",
    },
}
WORDS = {
    "Attack": "攻击力",
    "Attackate": "攻击力倍率",
    "Attr": "属性",
    "Elem": "属性",
    "Element": "属性",
    "Cond": "异常",
    "Critical": "会心率",
    "Crirical": "会心率",
    "Critiical": "会心率",
    "Defense": "防御力",
    "Defensek": "防御力",
    "Add": "加算",
    "Rate": "倍率",
    "Percent": "概率",
    "Value": "数值",
    "Time": "时间",
    "Timer": "时间",
    "Sec": "秒数",
    "Duration": "持续",
    "Active": "发动",
    "Max": "最大",
    "Min": "最小",
    "Count": "次数",
    "Stamina": "耐力",
    "Stamita": "耐力",
    "Heal": "回复",
    "Health": "体力",
    "Red": "红色",
    "Speed": "速度",
    "Motion": "动作",
    "Mot": "动作",
    "Stun": "眩晕",
    "Stan": "眩晕",
    "Stunadd": "眩晕值加算",
    "Damage": "伤害",
    "Fire": "火",
    "Water": "水",
    "Elec": "雷",
    "Thunder": "雷",
    "Ice": "冰",
    "Dragon": "龙",
    "Poison": "毒",
    "Paralyse": "麻痹",
    "Paralysis": "麻痹",
    "Sleep": "睡眠",
    "Blast": "爆破",
    "Bleed": "出血",
    "Resistance": "耐性",
    "Gauge": "槽",
    "Up": "提升",
    "Charge": "蓄力",
    "Reload": "装填",
    "Normal": "通常弹",
    "Penetrate": "贯穿弹",
    "ShotGun": "散弹",
    "Rapid": "速射",
    "Special": "特殊射击",
    "Grenade": "榴弹",
    "Ryuugeki": "龙击炮",
    "Kijin": "气刃",
    "Iai": "居合",
    "Begin": "起点",
    "End": "终点",
    "Wide": "范围",
    "Hit": "命中",
    "Scar": "伤口",
    "Parts": "部位",
    "Weak": "弱点",
    "Far": "远距离",
    "Near": "近距离",
    "Cool": "冷却",
    "CD": "冷却",
    "Interval": "间隔",
    "Radius": "半径",
    "Effective": "效果",
    "Item": "道具",
    "Use": "使用",
    "Buff": "增益",
    "Bless": "加护",
    "Guard": "防御",
    "Power": "",
    "Hate": "仇恨",
    "Dodge": "回避",
    "Dist": "距离",
    "Sight": "视野",
    "Feel": "察觉",
    "Lost": "丢失",
    "Crouch": "蹲伏",
    "Bone": "骨",
    "Crystal": "矿石",
    "Tokusan": "特产",
    "Grass": "草",
    "Insect": "虫",
    "Mushroom": "蘑菇",
    "Seed": "种子",
    "Cable": "钩索",
    "Egg": "搬蛋",
    "Move": "移动",
    "Trans": "移动",
    "Burn": "烤焦",
    "Input": "输入",
    "Kireaji": "锋利度",
    "Sharp": "锋利度",
    "Level": "等级",
    "Lv": "等级",
    "To": "对",
    "Pl": "玩家",
    "Npc": "NPC",
    "Ride": "骑乘",
    "Off": "收刀",
    "Transform": "变形",
    "Emote": "动作",
    "Energy": "能量",
    "Explosion": "爆炸",
    "Accumulation": "累积",
    "Stealth": "隐身",
    "Otomo": "随从",
    "Hunger": "饥饿",
    "Boost": "强化",
    "Running": "跑动",
    "Take": "受到",
    "High": "高速",
    "Enable": "可防御",
    "Last": "最后",
    "Variable": "可变",
}
# Codename words of the skills themselves; the sheet already names the skill.
SKILL_WORDS = {*"""Acc Area Armor Art Artillery Assault Autumn Awake Bacteria Ballistic
    Barbarian Batto Battle Behind Blade Blood Bomb Botany Break Bubble Challenger
    Climber Collection Come Concentration Continuous Convert Cooperation Corn
    Counter Dark Diligent Disaster Discharge Diversion Donki Down Ear Eexplorer
    Environment Event Ex En First Flash Fortitude Full Game Geology Grill Guardian
    Gunner Guts Hien Hiding Honey Hue Hunki Hunter Hyper Infect Intimidation
    Joy Just Katsu Kaziba King KO Kire Knight Konshin Kyoryu Life Lower Luck
    Maintenance Mantle Manzoku Martial Master Meat Morale Muga Muscleman Music No
    Offensive Option Over Plug Prolonge Quake Rebellion Recover Reinforce
    Resentment Resist Resonance Restraint Roast Runner Ryuki Ryunyu Scorching
    Shield Shingan Skill Sliding Spring Stabbing Storage Strengthening Summer
    Super Takumi Technical Timing Toishi Tough Upper Used Violent Wave Waza
    Wazamono Wind Winter Wp Yell Auto Ability Shot Ammo Heat""".split()}

# Method name (without the trailing metadata number) -> effect name.
EFFECT_NAMES = {
    "getSkillAttackAdd": "攻击力加算",
    "getSkillAttackRate": "攻击力倍率",
    "getSkillCriticalAdd": "会心率加算",
    "getSkillDefenseAdd": "防御力加算",
    "getSkillDefenseRate": "防御力倍率",
    "getSkillDefenseAttrAdd": "全属性耐性加算",
    "getSkillGunnerAmmo_Special": "特殊射击倍率",
    "getSkillBallisticBeginWideRate_Bow": "最佳距离起点倍率",
    "getSkillBallisticBeginWideRate_Gun": "最佳距离起点倍率",
    "getSkillBallisticEndWideRate_Bow": "最佳距离终点倍率",
    "getSkillBallisticEndWideRate_Gun": "最佳距离终点倍率",
    "getSkillSuperCriticalAttackRate": "会心伤害倍率",
    "getSkillAttrCriticalRate": "属性会心伤害倍率",
    "getSkillElementCriticalRate": "属性会心伤害倍率",
    "getSkillWazamonoPercent": "会心时不消耗锋利度概率",
    "getSkillCriticalNoKireRunning": "会心时不消耗锋利度（随机判定）",
    "getSkillShinganPercent": "发动概率",
    "getSkillDodgeNoHitLv": "回避无敌等级",
    "getDodgeNoHitTime": "回避无敌时间",
    "getDodgeDistRate": "回避距离倍率",
    "calcContinuousAttackAddAttack": "攻击力加算",
    "calcContinuousAttackAddElem": "属性值加算",
    "getSkillResistQuake_L": "防震（大震动）",
    "getSkillResistQuake_S": "防震（小震动）",
    "getSkillResistQuake_SS": "防震（微震动）",
    "getSkillResistWind_Dragon": "风压耐性（龙风压）",
    "getSkillResistWind_L": "风压耐性（大风压）",
    "getSkillResistWind_S": "风压耐性（小风压）",
    "getSkillEarPlugRate_L": "听觉保护（大咆哮）倍率",
    "getSkillEarPlugRate_S": "听觉保护（小咆哮）倍率",
    "getSkillHoneyHunter_Add_Max": "额外获得数量上限",
    "getSkillHoneyHunter_Add_Min": "额外获得数量下限",
    "getSkillDiligentAttack_5_Add": "攻击力加算（5 次）",
    "getSkillDiligentAttack_10_Add": "攻击力加算（10 次）",
    "getSkillDiligentAttack_20_Add": "攻击力加算（20 次）",
    "getSkillDiligentAttack_30_Add": "攻击力加算（30 次）",
    "getSkillDiligentDefense_5_Add": "防御力加算（5 次）",
    "getSkillDiligentDefense_10_Add": "防御力加算（10 次）",
    "getSkillDiligentDefense_20_Add": "防御力加算（20 次）",
    "getSkillDiligentDefense_30_Add": "防御力加算（30 次）",
    "getSkillSuperGuts_NoUsedAttackRate": "未触发时攻击力倍率",
    "getSkillSuperGuts_NoUsedDefenseRate": "未触发时防御力倍率",
    "getSkillSuperGuts_UsedAttrAdd": "触发后属性耐性加算",
    "getSkillSuperGuts_UsedDefenseRate": "触发后防御力倍率",
    "getSkillManzokuNoUseRate": "不消耗概率",
    "getSkillHunterLifeMeatGrillMusicGameJustTiming": "烤肉判定时机",
    "getSkillHunterLifeMeatGrillMusicGameInputCD": "烤肉输入冷却",
    "getSkillHunterLifeMeatGrillBurnTime": "烤焦时间",
    "isSkillReloadUpAddAmmo": "额外装填一发",
    "getSkillReloadUpMotionSpeed": "装填动作速度",
    "getSkillGuardPowerDamageRateEnableGuard": "可防御攻击的伤害倍率",
    "getskillGuardAbility_MaxGuardPowerAdd": "最大防御性能加算",
    "getSkillGuardAbility_GuardPowerAdd": "防御性能加算",
    "getSkillGuardPowerDamageRate": "防御时伤害倍率",
}


# Weapon words that narrow an effect; shown as a trailing "（弓）".
QUALIFIERS = {
    "BowGun": "弩炮",
    "Bow": "弓",
    "Gun": "弩炮",
    "Light": "轻弩",
    "Heavy": "重弩",
}
ELEMENTS = ("火", "水", "雷", "冰", "龙")
AILMENTS = ("毒", "麻痹", "睡眠", "爆破")
PHRASES = [
    *((f"{e}攻击力", f"{e}属性值") for e in ELEMENTS),
    *((f"{a}攻击力", f"{a}异常值") for a in AILMENTS),
    *((f"{e}耐性属性加算", f"{e}属性耐性加算") for e in ELEMENTS),
    *((f"{e}耐性防御力加算", "防御力加算") for e in ELEMENTS),
    ("耐性最大时间倍率", "持续时间倍率"),
    ("最大时间倍率", "持续时间倍率"),
    ("加算伤害", "追加伤害"),
    ("耐力受到倍率", "耐力消耗倍率"),
    ("红色体力速度倍率", "红色体力回复速度倍率"),
]
EFFECT_NAMES |= {
    "getSkill218AttackRate_Bow": "攻击力倍率（弓）",
    "getSkill218AttackRate_Gun": "攻击力倍率（弩炮）",
    "getSkillArtilleryAttackAddRateWp07Shot": "铳枪炮击攻击力倍率",
    "getSkillArtilleryFireAttackAddWp07Shot": "铳枪炮击火属性加算",
    "getSkillArtilleryAttackRateWp09Grenade": "盾斧榴弹瓶攻击力倍率",
    "getSkillArtilleryWp07RyuugekiTimerRate": "铳枪龙击炮冷却时间倍率",
    "getSkillAutoRecoverIntervalTime": "自动回复间隔时间",
    "getSkillLowerIntimidationRate": "倍率（Lower）",
    "getSkillUpperIntimidationRate": "倍率（Upper）",
    "getSkillAttrResistanceMaxTimeRate": "属性异常持续时间倍率",
    "getSkillDefenseDownResistanceMaxTimeRate": "防御力降低持续时间倍率",
    "getSkillEexplorerLuck_AddRate": "额外报酬倍率",
    "getSkillBloodJoyAdd": "数值加算",
    "getSkillBubbleToishiCriticalAdd_Bubble": "会心率加算（泡沫）",
    "getSkillBubbleToishiCriticalAdd_Water": "会心率加算（水）",
    "getSkillChallengerAttrAttrAdd": "属性值加算",
    "getSkillContinuousAttackReinforceTimeAdd": "持续时间加算",
    "getSkillCounterAttack_ActiveTime": "发动时间",
    "getSkillDischargeCriticalTime": "会心率提升持续时间",
    "getSkillElecStorageTimeAdd": "持续时间加算",
    "getSkillGunnerAmmo_Rapid_LightEnVariableLastShotRate": "速射最后一发倍率（轻弩）",
    "getSkillHeavyArmorBlessRate": "加护倍率",
    "getSkillMantleStrengtheningDefenseAttrAdd": "属性耐性加算",
    "getSkillOtomoPowerUpAttackRate": "随从攻击力倍率",
    "getSkillOtomoPowerUpDefensekRate": "随从防御力倍率",
    "getSkillPowerProlongeTimeRate": "强化状态持续时间倍率",
    "getSkillPowerProlongeExEmote00TimeRate": "强化状态持续时间倍率（ExEmote00）",
    "getSkillPowerProlongeDarkBladeTimeRate": "强化状态持续时间倍率（DarkBlade）",
    "getSkillRestraintResistanceRate": "束缚耐性倍率",
    "getSkillRoastCorn_FireAdd": "火属性值加算",
    "getSkillToishiBoostDurationTime": "强化持续时间",
    "getSkillToishiHighSpeedCount": "快速磨刀次数",
    "getSkillWeakAttackHitCriticalAdd": "弱点命中会心率加算",
    "getSkillWeakAttackScarHitCriticalAdd": "伤口命中会心率加算",
}


def effect_name(method: str) -> str:
    method = re.sub(r"\d+$", "", method)
    if method in EFFECT_NAMES:
        return EFFECT_NAMES[method]
    body = re.sub(r"^(getSkill|getskill|isSkill|get|calc)", "", method)
    body = body.replace("ShotGun", "_ShotGun_").replace("BowGun", "_BowGun_")
    words = []
    for part in body.split("_"):
        if part in WORDS or part in QUALIFIERS or re.fullmatch(r"Wp\d\d", part):
            words.append(part)
            continue
        words += re.findall(r"Wp\d\d|[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+", part)
    text, suffix = [], []
    for i, word in enumerate(words):
        if word in WEAPON_CODES:
            text.append(WEAPONS[WEAPON_CODES[word]])
        elif word in QUALIFIERS:
            suffix.append(QUALIFIERS[word])
        elif word == "To" and i + 1 < len(words):
            suffix.append("对" + WORDS.get(words[i + 1], words[i + 1]))
        elif i and words[i - 1] == "To":
            continue
        elif word in WORDS:
            text.append(WORDS[word])
        elif word not in SKILL_WORDS and not word.isdigit():
            text.append(word)
    label = "".join(dict.fromkeys(t for t in text if t)) or "数值"
    for old, new in PHRASES:
        label = label.replace(old, new)
    if label.startswith("加算") and len(label) > 2:
        label = label[2:] + "额外数量"
    if suffix:
        label += "（" + "、".join(dict.fromkeys(suffix)) + "）"
    return label


def enum_label(dimension: str, value: str) -> str:
    return ENUMS.get(dimension, {}).get(value, value)
