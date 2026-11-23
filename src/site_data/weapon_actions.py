"""The player-facing columns of WeaponActionValues, in workbook order."""

import json
import os
from pathlib import Path

from config import ACTION_MAP_ENV_VAR, ZH_HANS_LANGUAGE_ID
from src.database.action_values.build import SHEET_NAMES, build_action_value_workbook
from src.processed_data.skill_details.labels import ENUMS, WEAPON_CODES, WEAPONS
from src.shared.action_values.catalog import load_action_value_catalog
from src.shared.source.user3 import normalize

OUTPUT_NAME = "weapon_actions/actions.json"
COLLISION_ROLES = {
    "primary": "主判定",
    "sub_collision": "副判定",
    "additional_collision": "附加判定",
}
HORN_EFFECTS = {
    "BLOW": "打击",
    "SLASH": "斩击",
    "ELEM_FIRE": "火",
    "ELEM_WATER": "水",
    "ELEM_ELEC": "雷",
    "ELEM_ICE": "冰",
    "ELEM_DRAGON": "龙",
    "ELEM_BLAST": "爆破",
    "ELEM_POISON": "毒",
    "ELEM_PARALYZE": "麻痹",
    "ELEM_SLEEP": "睡眠",
}
LEVELS = {"S": "小", "M": "中", "L": "大"}
ARROW_TYPES = {
    "DASH_CLIMB": "攀登射击",
    "GOSHA": "刚射",
    "GOSHA_RAPID": "刚连射",
    "JUMP": "跳跃",
    "NORMAL": "通常射击",
    "QUICK_SHOT": "迅雷闪击",
    "TWIN": "龙之千矢",
}
INSECT_ATTACKS = {
    "NORMAL": "通常攻击",
    "NORMAL_MULTI": "通常连续攻击",
    "DIVE": "俯冲",
    "TOGETHER": "协同攻击",
    "TOGETHER_MULTI": "协同连续攻击",
    "FINAL_UPPER": "终结上挑",
    "AIM_ATTACK": "瞄准攻击",
    "AIM_ATTACK_DITECT": "瞄准攻击检测",
    "W_SLASH": "双斩",
}


def _describe_condition(condition):
    kind = condition["kind"]
    if kind == "collision_configuration":
        labels = [COLLISION_ROLES.get(role, role) for role in condition["roles"]]
        if condition["ammoLevel"] is not None:
            labels.insert(0, f"弹药 Lv.{condition['ammoLevel']}")
        return " · ".join(labels)
    if kind == "resource_family_membership":
        return "同组弹体，触发方式待核实"
    if kind == "action_name_hash_candidates":
        return f"动作指南有 {len(condition['candidateGuideIds'])} 个候选匹配"
    if kind == "inherited_action_method":
        return "沿用基础动作判定"
    if kind == "external_attack_collision":
        return "由外部动作处理调用"
    if kind == "horn_high_freq":
        effect = condition["highFreqType"].removeprefix("HIGH_FREQ_")
        level = condition["musicLevel"]
        return (
            f"响周波（{HORN_EFFECTS.get(effect, effect)} · {LEVELS.get(level, level)}）"
        )
    if kind == "horn_hibiki_damage":
        level = condition["damageType"].removeprefix("DAMAGE_")
        return f"回响伤害（{LEVELS.get(level, level)}）"
    if kind == "charge_blade_phial":
        phial = condition["binType"]
        labels = [{"ELEMENT": "强属性瓶", "GRENADE": "榴弹瓶"}.get(phial, phial)]
        if condition["overCharged"]:
            labels.append("过充")
        if condition["comboDischarge"]:
            labels.append("连携解放")
        return " · ".join(labels)
    if kind == "insect_attack_type":
        attack = condition["attackType"]
        return f"猎虫 · {INSECT_ATTACKS.get(attack, attack)}"
    if kind == "bow_bottle":
        bottle = condition["bottleType"]
        return "贯穿瓶" if bottle == "PENETRATE" else f"弓瓶 · {bottle}"
    if kind == "bow_tsugiya_homing":
        return "引导箭 · 贯穿" if condition["penetrate"] else "引导箭 · 单次命中"
    if kind == "bow_normal_askill005":
        level = condition["parentArrowLevel"]
        return f"原箭矢 · {'引导' if level == 'HOMING' else level}"
    if kind in {"bow_homing_body_hit", "bow_arrow_type_override"}:
        arrow = condition.get("parentArrowType") or condition["arrowType"]
        return f"箭矢类型 · {ARROW_TYPES.get(arrow, arrow)}"
    return f"待核实的判定条件（{kind}）"


def _describe_workbook_conditions(cell):
    if not cell:
        return None
    # Workbook cells join JSON objects with "; ". Decode each object first so
    # punctuation inside string values cannot split a condition in two.
    decoder = json.JSONDecoder()
    labels = []
    while True:
        condition, end = decoder.raw_decode(s=cell)
        labels.append(_describe_condition(condition=condition))
        if end == len(cell):
            return "；".join(labels)
        if not cell.startswith("; ", end):
            raise ValueError(f"Invalid MappingCondition separator in {cell!r}")
        cell = cell[end + 2 :]


def _fixed_element(row):
    symbol = normalize(value=row["_AttackAttrFixed._Value"])
    if symbol == "NONE":
        return None
    return {"name": ENUMS["受击属性"][symbol], "value": row["_AttrValue"]}


def export_weapon_actions(*, output_dir, repository, text_source):
    action_map = (
        os.environ.get(ACTION_MAP_ENV_VAR) or repository.root.parent / "ActionMap.json"
    )
    catalog = load_action_value_catalog(
        natives_dir=repository.root,
        action_map_path=Path(action_map),
    )
    text = text_source.build(lang_id=ZH_HANS_LANGUAGE_ID)
    workbook = build_action_value_workbook(
        catalog=catalog,
        resolve_text=text.get,
    )
    sheets = []
    for scope, sheet_name in SHEET_NAMES.items():
        groups = []
        for group in workbook.groups[sheet_name]:
            # Workbook group bounds include two header rows and an inclusive end.
            records = workbook.sheets[sheet_name][
                group.start_row - 3 : group.end_row - 2
            ]
            first = records[0]
            groups.append(
                {
                    "name": first["MappingName"] or "未匹配动作",
                    "internal": first["MappingInternalName"],
                    "rows": [
                        {
                            "request": row["requestSetID"],
                            "condition": _describe_workbook_conditions(
                                cell=row["MappingCondition"]
                            ),
                            "attack": row["_Attack"],
                            "fixedElement": _fixed_element(row=row),
                            "fixed": row["_FixAttack"],
                            "stun": row.get("_StunDamage"),
                            "breakRate": row.get("_PartsBreakRate"),
                            "elementRate": row.get("_StatusAttrRate"),
                            "statusRate": row.get("_StatusConditionRate"),
                        }
                        for row in records
                    ],
                }
            )
        sheets.append(
            {
                "id": scope,
                "name": "弹药" if scope == "Ammo" else WEAPONS[WEAPON_CODES[scope]],
                "groups": groups,
            }
        )
    path = output_dir / OUTPUT_NAME
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        data=json.dumps(
            obj=sheets,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
