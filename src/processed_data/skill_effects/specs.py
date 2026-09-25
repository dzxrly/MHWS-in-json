"""Audited skill value slots and their damage calculation stages.

Only entries here are numeric effects consumed by the calculator. Other skills
remain in the exported catalog with their source values and an explicit audit
status. Trigger conditions and durations are intentionally outside this schema.
"""

from __future__ import annotations


WEAPONS = (
    "greatsword", "swordshield", "dualblades", "longsword", "hammer",
    "huntinghorn", "lance", "gunlance", "switchaxe", "chargeblade",
    "insectglaive", "bow", "heavybowgun", "lightbowgun",
)
MELEE_WEAPONS = WEAPONS[:11]
RANGED_WEAPONS = WEAPONS[11:]
ELEMENTS = {
    "HunterSkill_005": "fire",
    "HunterSkill_006": "water",
    "HunterSkill_007": "ice",
    "HunterSkill_008": "thunder",
    "HunterSkill_009": "dragon",
}

# stage, source slot, conversion. A percent slot is a rate with 100 == 1.0.
SLOT_EFFECTS: dict[str, tuple[tuple[str, int, str], ...]] = {
    "HunterSkill_000": (("attack.stat.rate", 0, "percent"), ("attack.stat.flat", 1, "number")),
    "HunterSkill_002": (("physical.critical.rate", 0, "percent"),),
    "HunterSkill_018": (("attack.hit.rate", 1, "percent"),),
    "HunterSkill_020": (("attack.hit.rate", 0, "percent"),),
    "HunterSkill_028": (("attack.stat.rate", 0, "percent"),),
    "HunterSkill_047": (("attack.hit.rate", 1, "percent"),),
    "HunterSkill_048": (("element.stat.rate", 0, "percent"),),
    "HunterSkill_055": (("attack.hit.rate", 0, "percent"),),
    "HunterSkill_057": (("attack.hit.rate", 1, "percent"),),
    "HunterSkill_058": (("attack.stat.flat", 0, "number"),),
    "HunterSkill_059": (("attack.stat.flat", 0, "number"),),
    "HunterSkill_060": (("attack.stat.flat", 0, "number"),),
    "HunterSkill_091": (("part.rate", 0, "percent"),),
    "HunterSkill_100": (("attack.stat.rate", 0, "percent"),),
    "HunterSkill_110": (("attack.stat.flat", 0, "number"),),
    "HunterSkill_111": (("attack.hit.flat", 0, "number"),),
    "HunterSkill_113": (("element.stat.rate", 0, "percent"),),
    "HunterSkill_115": (("attack.stat.flat", 0, "number"),),
    "HunterSkill_116": (("attack.stat.rate", 0, "percent"),),
}
for _skill_id in ELEMENTS:
    SLOT_EFFECTS[_skill_id] = (
        ("element.stat.rate", 0, "percent"),
        ("element.stat.flat", 1, "number"),
    )

# There is source data or a native getter, but the identity, indexing, or final
# damage consumer is not sufficiently closed to publish a numeric formula.
PARAMETER_CANDIDATES: dict[str, tuple[str, ...]] = {
    "HunterSkill_030": ("PlayerSkillParam._BattoPowerData",),
    "HunterSkill_095": ("PlayerSkillParam._BombMasterData",),
    "HunterSkill_145": ("PlayerSkillParam._Diligent_ActiveAttackParam",),
    "HunterSkill_190": ("PlayerSkillParam._ElementConvertWp00Data..Wp13Data",),
    "HunterSkill_191": ("SkillData._value",),
    "HunterSkill_204": ("PlayerSkillParam._ViolentData: identity unconfirmed",),
    "HunterSkill_212": ("PlayerSkillParam._DischargeData: identity unconfirmed",),
    "HunterSkill_214": ("PlayerSkillParam._SkillAttrConvertElec_*: identity unconfirmed",),
    "HunterSkill_230": ("PlayerSkillParam._RoastCorn_*: identity unconfirmed",),
    "HunterSkill_233": ("PlayerSkillParam._DarkBladeData: identity unconfirmed",),
    "HunterSkill_237": ("PlayerSkillParam._ResonanceData: identity unconfirmed",),
    "HunterSkill_239": ("PlayerSkillParam._ChallengerAttr_*: identity unconfirmed",),
    "HunterSkill_243": ("PlayerSkillParam._SkillAttrConvertWater_*: identity unconfirmed",),
    "HunterSkill_244": ("Wp00GlobalActionParam._DarkWaveShellExAttack/_DarkWaveShellExAttr: identity unconfirmed",),
}

PENDING_DAMAGE_IDS = frozenset({
    "HunterSkill_035", "HunterSkill_037", "HunterSkill_045", "HunterSkill_146", "HunterSkill_168",
    "HunterSkill_170", "HunterSkill_171", "HunterSkill_175", "HunterSkill_178",
    "HunterSkill_179", "HunterSkill_180", "HunterSkill_182", "HunterSkill_183",
    "HunterSkill_186", "HunterSkill_188", "HunterSkill_197", "HunterSkill_198",
    "HunterSkill_207", "HunterSkill_209", "HunterSkill_211",
    "HunterSkill_215", "HunterSkill_221", "HunterSkill_223", "HunterSkill_225",
    "HunterSkill_229", "HunterSkill_231", "HunterSkill_236",
})
