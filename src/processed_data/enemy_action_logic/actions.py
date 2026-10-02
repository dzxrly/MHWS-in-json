"""Identify move versions using action bank, ActionGuid and branch parameters."""

from collections import defaultdict
import hashlib
import json
import re

from src.processed_data.enemy_action_logic.source import (
    ResourceCatalog,
    ZERO_GUID,
    typed,
)

# Literal descriptions of type names; these are not an official move-name map.
ACTION_NAMES = {
    "cRocketPunch": "火箭拳",
    "cJabAttack": "刺拳",
    "cJabAttackDouble": "双刺拳",
    "cStrongJabFront": "前方重拳",
    "cStrongJabBack": "后方重拳",
    "cRushAttack": "冲撞",
    "cRushAttackTurn": "转向冲撞",
    "cBodyPress": "压身",
    "cMultiMissile": "多重导弹",
    "cUpperLaser": "上方激光",
    "cJabLaser": "刺拳激光",
    "cFlameThrower": "喷火",
    "cFlameThrowerDouble": "二连喷火",
    "cFlameThrowerTriple": "三连喷火",
    "cFlameThrowerCross": "交叉喷火",
    "cFlameThrowerCrossDouble": "二连交叉喷火",
    "cFlameThrowerCrossTriple": "三连交叉喷火",
    "cLaserCannon": "激光炮",
    "cMiniSummon": "小型召唤",
    "cRoarShort": "短咆哮",
    "cSpinLaserTwinL": "左双旋转激光",
    "cSpinLaserTwinR": "右双旋转激光",
    "cSpinLaserRight": "右旋转激光",
    "cSpinLaserLeft": "左旋转激光",
    "cRushAttackCombo": "连续冲撞",
    "cRushAttackComboTwo": "二段连续冲撞",
    "cRushAttackTriple": "三连冲撞",
    "cBackDash": "后撤",
    "cSideDash": "侧向移动",
    "cDash": "突进移动",
    "cQuickTurn": "快速转身",
    "cTakeoff": "起飞",
    "cLanding": "落地",
    "cLandingFromGlide": "滑翔后落地",
    "cWaitFly": "空中等待",
    "cSpAtkTakeoff": "大招起飞",
    "cRampageStart": "进入愤怒状态",
    "cRampageEnd": "结束愤怒状态",
    "cHostilityStart": "开始敌视",
    "cMasteredBomb": "芥末炸弹",
    "cResetJetAttack": "喷射攻击重置",
}
for _range, _name in (("Far", "远距离调整步"), ("Near", "近距离调整步")):
    for _direction, _text in (("F", "前"), ("B", "后"), ("L", "左"), ("R", "右")):
        ACTION_NAMES[f"cAdjustStep{_range}{_direction}"] = f"{_name}（向{_text}）"


def action_group(kind: str) -> str:
    if re.search(r"Rampage|Hostility|SpAtk|Summon|Roar", kind):
        return "特殊状态动作"
    if re.search(r"Punch|Jab|Strong", kind):
        return "拳击动作"
    if re.search(r"Rush|Press|Stamp", kind):
        return "冲撞与压身"
    if re.search(r"Laser|Flame|Missile|Bomb|Blaster", kind):
        return "远程攻击"
    if re.search(r"Step|Dash|Turn|Glide|Takeoff|Landing|WaitFly|Refresh", kind):
        return "移动与姿态调整"
    return "其他战斗动作"


def variant_id(action: dict) -> str:
    identity = [
        action.get(key)
        for key in ("type", "actionSource", "assetIndex", "guid", "branchGuid")
    ]
    return hashlib.sha256(
        json.dumps(identity, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def parameter_notes(params: dict) -> list[str]:
    notes = []
    for key, name in (
        ("_LoopTime", "循环计时配置"),
        ("_OverrideMotionRate_Angry", "愤怒状态动画倍率"),
    ):
        if key in params and (key != "_OverrideMotionRate_Angry" or params[key] != 1):
            notes.append(f"{name} = {params[key]:g}")
    filters = []
    for item in params.get("_MotionSequenceFilters", []):
        _, item = typed(item)
        if "STRUCT__ID_PageNo" in item and "STRUCT__ID_FilterNo" in item:
            filters.append(f"{item['STRUCT__ID_PageNo']}/{item['STRUCT__ID_FilterNo']}")
    if filters:
        notes.append("动画过滤版本 " + "、".join(filters))
    return notes


def resource_actions(catalog: ResourceCatalog) -> list[dict]:
    tables = {table["source"].casefold(): table for table in catalog.tables}
    pending = [key for key in tables if "combat" in key or "commonattack" in key]
    selected = set()
    while pending:
        key = pending.pop()
        if key in selected or key not in tables:
            continue
        selected.add(key)
        pending.extend(path.casefold() for path in tables[key]["imports"] if path)
    params = defaultdict(list)
    for row in catalog.action_params:
        params[(row["guid"], row["branchGuid"])].append(row)
    actions = {}
    for key in sorted(selected):
        for record in tables[key]["actionArguments"]:
            action = {
                "type": record["class"] or "未解析动作类型",
                "evidence": "resource",
                **{
                    name: record[name]
                    for name in ("assetIndex", "guid", "branchGuid", "actionSource")
                },
            }
            matches = [
                row
                for row in params[(action["guid"], action["branchGuid"])]
                if row["class"] == action["type"]
                and (
                    not action["actionSource"]
                    or not row["actionSource"]
                    or row["actionSource"].casefold()
                    == action["actionSource"].casefold()
                )
            ]
            action["parameterSources"] = [
                {"source": row["source"], "index": row["index"]} for row in matches
            ]
            action["parameters"] = matches[0]["parameters"] if len(matches) == 1 else {}
            action["parameterResolved"] = len(matches) == 1 and matches[0].get(
                "parameterCompatible", True
            )
            action["parameterClass"] = (
                matches[0].get("parameterClass") if len(matches) == 1 else None
            )
            action["parameterNotes"] = parameter_notes(action["parameters"])
            action["variantId"] = variant_id(action)
            action = actions.setdefault(action["variantId"], {**action, "sources": []})
            action["sources"].append(
                {"source": tables[key]["source"], "index": record["index"]}
            )
    versions = defaultdict(list)
    for action in actions.values():
        versions[action["type"]].append(action)
    for entries in versions.values():
        for index, action in enumerate(entries, 1):
            action["versionLabel"] = (
                "默认参数" if action["branchGuid"] == ZERO_GUID else f"参数版本 {index}"
            )
    return list(actions.values())


def action_label(action: dict) -> str:
    kind = action["type"]
    name = ACTION_NAMES.get(kind, "动作类型")
    lines = [name, kind, action.get("versionLabel", "")]
    lines.extend(action.get("parameterNotes", []))
    if not action.get("parameterResolved", True):
        lines.append("具体参数尚未关联")
    return "\n".join(line for line in lines if line)
