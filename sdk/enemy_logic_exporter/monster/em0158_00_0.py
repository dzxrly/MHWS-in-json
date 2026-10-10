"""Offline analysis entry for EM0158_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0158_00_0"
NATIVE_OWNER = "Em0158_00"

# Em0158 commands (game 1.42.0.2). Both onExecute read the Extend at
# work->Accessor+0x78 +0x10 after an exact cEm0158_00Extend type check.
# cCheckFire: _CheckType BODY -> Extend._BodyWrapState (+0xc8) == FIRE;
# ANY_TENTACLE -> the inlined checkFireAnyTentacle loop (any of the first
# static-count _TentacleWrapInfos has State == FIRE); other values -> false.
# cCheckLostTentacleCount: checkLostTentacleCount() sums TENTACLE_INFO.IsLost
# over the same entries; EQUAL count == _CheckNum, OR_MORE count >= _CheckNum,
# OR_LESS count <= _CheckNum.
# Tentacle checks index _TentacleWrapInfos by cSelectTentacleArg._CheckType
# (LEFT_FRONT=0 ... RIGHT_FRONT=5). cCheckWrapNone: that State == NONE.
# cCheckOilTime: State == NONE and its _WrapOilTimer (cTimer._Param) has
# _IsTimeOut. cCheckBodyOilTime: _BodyWrapState == NONE and
# _WrapBodyOilTimer._IsTimeOut (+0xc6). cCheckFireTime: _FireTimer._IsTimeOut
# (+0x102). cCheckWrapNoneBody is recovered as an ordinary Extend leaf.
EXTEND = "app.cEm0158_00Extend"
FIRE_COMMAND = "app.btable.Em0158_00BTableCommand.cCheckFire"
LOST_COMMAND = "app.btable.Em0158_00BTableCommand.cCheckLostTentacleCount"
COMMAND_PREFIX = "app.btable.Em0158_00BTableCommand."
TENTACLE_COMMANDS = ("cCheckWrapNone", "cCheckOilTime")
TIMER_COMMANDS = {
    "cCheckBodyOilTime": "_WrapBodyOilTimer",
    "cCheckFireTime": "_FireTimer",
}
WRAP_STATES = {"NONE": 0, "OIL": 1, "FIRE": 2}
LOST_OPERATORS = {"EQUAL": "eq", "OR_MORE": "ge", "OR_LESS": "le"}
FIRE_EVIDENCE = (
    dict(
        type=FIRE_COMMAND,
        method="onExecute1234233",
        address="0x1441955e0",
        end="0x144195640",
    ),
    dict(
        type=EXTEND,
        method="checkFireAnyTentacle546125",
        address="0x144915160",
        end="0x1449151b5",
    ),
)
STATE_EVIDENCE = {
    "cCheckWrapNone": dict(
        method="onExecute1234245", address="0x144a1ff40", end="0x144a1ffa0"
    ),
    "cCheckOilTime": dict(
        method="onExecute1234249", address="0x1450a7d80", end="0x1450a7e20"
    ),
    "cCheckBodyOilTime": dict(
        method="onExecute1234251", address="0x145393660", end="0x1453936b0"
    ),
    "cCheckFireTime": dict(
        method="onExecute1234235", address="0x144462ab0", end="0x144462b00"
    ),
}
LOST_EVIDENCE = (
    dict(
        type=LOST_COMMAND,
        method="onExecute1234264",
        address="0x145dbc420",
        end="0x145dbc4a2",
    ),
    dict(
        type=EXTEND,
        method="checkLostTentacleCount546134",
        address="0x1449152d0",
        end="0x144915328",
    ),
)


def recover_condition(node, enemy_id, resources):
    """Reviewed wrap-state and lost-tentacle checks over this monster's Extend."""
    from copy import deepcopy

    from ..shared.logic.expressions import combined, compare, runtime
    from ..shared.logic.values import scalar

    command = node.get("commandType")
    name = str(command).removeprefix(COMMAND_PREFIX)
    if command not in (FIRE_COMMAND, LOST_COMMAND) and name not in STATE_EVIDENCE:
        return None
    argument = node.get("argument") or {}
    mode = (
        str(scalar(argument["_CheckType"])).split("] ", 1)[-1]
        if "_CheckType" in argument
        else None
    )
    guards = (
        runtime("enemy_command_work_valid", "命令工作存在且原生类型检查通过"),
        runtime("self_extend_valid", "自身 Extend 存在且是 cEm0158_00Extend"),
    )
    extra = {}
    if name in STATE_EVIDENCE:
        checks = []
        if name in TENTACLE_COMMANDS:
            if mode is None:
                return None
            path = f"_TentacleWrapInfos[{mode}]"
            key = f"extend:{EXTEND}.{path}.State"
            checks.append(
                compare(key, WRAP_STATES["NONE"], source=f"{EXTEND}.{path}.State")
            )
            extra["inputEnums"] = {key: dict(WRAP_STATES)}
            summary = f"{path}.State 为 NONE"
            if name == "cCheckOilTime":
                timer = f"{path}._WrapOilTimer._IsTimeOut"
                checks.append(
                    runtime(f"extend:{EXTEND}.{timer}", "该触手缠油计时器已超时")
                )
                summary += f"，且 {timer}"
        else:
            timer = TIMER_COMMANDS[name] + "._IsTimeOut"
            if name == "cCheckBodyOilTime":
                key = f"extend:{EXTEND}._BodyWrapState"
                checks.append(
                    compare(key, WRAP_STATES["NONE"], source=f"{EXTEND}._BodyWrapState")
                )
                extra["inputEnums"] = {key: dict(WRAP_STATES)}
            checks.append(runtime(f"extend:{EXTEND}.{timer}", f"{timer} 为真"))
            summary = ("BodyWrapState 为 NONE，且 " if len(checks) > 1 else "") + timer
        return dict(
            expression=combined("all", *guards, *checks),
            summary=summary,
            semanticStatus="reviewed_native_semantics",
            semanticEvidence=[dict(type=COMMAND_PREFIX + name, **STATE_EVIDENCE[name])],
            **extra,
        )
    if command == FIRE_COMMAND and mode == "BODY":
        key = f"extend:{EXTEND}._BodyWrapState"
        check = compare(key, WRAP_STATES["FIRE"], source=f"{EXTEND}._BodyWrapState")
        summary = "BodyWrapState 为 FIRE"
        extra["inputEnums"] = {key: dict(WRAP_STATES)}
    elif command == FIRE_COMMAND and mode == "ANY_TENTACLE":
        check = runtime(
            f"extend:{EXTEND}.checkFireAnyTentacle()",
            "_TentacleWrapInfos 中任一触手的 State 为 FIRE",
        )
        summary = "checkFireAnyTentacle() 成立（任一触手 State 为 FIRE）"
    elif command == LOST_COMMAND and mode in LOST_OPERATORS:
        number = scalar(argument["_CheckNum"])
        if type(number) is not int:
            return None
        operator = LOST_OPERATORS[mode]
        check = compare(
            f"extend:{EXTEND}.checkLostTentacleCount()",
            number,
            operator,
            source="_TentacleWrapInfos 中 IsLost 为真的条数",
        )
        sign = {"eq": "=", "ge": "≥", "le": "≤"}[operator]
        summary = f"checkLostTentacleCount() {sign} {number}"
    else:
        return None
    return dict(
        expression=combined("all", *guards, check),
        summary=summary,
        semanticStatus="reviewed_native_semantics",
        semanticEvidence=deepcopy(
            list(FIRE_EVIDENCE if command == FIRE_COMMAND else LOST_EVIDENCE)
        ),
        **extra,
    )


def extract(context):
    """Select this monster's declared tables, imports and native method contexts."""
    return context.extract_enemy(ENEMY_ID, NATIVE_OWNER)


def build_model(
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    *,
    requests_path=None,
    inventory_path=None,
    context=None
):
    """Extract this EM from its real slot/import closure and typed native calls."""
    from ..shared.models.native_recipe import build_monster

    return build_monster(
        ENEMY_ID,
        NATIVE_OWNER,
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        requests_path=requests_path,
        inventory_path=inventory_path,
        context=context,
    )
