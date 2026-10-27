from __future__ import annotations

from dataclasses import dataclass

from .models import ShellEntryRecord
from .shells import enum_name

# Request sets that player shell components activate in place of (or beside)
# the ShellList _AttackCollisionID. Every table below is a constant read from
# the named game function; a rule only becomes a relation when its ID exists
# in the entry's own prefab RCOL.


@dataclass(frozen=True, slots=True)
class ShellColliderRule:
    collision_id: int
    marker: str
    method: str
    game_function: str
    conditions: tuple[dict[str, object], ...]


def shell_collider_rules(entry: ShellEntryRecord) -> list[ShellColliderRule]:
    return [
        *_bow_rules(entry),
        *_hunting_horn_rules(entry),
        *_charge_blade_rules(entry),
    ]


# --- Bow: app.mcShellPlWp11Arrow keeps the ShellList ID in _ColliderIndex
# (onSetup) and swaps colliders through _OverwriteColliderIndex.

BOW_ARROW_PARAM = "app.cShellminiParamPlWp11Arrow"

# applyBottle: BottleType PENETRATE sets _OverwriteColliderIndex to
# 0x190 + _ColliderIndex unless ArrowType is SPECIAL/SPECIAL_SHORT or the
# arrow level is HOMING.
PENETRATE_BOTTLE_OFFSET = 400
PENETRATE_EXCLUDED_ARROW_TYPES = frozenset({"SPECIAL", "SPECIAL_SHORT"})
HOMING_ARROW_LEVEL = "HOMING"

# setTsugiyaHoming: a non-penetrating Tsugiya homing arrow switches to the
# single-hit collider selected by ArrowType.
TSUGIYA_HOMING_SINGLE_HIT = {
    "NORMAL": 201,
    "QUICK_SHOT": 213,
    "GOSHA": 203,
    "GOSHA_RAPID": 205,
    "JUMP": 214,
    "TWIN": 207,
    "DASH_CLIMB": 212,
}

# getTsugiyaHomingSingleHitColliderIndex(true), and the inverse table in
# mcShellPlWp11HomingBodyHit.onSetup: the HOMING_BODY_HIT shell hits with
# 500 + n according to the parent arrow's ArrowType.
HOMING_BODY_HIT = {
    "NORMAL": 500,
    "GOSHA": 501,
    "GOSHA_RAPID": 502,
    "TWIN": 503,
    "DASH_CLIMB": 504,
    "QUICK_SHOT": 505,
    "JUMP": 506,
}

# mcShellPlWp11NormalASkill005.getNormalASkill005HitColliderIndex: parent
# arrow CHARGE_LV -> collider (LV4 has none).
NORMAL_ASKILL005_HIT = {"LV1": 600, "LV2": 601, "LV3": 602, "HOMING": 603}

# cHunterWp11Handling.getShootShellIndex shares the GOSHA case for ARROW_TYPE
# JUMP (level entry = Lv + 7, homing entry 12); setupShellArrow then
# overwrites the arrow's ArrowType with JUMP.
JUMP_SHOT_SHELL_ENTRIES = frozenset(
    {"GOSHA_LV1", "GOSHA_LV2", "GOSHA_LV3", "GOSHA_LV4", "GOSHA_HOMING"}
)


