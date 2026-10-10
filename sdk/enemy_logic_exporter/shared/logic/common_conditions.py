"""Reviewed common-command cases, bound to resource values and native fields.

Only the listed cases are accepted. Runtime keys describe raw fields or the
explicit target/parts queries, rather than assuming a command's final result.
"""

import json
from copy import deepcopy
from functools import lru_cache
from ..config import (
    BAD_CONDITION_LABELS,
    EVIDENCE_DIR,
    HUNTER_BAD_CONDITION_INDEX,
    HUNTER_BAD_CONDITION_SOURCE,
    HUNTER_STATUS_BITS,
    HUNTER_STATUS_LABELS,
    HUNTER_STATUS_SOURCE,
    STATE_SIGN_LABELS,
    STATE_SIGN_SOURCE,
    COMMON_COMMAND_PREFIX,
    CONDITION_FIELDS as FIELDS,
)
from ..resources.reader import typed
from .expressions import runtime, compare, combined
from .values import enum_number, scalar
from .navigation_conditions import recover_navigation_condition


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        (EVIDENCE_DIR / "condition_evidence.v1.json").read_text(encoding="utf8")
    )


def enum_name(value):
    return str(scalar(value)).split("] ", 1)[-1]


def _enemy_label(resources, value):
    """Official monster name for an Enemy enum value, else its enum name."""
    name = enum_name(value)
    if resources is not None:
        try:
            return resources.enemy_name(name)["displayName"]
        except ValueError:
            pass
    return name


def _player_target_status(argument):
    """Return the player branch of CheckStatus for a reviewed case, or None."""
    category = enum_number(argument["_EditCategory"])
    if category == 2:
        name = enum_name(typed(argument["BadConditions"])[1]["_EditArg"])
        if name == "STUN" or name not in HUNTER_BAD_CONDITION_INDEX:
            return None
        index = HUNTER_BAD_CONDITION_INDEX[name]
        player = runtime(
            "selected_hunter_bad_condition:" + name,
            HUNTER_BAD_CONDITION_SOURCE.format(index=index),
        )
        return player, False, "当前目标处于" + BAD_CONDITION_LABELS.get(name, name)
    if category == 3:
        name = enum_name(typed(argument["Status"])[1]["_EditArg"])
        if name not in HUNTER_STATUS_BITS:
            return None
        player = runtime(
            "selected_hunter_status:" + name,
            HUNTER_STATUS_SOURCE.format(bits="/".join(map(str, HUNTER_STATUS_BITS[name]))),
        )
        return player, False, HUNTER_STATUS_LABELS[name].replace("玩家", "当前目标（玩家）")
    return None


def _part_name(resources, enemy_id, guid):
    """The official name (or _PartsType name) of one EmParamParts part."""
    owner = "Em" + enemy_id[2:9]
    path = f"STM/GameDesign/Enemy/{owner[:6]}/{owner[7:]}/Data/{owner}_Param_Parts.user.3.json"
    try:
        body = resources.read(path)
    except FileNotFoundError:
        return None
    matches = [
        typed(item)[1]
        for item in typed(body["_PartsArray"])[1]["_DataArray"]
        if typed(item)[1]["_InstanceGuid"] == guid
    ]
    return resources.part_name(matches[0]["_PartsType"]) if len(matches) == 1 else None


