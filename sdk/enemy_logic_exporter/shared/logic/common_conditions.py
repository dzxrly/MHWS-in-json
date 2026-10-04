"""Reviewed common-command cases, bound to resource values and native fields.

Only the listed cases are accepted. Runtime keys describe raw fields or the
explicit target/parts queries, rather than assuming a command's final result.
"""

import json
from copy import deepcopy
from functools import lru_cache
from ..config import EVIDENCE_DIR
from ..resources.reader import typed
from .expressions import runtime, compare, combined
from .values import enum_number, scalar
from .navigation_conditions import recover_navigation_condition


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        (EVIDENCE_DIR / "condition_evidence.v1.json").read_text(encoding="utf8")
    )


def recover_condition(node, profile, enemy_id, resources):
    if profile != receipt()["profile"]:
        raise ValueError("公共条件配方与来源版本不匹配")
    command = node.get("commandType", "")
    if not command.startswith("app.btable.EmCommonCommand."):
        return None
    navigation = recover_navigation_condition(node, profile)
    if navigation is not None:
        return navigation
    argument = node["argument"]
    guard = runtime(
        "enemy_command_work_valid",
        "cEnemyBTableCommandWork 存在且通过此命令的原生类型检查",
    )
    self_valid = runtime(
        "self_target_context_valid",
        "Accessor.TargetContext（命令工作偏移0x28，经0x68）存在",
    )
    selected = (
        "cEmModuleTarget.getTarget(requireValid=True, slot=0)：状态不为1时返回无效键"
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
        elif category == 6:
            value = enum_number(typed(argument["LegendaryID"])[1]["_EditArg"])
            expression = compare(
                "self_basic_legendary_id",
                value,
                source="cEnemyContext.Basic.LegendaryID（0x108→0x50）",
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
                        "self_basic_enemy_id", "cEnemyContext.Basic.EmID（0x108→0x48）"
                    ),
                    right=mapped,
                ),
            )
            summary = "自身怪物类型匹配 " + str(
                scalar(typed(argument["Enemy"])[1]["_EditArg"])
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
                "cHunterBadConditions._Stun（0x40）._IsActive（0x2f） != 0",
            ),
        )
        enemy = combined(
            "all",
            compare("selected_target_key_type", 1, source=selected),
            runtime(
                "selected_enemy_context_enabled",
                "选中怪物 Context 存在且其启用标志（0x308→0x27）为真",
            ),
            combined(
                "any",
                compare(
                    "selected_enemy_condition_state:15",
                    1,
                    source="cEmModuleConditions._Conditions[15]._State（0xb0→数组项→0x58）",
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
                    "cEnemyContext.Parts 的破坏索引数量（0x128→0x8c）",
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
                source="匹配破坏记录的 _BreakCount（0x18）",
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
            part = str(definition["_PartsType"]).split("] ", 1)[-1]
            name = {
                "LEFT_WING": "左翼",
                "RIGHT_WING": "右翼",
                "HEAD": "头部",
                "TAIL": "尾部",
            }.get(part, part)
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