def _bow_rules(entry: ShellEntryRecord) -> list[ShellColliderRule]:
    arrow_type = enum_name(entry.mini_param(BOW_ARROW_PARAM, "_ArrowType"))
    arrow_level = enum_name(entry.mini_param(BOW_ARROW_PARAM, "_ArrowLv"))
    if not arrow_type:
        return []
    output: list[ShellColliderRule] = []
    primary = _primary_collision_ids(entry)
    if (
        len(primary) == 1
        and arrow_type not in PENETRATE_EXCLUDED_ARROW_TYPES
        and arrow_level != HOMING_ARROW_LEVEL
    ):
        output.append(
            ShellColliderRule(
                collision_id=primary[0] + PENETRATE_BOTTLE_OFFSET,
                marker="PENETRATE_BOTTLE",
                method="bow_penetrate_bottle_collider",
                game_function="app.mcShellPlWp11Arrow.applyBottle",
                conditions=({"kind": "bow_bottle", "bottleType": "PENETRATE"},),
            )
        )

    arrow_types = [arrow_type]
    if entry.fixed_name in JUMP_SHOT_SHELL_ENTRIES:
        arrow_types.append("JUMP")
    for candidate_type in arrow_types:
        collision_id = TSUGIYA_HOMING_SINGLE_HIT.get(candidate_type)
        if collision_id is None:
            continue
        overridden = candidate_type != arrow_type
        conditions: tuple[dict[str, object], ...] = (
            {"kind": "bow_tsugiya_homing", "penetrate": False},
        )
        if overridden:
            conditions += (
                {"kind": "bow_arrow_type_override", "arrowType": candidate_type},
            )
        output.append(
            ShellColliderRule(
                collision_id=collision_id,
                marker=(
                    f"{candidate_type}_TSUGIYA_HOMING_SINGLE_HIT"
                    if overridden
                    else "TSUGIYA_HOMING_SINGLE_HIT"
                ),
                method="bow_tsugiya_homing_single_hit_collider",
                game_function="app.mcShellPlWp11Arrow.setTsugiyaHoming",
                conditions=conditions,
            )
        )

    if arrow_type == "HOMING_BODY_HIT":
        output.extend(
            ShellColliderRule(
                collision_id=collision_id,
                marker=parent_type,
                method="bow_homing_body_hit_collider",
                game_function=(
                    "app.mcShellPlWp11Arrow.getTsugiyaHomingSingleHitColliderIndex"
                ),
                conditions=(
                    {"kind": "bow_homing_body_hit", "parentArrowType": parent_type},
                ),
            )
            for parent_type, collision_id in HOMING_BODY_HIT.items()
        )
    if arrow_type == "NORMAL_ASKILL005":
        output.extend(
            ShellColliderRule(
                collision_id=collision_id,
                marker=level,
                method="bow_normal_askill005_collider",
                game_function=(
                    "app.mcShellPlWp11NormalASkill005."
                    "getNormalASkill005HitColliderIndex"
                ),
                conditions=(
                    {"kind": "bow_normal_askill005", "parentArrowLevel": level},
                ),
            )
            for level, collision_id in NORMAL_ASKILL005_HIT.items()
        )
    return output


# --- Hunting Horn.

HORN_PARAM = "app.cShellminiParamPlWp05"

# app.Wp05Def.WP05_MUSIC_SKILL_HIGH_FREQ_TYPE 1..11 and MULTI_MUSIC_LEVEL;
# mcShellPlWp05HighFreq.getRequestID returns 100 + 3 * (type - 1) + level.
HIGH_FREQ_TYPES = (
    "HIGH_FREQ_BLOW",
    "HIGH_FREQ_SLASH",
    "HIGH_FREQ_ELEM_FIRE",
    "HIGH_FREQ_ELEM_WATER",
    "HIGH_FREQ_ELEM_ELEC",
    "HIGH_FREQ_ELEM_ICE",
    "HIGH_FREQ_ELEM_DRAGON",
    "HIGH_FREQ_ELEM_POISON",
    "HIGH_FREQ_ELEM_PARALYZE",
    "HIGH_FREQ_ELEM_SLEEP",
    "HIGH_FREQ_ELEM_BLAST",
)
MULTI_MUSIC_LEVELS = ("S", "M", "L")
HIGH_FREQ_REQUEST_BASE = 100

# mcShellPlWp05HibikiDamage.updateDamageShellHitID:
# 7 + 4 * (SHELL_DAMAGE_TYPE != DAMAGE_M).
HIBIKI_DAMAGE_HIT = {"DAMAGE_M": 7, "DAMAGE_S": 11}


