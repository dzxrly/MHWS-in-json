"""Offline analysis entry for EM0162_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0162_00_0"
NATIVE_OWNER = "Em0162_00"

# cCheckTargetFromLegJoint (game 1.42.0.2). onExecute picks the leg joint by
# _WhitchLeg (Extend joint holder +0x38/+0x20/+0x28/+0x30 for LF/RF/LB/RB) and
# the target position; checkTargetPos projects joint -> target onto XZ and
# requires |d| <= _AllowLength, then by _FrontOrBack the signed angle
# a = AppMath.diffRad(...) * 57.2958 must satisfy FRONT |a| <= 90,
# BACK |a| >= 90, LEFT a < 0 or RIGHT a >= 0.
LEG_JOINT_COMMAND = "app.btable.Em0162_00BTableCommand.cCheckTargetFromLegJoint"
LEG_JOINT_EVIDENCE = (
    dict(
        type=LEG_JOINT_COMMAND,
        method="onExecute1234370",
        address="0x1484b0bf0",
        end="0x1484b0f24",
    ),
    dict(
        type=LEG_JOINT_COMMAND,
        method="checkTargetPos1234372",
        address="0x1484b0f30",
        end="0x1484b11e8",
    ),
    dict(
        type="app.AppMath",
        method="diffRad1120814",
        address="0x144b88520",
        end="0x144b8877f",
    ),
)
# Em0162 leg enum names; the game messages have no text for them.
LEG_NAMES = ("LF", "RF", "LB", "RB")
LEG_DIRECTIONS = {
    "FRONT": "前方（夹角绝对值 ≤ 90°）",
    "BACK": "后方（夹角绝对值 ≥ 90°）",
    "LEFT": "左侧（带符号夹角 < 0）",
    "RIGHT": "右侧（带符号夹角 ≥ 0）",
}


# cCheckBreakParts (game 1.42.0.2, onExecute 0x148de7150..0x148de71f0): the
# PARTS_BREAK choice selects a fixed element of
# cEnemyContext.Parts._BreakPartsByPartsIdx; true when its _BreakCount > 0.
# Other choices return false.
BREAK_PARTS_COMMAND = "app.btable.Em0162_00BTableCommand.cCheckBreakParts"
BREAK_PARTS_EVIDENCE = dict(
    type=BREAK_PARTS_COMMAND,
    method="onExecute1234385",
    address="0x148de7150",
    end="0x148de71f0",
)
# PARTS_BREAK name -> element read by the native switch.
BREAK_PARTS_ELEMENTS = {"TAIL_LOST": 7, "HEAD": 0, "CORE_WAIST": 8, "CORE_MAIN": 10}

DEST_WALL_COMMAND = "app.btable.Em0162_00BTableCommand.cCheckDestWall"
DEST_GIMMICK_COMMAND = "app.btable.Em0162_00BTableCommand.cCheckDestShutterGimmick"
DEST_GIMMICK_IDS = ("GM607_000_00", "GM607_001_00", "GM601_000_00")
WALL_EXCLUDE_MASK = 0x2100


def _recover_destination_scene(node):
    from ..shared.logic.expressions import combined, compare, runtime
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition
    from ..shared.logic.values import scalar

    command = node.get("commandType")
    if command not in (DEST_WALL_COMMAND, DEST_GIMMICK_COMMAND):
        return None
    threshold = scalar(node["argument"]["_CheckDest"])
    if type(threshold) not in (int, float):
        return None
    if command == DEST_WALL_COMMAND:
        found = "em0162_active_wall_query_found"
        count = "em0162_eligible_wall_count"
        distance = "em0162_nearest_eligible_wall_distance"
        expression = combined(
            "all",
            runtime(found, "自身 getDataInfoEm 与 getWallInfoArrayActive 均成功"),
            compare(
                count,
                0,
                "gt",
                source=f"有效 WALL_INFO 中 (_Data._MaskBits & {WALL_EXCLUDE_MASK:#x}) == 0 的数量",
            ),
            compare(distance, threshold, "le", source="上述有效墙体的最小 _Data._Dist"),
        )
        inputs = {
            found: dict(label="自身位置的活动墙体查询成功", boolean=True),
            count: dict(
                label="未设置 0x2100 屏蔽位的有效墙体数", number=True, min=0, max=None
            ),
            distance: dict(
                label="这些墙体中最小的墙体距离",
                number=True,
                min=0,
                max=None,
                unit="命令距离单位",
            ),
        }
        result = reviewed_condition(
            expression,
            condition_evidence("frozen_wall"),
            summary=f"活动墙体查询成功，且未被 0x2100 屏蔽的墙体距离 ≤ {threshold:g}",
            inputs=inputs,
        )
    else:
        count = "em0162_shutter_gimmick_count"
        distance = "em0162_nearest_shutter_gimmick_xz"
        expression = combined(
            "all",
            compare(count, 0, "gt", source="三类机关中对象与场景实体均有效的数量"),
            compare(
                distance,
                abs(threshold),
                "le",
                source="这些机关到怪物自身的最小 XZ 平面距离；原生比较距离平方与资源阈值平方",
            ),
        )
        inputs = {
            count: dict(
                label="GM607_000_00、GM607_001_00、GM601_000_00 的有效对象数",
                number=True,
                min=0,
                max=None,
            ),
            distance: dict(
                label="这些机关到怪物自身的最小水平距离",
                number=True,
                min=0,
                max=None,
                unit="命令距离单位",
            ),
        }
        result = reviewed_condition(
            expression,
            condition_evidence("frozen_gimmick"),
            summary=f"三类指定机关中有对象与怪物自身的水平距离 ≤ {abs(threshold):g}",
            extend="app.cEm0162_00Extend",
            inputs=inputs,
        )
        result["gimmickTypes"] = list(DEST_GIMMICK_IDS)
    return result


def _recover_break_parts(node):
    from copy import deepcopy

    from ..shared.logic.expressions import combined, runtime
    from ..shared.logic.values import scalar

    name = str(scalar(node["argument"]["_ChoiceBreakParts"])).split("] ", 1)[-1]
    if name not in BREAK_PARTS_ELEMENTS:
        return None
    element = BREAK_PARTS_ELEMENTS[name]
    return dict(
        expression=combined(
            "all",
            runtime("enemy_command_work_valid", "命令工作存在且原生类型检查通过"),
            runtime(
                f"break_parts_element:{element}",
                f"cEnemyContext.Parts._BreakPartsByPartsIdx[{element}]._BreakCount > 0",
            ),
        ),
        summary=f"{name} 的破坏次数 > 0",
        semanticStatus="reviewed_native_semantics",
        semanticEvidence=[deepcopy(BREAK_PARTS_EVIDENCE)],
        sceneInput="break_parts",
    )


def recover_condition(node, enemy_id, resources):
    """Reviewed position and part checks, shown as scene inputs per argument."""
    scene = _recover_destination_scene(node)
    if scene is not None:
        return scene
    if node.get("commandType") == BREAK_PARTS_COMMAND:
        return _recover_break_parts(node)
    if node.get("commandType") != LEG_JOINT_COMMAND:
        return None
    from copy import deepcopy

    from ..shared.logic.expressions import combined, runtime
    from ..shared.logic.values import scalar

    argument = node["argument"]
    leg = str(scalar(argument["_WhitchLeg"])).split("] ", 1)[-1]
    direction = str(scalar(argument["_FrontOrBack"])).split("] ", 1)[-1]
    length = scalar(argument["_AllowLength"])
    if (
        leg not in LEG_NAMES
        or direction not in LEG_DIRECTIONS
        or type(length) not in (int, float)
    ):
        return None
    key = f"leg_joint:{leg}:{direction}:{length:g}"
    return dict(
        expression=combined(
            "all",
            runtime("enemy_command_work_valid", "命令工作存在且原生类型检查通过"),
            runtime("self_extend_valid", "自身 Extend 及其腿关节对象存在"),
            runtime(key, "目标位置可取得，且满足该腿关节的水平距离与方位条件"),
        ),
        summary=(
            f"玩家位于腿关节 {leg} 的{LEG_DIRECTIONS[direction]}，"
            f"且水平距离 ≤ {length:g}"
        ),
        semanticStatus="reviewed_native_semantics",
        semanticEvidence=deepcopy(list(LEG_JOINT_EVIDENCE)),
        sceneInput="leg_joint",
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
    context=None,
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