def recover_condition(node, profile, enemy_id, resources):
    if profile != receipt()["profile"]:
        raise ValueError("公共条件配方与来源版本不匹配")
    command = node.get("commandType", "")
    if not command.startswith(COMMON_COMMAND_PREFIX):
        # Monster-specific commands are reviewed in their own monster modules.
        from .monster_rules import hooks

        for recover in hooks("recover_condition"):
            recovered = recover(node, enemy_id, resources)
            if recovered is not None:
                return recovered
        return None
    navigation = recover_navigation_condition(node, profile)
    if navigation is not None:
        return navigation
    argument = node["argument"]
    guard = runtime(
        "enemy_command_work_valid",
        FIELDS["command_work_valid"],
    )
    self_valid = runtime(
        "self_target_context_valid",
        FIELDS["target_context"],
    )
    selected = (
        FIELDS["selected_target"]
    )
    key = command.rsplit(".", 1)[-1]
    extra = {}
    if key == "cCheckSelfType":
        category = enum_number(argument["_EditCategory"])
        evidence = "self_type"
        if category == 2:
            value = scalar(typed(argument["QuestRank"])[1]["_EditArg"])
            if type(value) is not int or not 0 <= value < 3:
                return None
            expression = compare(
                "environment_current_rank",
                value,
                source="EnvironmentManager.get_CurrentRank 的实际返回值；资源等级经 getTYPEFromFixed 校验",
            )
            summary = f"当前任务等级为 {value}"
        elif category == 5:
            # Basic.RoleID (+0x4c) == the resource RoleID; compared by enum name.
            name = enum_name(typed(argument["RoleID"])[1]["_EditArg"])
            expression = compare("self_basic_role_id", name, source=FIELDS["role_id"])
            summary = "自身 RoleID 为 " + name
        elif category == 6:
            value = enum_number(typed(argument["LegendaryID"])[1]["_EditArg"])
            expression = compare(
                "self_basic_legendary_id",
                value,
                source=FIELDS["legendary_id"],
            )
            summary = "自身历战分类为 " + str(
                scalar(typed(argument["LegendaryID"])[1]["_EditArg"])
            )
        elif category == 1:
            value = enum_number(typed(argument["Enemy"])[1]["_EditArg"])
            mapped = runtime(
                f"enemy_enum_index:{value}",
                "EnumMaker.getEnumValue：在当前 Enemy 枚举表查找资源枚举 key，未找到返回 -1",
            )
            expression = combined(
                "any",
                dict(
                    kind="compare",
                    operator="eq",
                    left=mapped,
                    right=dict(kind="constant", value=-1),
                ),
                dict(
                    kind="compare",
                    operator="eq",
                    left=runtime(
                        "self_basic_enemy_id", FIELDS["enemy_id"]
                    ),
                    right=mapped,
                ),
            )
            summary = "自身怪物类型匹配 " + _enemy_label(
                resources, typed(argument["Enemy"])[1]["_EditArg"]
            )
            extra["detail"] = (
                "资源枚举先映射为 Enemy ID；映射为 -1 时此原生判断返回真。不能仅凭本页怪物 ID 把分支裁掉。"
            )
        else:
            return None
        expression = combined("all", guard, self_valid, expression)
    elif key == "cCheckTargetType" and enum_number(argument["_EditCategory"]) == 2:
        evidence = "target_type"
        expression = combined(
            "all", guard, compare("selected_target_key_type", 0, source=selected)
        )
        summary = "当前有效目标是玩家"
    elif key == "cCheckTargetType" and enum_number(argument["_EditCategory"]) == 3:
        evidence = "target_type"
        expression = combined(
            "all", guard, compare("selected_target_key_type", 2, source=selected)
        )
        summary = "当前有效目标是随从"
    elif key == "cCheckTargetType" and enum_number(argument["_EditCategory"]) == 1:
        evidence = "target_type_enemy"
        name = _enemy_label(resources, typed(argument["Enemy"])[1]["_EditArg"])
        expression = combined(
            "all",
            guard,
            compare("selected_target_key_type", 1, source=selected),
            dict(
                kind="unknown",
                reason="目标怪物 Context 的启用与类型比较 helper 尚未逐项固化",
            ),
        )
        summary = "当前有效目标是怪物 " + name
        extra["detail"] = "目标键必须是怪物；目标为玩家时此判断为假。"
    elif key == "cCheckTargetStatus" and _player_target_status(argument):
        evidence = "target_status"
        player, enemy_known, summary = _player_target_status(argument)
        player = combined(
            "all",
            compare("selected_target_key_type", 0, source=selected),
            runtime(
                "selected_hunter_context_valid",
                "由选中键查询玩家 Context 且其角色模块存在",
            ),
            player,
        )
        enemy = combined(
            "all",
            compare("selected_target_key_type", 1, source=selected),
            dict(kind="unknown", reason="目标为怪物时的状态映射尚未逐项固化"),
        )
        expression = combined("all", guard, combined("any", player, enemy))
        extra["detail"] = "目标为玩家时读取玩家状态；目标为怪物时的分支保留未知。"
    elif key == "cCheckStateSignTyoe":
        evidence = "state_sign"
        name = enum_name(argument["_EditArg"])
        expression = combined(
            "all", guard, compare("self_state_sign", name, source=STATE_SIGN_SOURCE)
        )
        summary = "状态信号：" + STATE_SIGN_LABELS.get(name, name)
    elif key == "cCheckTargetStatus":
        if (
            enum_number(argument["_EditCategory"]) != 2
            or enum_number(typed(argument["BadConditions"])[1]["_EditArg"]) != 4
        ):
            return None
        evidence = "target_stun"
        player = combined(
            "all",
            compare("selected_target_key_type", 0, source=selected),
            runtime(
                "selected_hunter_context_valid",
                "由选中键查询玩家 Context 且其角色模块存在",
            ),
            runtime(
                "selected_hunter_stun_active",
                FIELDS["hunter_stun"],
            ),
        )
        enemy = combined(
            "all",
            compare("selected_target_key_type", 1, source=selected),
            runtime(
                "selected_enemy_context_enabled",
                FIELDS["enemy_enabled"],
            ),
            combined(
                "any",
                compare(
                    "selected_enemy_condition_state:15",
                    1,
                    source=FIELDS["enemy_condition_15"],
                ),
                compare(
                    "selected_enemy_condition_state:16",
                    1,
                    source="cEmModuleConditions._Conditions[16]._State；isActive(15) 实际也检查此项",
                ),
            ),
        )
        expression = combined("all", guard, combined("any", player, enemy))
        summary = "当前目标处于眩晕状态"
    elif key == "cCheckGimmickReactionType":
        evidence = "gimmick_reaction"
        name = enum_name(argument["_EditType"])
        # ReactionGm.TargetReactableGmInterface.get_ReactionType() == argument;
        # no reacting gimmick returns false, written as the value NONE.
        expression = combined(
            "all",
            guard,
            compare(
                "gimmick_reaction_type",
                name,
                source="cEmModuleReactionGm.TargetReactableGmInterface.get_ReactionType()；对象为空时记为 NONE",
            ),
        )
        summary = "正在反应的机关类型为 " + name
    elif key == "cCheckObstacleClimbHeight":
        evidence = "obstacle_climb_height"
        # cEnemyContext.Obstacle (+0x1f0): ObstacleType (+0x68) == STEP_UP_WALL
        # and StepClimbHeight (+0x80) > the .rdata constant 20.0 (1.42.0.2).
        expression = combined(
            "all",
            guard,
            self_valid,
            runtime(
                "self_obstacle_step_up_wall_climb",
                "cEnemyContext.Obstacle.ObstacleType == STEP_UP_WALL 且 StepClimbHeight > 20.0",
            ),
        )
        summary = "前方障碍为 STEP_UP_WALL 且 StepClimbHeight > 20"
        extra["sceneInput"] = "obstacle_climb_height"
    elif key == "cCheckRidingParts":
        evidence = "riding_parts"
        guid = scalar(argument["_EditPartsGuid"])
        # EmParamParts.getPartsIndex(guid) -> cEmModuleRide._RidePartsInfos
        # entry; true when its Rider key is set (category != -1, index >= 0).
        expression = combined(
            "all",
            guard,
            runtime(
                f"riding_part:{guid}",
                "该部位的 cEmModuleRide.cInfo.Rider 类别不为 -1 且索引 ≥ 0",
            ),
        )
        name = _part_name(resources, enemy_id, guid) or guid[:8]
        summary = f"有骑乘者骑在{name}上"
        extra["sceneInput"] = "riding_part"
    elif key == "cCheckBreakParts" and enum_number(argument["_EditType"]) == 0:
        evidence = "break_parts"
        guid = scalar(argument["_EditBreakPartsGuid"])
        lookup = f"parts_lookup:{guid}"
        expression = combined(
            "all",
            guard,
            runtime(
                lookup + ":has_value",
                "cSelectBreakPartsArg.getBreakPartsIndex 返回的可选索引标志；资源未就绪时受原生权限检查限制",
            ),
            dict(
                kind="compare",
                operator="lt",
                left=runtime(
                    lookup + ":index", "对该参数运行时 PartsParam 的 GUID 查询所得索引"
                ),
                right=runtime(
                    "self_parts_break_index_count",
                    FIELDS["parts_break_count"],
                ),
            ),
            runtime(
                lookup + ":record_found",
                "在 Parts 破坏记录数组中查找 Index 与上述索引相等的记录；无匹配返回假",
            ),
            compare(
                lookup + ":break_count",
                0,
                "gt",
                source=FIELDS["parts_record_break_count"],
            ),
        )
        summary = "指定部位的破坏次数 > 0"
        owner = "Em" + enemy_id[2:9]
        path = f"STM/GameDesign/Enemy/{owner[:6]}/{owner[7:]}/Data/{owner}_Param_Parts.user.3.json"
        try:
            body = resources.read(path)
        except FileNotFoundError:
            body = None
        if body is not None:
            matches = [
                (i, typed(item)[1])
                for i, item in enumerate(
                    typed(body["_PartsBreakArray"])[1]["_DataArray"]
                )
                if typed(item)[1]["_InstanceGuid"] == guid
            ]
            if len(matches) != 1:
                return None
            index, definition = matches[0]
            name = resources.part_name(definition["_PartsType"])
            summary = f"{name}的破坏次数 > 0"
            extra["partBinding"] = dict(
                source=path,
                guid=guid,
                index=index,
                definition=definition,
                scope="名称绑定来自本怪物资源；判断索引仍由运行时 PartsParam 的 GUID 查询确定",
            )
    else:
        return None
    return dict(
        expression=expression,
        summary=summary,
        semanticStatus="reviewed_native_semantics",
        semanticEvidence=deepcopy(receipt()["evidence"][evidence]),
        **extra,
    )