def _hunting_horn_rules(entry: ShellEntryRecord) -> list[ShellColliderRule]:
    shell_type = enum_name(entry.mini_param(HORN_PARAM, "_ShellType"))
    if shell_type == "HIGH_FREQ":
        return [
            ShellColliderRule(
                collision_id=HIGH_FREQ_REQUEST_BASE + 3 * type_index + level_index,
                marker=f"{high_freq_type.removeprefix('HIGH_FREQ_')}_{level}",
                method="horn_high_freq_request_set",
                game_function="app.mcShellPlWp05HighFreq.getRequestID",
                conditions=(
                    {
                        "kind": "horn_high_freq",
                        "highFreqType": high_freq_type,
                        "musicLevel": level,
                    },
                ),
            )
            for type_index, high_freq_type in enumerate(HIGH_FREQ_TYPES)
            for level_index, level in enumerate(MULTI_MUSIC_LEVELS)
        ]
    if shell_type == "HIBIKI_DAMAGE":
        return [
            ShellColliderRule(
                collision_id=collision_id,
                marker=damage_type,
                method="horn_hibiki_damage_request_set",
                game_function=("app.mcShellPlWp05HibikiDamage.updateDamageShellHitID"),
                conditions=({"kind": "horn_hibiki_damage", "damageType": damage_type},),
            )
            for damage_type, collision_id in HIBIKI_DAMAGE_HIT.items()
        ]
    return []


# --- Charge Blade: mcShellPlWp09.setOverwriteColliderIndex picks a field of
# cShellminiParamPlWp09 from _BinType (app.Wp09Def.BIN_TYPE: GRENADE 0,
# ELEMENT 1), _IsOverCharged and _IsComboDischarge; IDs <= 0 keep the
# ShellList collider. Grenade without either flag never overwrites.

CHARGE_BLADE_PARAM = "app.cShellminiParamPlWp09"
CHARGE_BLADE_OVERWRITE_FIELDS = (
    ("ELEMENT", False, False, "_AttrColID"),
    ("ELEMENT", True, False, "_OverChargedAttrColID"),
    ("ELEMENT", False, True, "_ComboDischarge_AttrColID"),
    ("ELEMENT", True, True, "_ComboDischarge_OC_AttrColID"),
    ("GRENADE", True, False, "_OverChargedGrenadeColID"),
    ("GRENADE", False, True, "_ComboDischarge_GrenadeColID"),
    ("GRENADE", True, True, "_ComboDischarge_OC_GrenadeColID"),
)


def _charge_blade_rules(entry: ShellEntryRecord) -> list[ShellColliderRule]:
    output: list[ShellColliderRule] = []
    for bin_type, over_charged, combo, field_name in CHARGE_BLADE_OVERWRITE_FIELDS:
        collision_id = entry.mini_param(CHARGE_BLADE_PARAM, field_name)
        if (
            not isinstance(collision_id, int)
            or isinstance(collision_id, bool)
            or collision_id <= 0
        ):
            continue
        marker = "_".join(
            part
            for part, enabled in (
                (f"{bin_type}_PHIAL", True),
                ("OVERCHARGED", over_charged),
                ("COMBO_DISCHARGE", combo),
            )
            if enabled
        )
        output.append(
            ShellColliderRule(
                collision_id=collision_id,
                marker=marker,
                method="charge_blade_overwrite_collider",
                game_function="app.mcShellPlWp09.setOverwriteColliderIndex",
                conditions=(
                    {
                        "kind": "charge_blade_phial",
                        "binType": bin_type,
                        "overCharged": over_charged,
                        "comboDischarge": combo,
                        "sourceField": field_name,
                    },
                ),
            )
        )
    return output


def _primary_collision_ids(entry: ShellEntryRecord) -> list[int]:
    return [
        reference.collision_id
        for reference in entry.collision_references
        if reference.role == "primary"
    ]
