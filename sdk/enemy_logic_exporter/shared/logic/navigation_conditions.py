"""Reviewed navigation guards; unresolved physical filters stay explicit.

Inputs name query outputs and individual native fields, never the final command
or EnemyUtil result. The Boolean bit inputs are snapshots of the named raw bit,
not a substitute for running the whole condition helper.
"""

import json
import struct
from pathlib import Path
from copy import deepcopy
from functools import lru_cache
from ..config import (
    EVIDENCE_DIR,
    COMMON_COMMAND_PREFIX,
    CONDITION_FIELDS as FIELDS,
    OCCLUSION_QUERY,
)
from .values import MissingState, enum_number, scalar
from .expressions import runtime, compare, combined, invert


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        Path(EVIDENCE_DIR / "navigation_condition_evidence.v1.json").read_text(
            encoding="utf-8"
        )
    )


def verify_navigation_conditions(pe, metadata):
    """Verify the specialized Unfair chain and its referenced constant data.

    RIP targets are decoded from the current method identity, rather than
    carrying unmigratable addresses for Nullable templates, classes or statics.
    """
    from capstone import CS_OP_MEM
    from ..native.symbols import instructions, method_stem

    document = receipt()
    rows = document["evidence"]["unfair_active"]
    by_method = {}
    for row in rows:
        method = (metadata.get(row["type"]) or {}).get("methods", {}).get(row["method"])
        if method is None or int(method.get("function", "0"), 16) != int(
            row["address"], 16
        ):
            raise ValueError(
                "Unfair资格链方法身份变化：" + row["type"] + "." + row["method"]
            )
        signature = row["signature"]
        if [p.get("type") for p in method.get("params", [])] != signature[
            "params"
        ] or method.get("returns", {}).get("type") != signature["returns"]:
            raise ValueError("Unfair资格链方法签名变化：" + row["method"])
        start, end = int(row["address"], 16), int(row["end"], 16)
        expected = bytes.fromhex(row["nativeBytes"])
        if end - start != len(expected) or pe.read(start, len(expected)) != expected:
            raise ValueError("Unfair资格链原生字节变化：" + row["method"])
        by_method[row["type"], method_stem(row["method"])] = row
    for check in document["unfairFieldChecks"]:
        field = metadata.fields(check["type"]).get(check["field"], {})
        if (
            field.get("type") != check["fieldType"]
            or field.get("offset_from_base") != check["offset"]
        ):
            raise ValueError(
                "Unfair资格链字段布局变化：" + check["type"] + "." + check["field"]
            )
    for check in document["unfairEnumChecks"]:
        field = (
            (metadata.get(check["type"]) or {})
            .get("fields", {})
            .get(check["field"], {})
        )
        if field.get("default") != check["value"]:
            raise ValueError(
                "Unfair资格链枚举变化：" + check["type"] + "." + check["field"]
            )
    for check in document["unfairRipChecks"]:
        row = by_method[check["type"], check["method"]]
        pc = int(row["address"], 16) + int(check["instructionOffset"], 16)
        decoded, _ = instructions(pe, pc, pc + 16)
        if not decoded:
            raise ValueError("Unfair常量读取指令缺失")
        ins = decoded[0]
        operand = ins.operands[check.get("operand", 1)]
        if (
            operand.type != CS_OP_MEM
            or ins.reg_name(operand.mem.base) != "rip"
            or operand.mem.index
        ):
            raise ValueError("Unfair常量不再来自已审核的RIP读取")
        address = ins.address + ins.size + operand.mem.disp + check.get("readOffset", 0)
        if check["kind"] == "class":
            expected = int(
                (metadata.get(check["classType"]) or {}).get("address", "0"), 16
            )
            actual = int.from_bytes(pe.read(address, 8), "little")
        else:
            format_code, size = {
                "Int32": ("<i", 4),
                "Single": ("<f", 4),
                "Byte": ("<B", 1),
            }[check["kind"]]
            actual = struct.unpack(format_code, pe.read(address, size))[0]
            expected = (
                document["unfairConstants"][check["constant"]]
                if "constant" in check
                else check["value"]
            )
        if actual != expected:
            raise ValueError(
                "Unfair资格链引用常量或类型变化："
                + check.get("constant", check["kind"])
            )


def bit(member, index):
    return runtime(
        f"destination_wall:{member}:bit:{index}",
        f"本次 getWallInfoNearVector 输出 WALL_INFO._Data.{member} 的 bit {index}；原始位值",
    )


def category(value, operator="eq"):
    return compare(
        "self_basic_category",
        value,
        operator,
        source=FIELDS["category"],
    )


def destination_relation(argument):
    relation = enum_number(argument["_EditType"])
    if relation not in (0, 1):
        return None
    source = "本次目标/Nullable 覆盖位置减去 holder.Transform.Pos 的 vec3"
    prefix = [
        runtime(
            "self_target_context_valid",
            FIELDS["target_context_nav"],
        ),
        runtime(
            "destination_nav_query_succeeded",
            FIELDS["nav_query"],
        ),
        runtime(
            "self_target_module_valid",
            FIELDS["target_module"],
        ),
        combined(
            "any",
            runtime(
                "destination_override_has_value",
                FIELDS["override_position"],
            ),
            runtime(
                "destination_target_position_has_value",
                FIELDS["target_position"],
            ),
        ),
        runtime(
            "destination_wall_query_succeeded",
            FIELDS["wall_query"],
        ),
        invert(bit("_NaviAttribute", 3)),
        compare(
            "destination_wall_distance",
            0,
            "ge",
            source="WALL_INFO._Data._Dist；不把查询距离当高度阈值",
        ),
        dict(
            kind="compare",
            operator="le",
            left=runtime("destination_wall_distance", "WALL_INFO._Data._Dist"),
            right=runtime(
                "destination_displacement_length",
                source + "的长度；原生 sqrt(x²+y²+z²)",
            ),
        ),
    ]
    if relation == 1:
        classification = combined(
            "any",
            bit("_Attribute1", 4),
            combined("all", category(0), bit("_MaskBits", 8)),
            combined("all", category(0, "ne"), bit("_MaskBits", 13)),
        )
        detail = "LOW 要求目标位移Y严格小于0；墙属性位或按大型/其他怪物分类选择的 MaskBits 也必须匹配。查询失败、禁止导航属性或墙距离越界均返回假。"
    else:
        classification = combined(
            "any",
            combined("all", category(0), bit("_NaviAttribute", 5)),
            combined("all", category(1), bit("_NaviAttribute", 6)),
            bit("_Attribute1", 1),
            bit("_Attribute1", 8),
            bit("_Attribute1", 9),
            combined(
                "all",
                compare(
                    "self_current_area_no",
                    2,
                    source=FIELDS["area_no"],
                ),
                compare(
                    "self_current_stage_no",
                    0,
                    source=FIELDS["stage_no"],
                ),
                combined("any", bit("_Attribute1", 7), bit("_MaskBits", 31)),
                dict(
                    kind="unknown",
                    reason=FIELDS["terrain_fallback"],
                ),
            ),
        )
        detail = "HIGH 常规路径按怪物分类、导航属性与墙属性检查；只有这些路径均不成立时才进入特定区域的物理回退。所有成功路径都要求目标位移Y严格大于0。未把回退命中简化成最终布尔输入。"
    expression = combined(
        "all",
        *prefix,
        classification,
        compare(
            "destination_displacement_y",
            0,
            "gt" if relation == 0 else "lt",
            source=source + "的Y分量",
        ),
    )
    return dict(
        expression=expression,
        summary=(
            "目标在自身上方且地形检查满足高处条件"
            if relation == 0
            else "目标在自身下方且地形检查满足低处条件"
        ),
        semanticStatus=(
            "reviewed_partial_native_semantics"
            if relation == 0
            else "reviewed_native_semantics"
        ),
        semanticEvidence=deepcopy(receipt()["evidence"]["destination_relation"]),
        detail=detail,
        queryContract=deepcopy(receipt()["queryContracts"]["destination_relation"]),
    )


def unfair_qualification():
    """Specialize checkTargetCharaUnfair to this command's actual arguments.

    The position/float Nullable values are empty, both optional Boolean modes
    are false, and the stage exclusion mode is true. Query inputs describe only
    the named native query's normal return and its raw output fields.
    """
    constants = receipt()["unfairConstants"]
    special = constants["specialCombatArea"]
    area_limit = constants["combatAreaLimit"]
    near_limit = constants["nearGroundDistanceSquared"]

    def current_area(value, operator="eq"):
        return compare(
            "self_current_area_no", value, operator, source=FIELDS["area_no"]
        )

    source = "所选玩家 FieldAreaInfo._MergedAreaBit_EnemyCombatArea"
    current_bit = combined(
        "any",
        combined(
            "all",
            current_area(special),
            runtime(
                "selected_hunter_combat_area_bit_special", source + f" 的 bit {special}"
            ),
        ),
        combined(
            "all",
            current_area(special, "ne"),
            runtime(
                "selected_hunter_combat_area_bit_current",
                source + " 的 bit (自身区域编号 & 63)",
            ),
        ),
    )
    near = compare(
        "unfair_ground_transform_distance_squared",
        near_limit,
        "lt",
        source="本次检测位置与所选玩家 Transform.Pos 的三维差平方和（按原生单精度顺序）",
    )
    near_area = combined(
        "all",
        invert(
            combined(
                "all",
                current_area(0, "ge"),
                current_area(area_limit, "lt"),
                current_bit,
            )
        ),
        combined(
            "any",
            current_area(special),
            runtime(
                "selected_hunter_combat_area_bit_special", source + f" 的 bit {special}"
            ),
        ),
    )
    queried_area = runtime(
        "unfair_point_combat_area_no",
        "EnemyManager.getAreaNoNearPoint(本次检测位置, ST103) 的 Int32 返回值",
    )
    far_area = combined(
        "any",
        combined(
            "all",
            current_area(special, "ne"),
            compare(
                "unfair_point_combat_area_no", special, source=queried_area["source"]
            ),
        ),
        combined(
            "all",
            current_area(special),
            compare(
                "unfair_point_combat_area_no",
                special,
                "ne",
                source=queried_area["source"],
            ),
        ),
    )
    first = runtime(
        "unfair_voxel_first_query_succeeded",
        "本次 getDataInfoForNav 的第一次查询返回值；位置取玩家 GroundInfo.Pos，缺失则取 Transform.Pos",
    )
    transform = runtime(
        "selected_hunter_transform_valid", "所选玩家 GameObject.Transform 引用存在"
    )
    ground = runtime(
        "selected_hunter_ground_info_exists", "CharacterBase.get_GroundInfo 返回非空"
    )
    error = dict(
        kind="unknown",
        reason="此路径需要读取所选玩家Transform.Pos；GameObject或Transform缺失时调用错误处理0x46并终止正常路径，不是普通false返回",
    )
    area = combined(
        "any",
        combined(
            "all",
            transform,
            combined(
                "any",
                combined("all", near, near_area),
                combined("all", invert(near), far_area),
            ),
        ),
        combined("all", invert(transform), error),
    )
    terrain = combined(
        "any",
        invert(first),
        combined(
            "all",
            first,
            combined(
                "any",
                combined(
                    "all",
                    category(2, "ne"),
                    runtime(
                        "unfair_voxel_first_nav_attr:10",
                        "第一次查询命中体素的 _NavNodeAttrArray[_IndexNavNodeAttr] bit10",
                    ),
                ),
                combined(
                    "all",
                    runtime(
                        "unfair_voxel_second_query_succeeded",
                        "本次 getDataInfoForNav 第二次查询的返回值（同位置，参数10、5、1）",
                    ),
                    runtime(
                        "unfair_voxel_second_nav_attr:27",
                        "第二次查询命中体素的 _NavNodeAttrArray[_IndexNavNodeAttr] bit27",
                    ),
                ),
                combined(
                    "all",
                    compare("self_current_stage_no", 2, source=FIELDS["stage_no"]),
                    area,
                ),
            ),
        ),
    )
    source_valid = combined("any", ground, transform)
    return combined(
        "any",
        combined(
            "all",
            runtime(
                "selected_hunter_base_action_exists",
                "所选玩家 BaseActionController.CurrentAction 不为空",
            ),
            runtime(
                "selected_hunter_base_action_is_hunter_action",
                "当前动作通过 cHunterActionBase 类型检查",
            ),
            runtime(
                "selected_hunter_action_attr:29",
                "当前动作 _Attr 中 TARZAN_ATTACH（bit29），不是ContinueFlag294",
            ),
        ),
        combined(
            "all",
            source_valid,
            terrain,
        ),
        combined("all", invert(source_valid), error),
    )


def unfair_inputs():
    definitions = {
        "selected_target_key_unique_high_bit_clear": "所选玩家访问键的UniqueIndex高位为0",
        "self_permanent_flag:129": "自身永久标志DISABLE_CHECK_UNFAIR已设置",
        "self_continue_flag:129": "自身持续标志DISABLE_CHECK_UNFAIR已设置",
        "selected_hunter_base_action_exists": "目标玩家存在当前基础动作",
        "selected_hunter_base_action_is_hunter_action": "目标玩家基础动作属于 cHunterActionBase",
        "selected_hunter_action_attr:29": "目标玩家当前基础动作具有 TARZAN_ATTACH 属性",
        "selected_hunter_ground_info_exists": "目标玩家存在当前GroundInfo",
        "selected_hunter_transform_valid": "目标玩家存在有效的GameObject.Transform",
        "unfair_voxel_first_query_succeeded": "目标位置的第一次导航体素查询成功",
        "unfair_voxel_first_nav_attr:10": "第一次命中体素的导航节点属性 bit10",
        "unfair_voxel_second_query_succeeded": "目标位置的第二次导航体素查询成功",
        "unfair_voxel_second_nav_attr:27": "第二次命中体素的导航节点属性 bit27",
        "selected_hunter_combat_area_bit_current": "目标玩家的合并战斗区域位包含自身当前区域",
        "selected_hunter_combat_area_bit_special": "目标玩家的合并战斗区域位包含特殊区域17",
    }
    result = {
        key: dict(label=label, boolean=True) for key, label in definitions.items()
    }
    result["self_basic_category"] = dict(
        label="自身怪物分类",
        options=[
            dict(label=name, value=value)
            for name, value in (("BOSS", 0), ("ZAKO", 1), ("ANIMAL", 2))
        ],
    )
    result["unfair_ground_transform_distance_squared"] = dict(
        label="目标检测位置与玩家Transform位置的三维距离平方",
        number=True,
        min=0,
        max=None,
        unit="游戏坐标单位的平方",
    )
    result["unfair_point_combat_area_no"] = dict(
        label="getAreaNoNearPoint 返回的战斗区域编号",
        number=True,
        min=-(1 << 31),
        max=(1 << 31) - 1,
    )
    return result


def unfair_guard():
    return combined(
        "all",
        runtime("self_target_context_valid", FIELDS["target_context_unfair"]),
        compare(
            "selected_target_key_type",
            0,
            source="Target.getTarget(requireValid=True, slot=0)：命令只接受PLAYER键",
        ),
        runtime(
            "selected_target_key_unique_high_bit_clear",
            FIELDS["unique_index_mask"],
        ),
        runtime(
            "selected_hunter_lookup_found",
            FIELDS["hunter_lookup"],
        ),
        runtime(
            "selected_hunter_character_valid",
            FIELDS["hunter_character"],
        ),
        invert(
            runtime(
                "self_permanent_flag:129",
                "cEnemyContext._PermanentFlag 中 DISABLE_CHECK_UNFAIR 位",
            )
        ),
        invert(
            runtime(
                "self_continue_flag:129",
                "cEnemyContext.ContinueFlag 中 DISABLE_CHECK_UNFAIR 位",
            )
        ),
        invert(
            combined(
                "any",
                compare(
                    "self_current_stage_no",
                    13,
                    source=FIELDS["stage_no_unfair"],
                ),
                combined(
                    "all",
                    compare(
                        "self_current_stage_no",
                        10,
                        source=FIELDS["stage_no_short"],
                    ),
                    compare("self_current_area_no", 4, source=FIELDS["area_no_short"]),
                ),
            )
        ),
        unfair_qualification(),
    )


# Raw inputs of the voxel terrain commands (queryContracts.voxel_terrain).
HEIGHT = runtime(
    "distance:2:0",
    "get_TargetPosition.y − ThisObject.Transform 位置的 y（cCheckDistance 高度轴的同一个量）",
)
VOXEL_READY = runtime(
    "voxel_manager_valid",
    "全局 VoxelDataManager 实例存在，且其 +0x10 不为空",
)
VOXEL_INFO = runtime(
    "voxel_self_info_found",
    "本次 getDataInfoEmAuto（ContextHolder.Transform._Position）的返回值",
)


def terrain_rise(argument):
    """cCheckRise: the target is at least CheckHeight above, unless the voxel
    ceiling over the monster is lower than that height.

    Native (0x146e50cb0): h = target.y − self.y; the check continues when
    CheckHeight <= h or the compare is unordered; Stage 1 Area 6 is false;
    a missing voxel manager or a failed query is true; with
    v = float(double(info._Pos.y) + double(getCeilingDist) − double(position.y))
    the result is false only when v > 0 and h > v.
    """
    height = scalar(argument.get("_CheckHeight"))
    if type(height) not in (int, float):
        return None
    clearance = runtime(
        "voxel_ceiling_clearance",
        "float(double(DATA_INFO._Pos.y) + double(getCeilingDist(DATA_INFO)) − "
        "double(ContextHolder.Transform._Position.y))；原生以双精度计算后转单精度",
    )
    return combined(
        "all",
        invert(compare("distance:2:0", float(height), "lt", source=HEIGHT["source"])),
        invert(
            combined(
                "all",
                compare("self_current_stage_no", 1, source=FIELDS["stage_no"]),
                compare("self_current_area_no", 6, source=FIELDS["area_no"]),
            )
        ),
        combined(
            "any",
            invert(VOXEL_READY),
            invert(VOXEL_INFO),
            invert(
                dict(
                    kind="compare",
                    operator="gt",
                    left=clearance,
                    right=dict(kind="constant", value=0.0),
                )
            ),
            invert(dict(kind="compare", operator="gt", left=HEIGHT, right=clearance)),
        ),
    )


def terrain_to_destination():
    """cCheckTerrainToDestination (0x1476150f0).

    Needs the voxel manager, a found DATA_INFO and no wall on the way. When
    the monster is not below the target (!(self.y <= target.y)), the result
    is info._Pos.y <= target.y (setbe: also when unordered); otherwise it is
    ceiling < 0 or info._Pos.y + ceiling >= target.y (negated compares, so an
    unordered value also passes).
    """
    target_y = runtime("target_position_y", "get_TargetPosition 的 y 分量")
    info_y = runtime("voxel_self_info_y", "本次 DATA_INFO._Pos.y")
    ceiling = runtime("voxel_ceiling_distance", "getCeilingDist(DATA_INFO) 的返回值")
    ceiling_y = runtime(
        "voxel_ceiling_y", "DATA_INFO._Pos.y + getCeilingDist(DATA_INFO)（单精度相加）"
    )
    below = compare("distance:2:0", 0.0, "ge", source=HEIGHT["source"])
    return combined(
        "all",
        VOXEL_READY,
        VOXEL_INFO,
        invert(
            runtime(
                "voxel_wall_blocks_target",
                "本次 isBlockByWall(DATA_INFO, 目标−自身位置, 其水平长度) 的返回值",
            )
        ),
        combined(
            "any",
            combined(
                "all",
                invert(below),
                invert(
                    dict(kind="compare", operator="gt", left=info_y, right=target_y)
                ),
            ),
            combined(
                "all",
                below,
                combined(
                    "any",
                    invert(
                        dict(
                            kind="compare",
                            operator="ge",
                            left=ceiling,
                            right=dict(kind="constant", value=0.0),
                        )
                    ),
                    invert(
                        dict(
                            kind="compare",
                            operator="lt",
                            left=ceiling_y,
                            right=target_y,
                        )
                    ),
                ),
            ),
        ),
    )


def occlusion_hits(context):
    """Evaluate the native loop over ray hits, with raw keys and gimmick IDs.

    A hit's key is the output of TargetAccessKeyUtil.makeTargetAccessKey, rather
    than an invented collider classification. A found gimmick can be passed
    through only when its actual GmId occurs in _OccludedCheckThroughGmIDs.
    """
    if "destination_occlusion_ray_hits" not in context:
        raise MissingState("缺少本次 TERRAIN_EM_SIGHT 射线命中列表")
    hits = context["destination_occlusion_ray_hits"]
    if not isinstance(hits, list):
        raise MissingState("射线命中列表无效")
    unknown = None
    for hit in hits:
        try:
            if not isinstance(hit, dict) or type(hit.get("key_category")) is not int:
                raise MissingState("命中对象缺少原生 TARGET_ACCESS_KEY.Category")
            if hit["key_category"] != 4:
                return True
            if type(hit.get("key_unique_index")) is not int:
                raise MissingState("GIMMICK 命中缺少原生 UniqueIndex")
            special = context.get("occlusion_special_gimmick_unique_index")
            if type(special) is not int:
                raise MissingState(FIELDS["special_gimmick_missing"])
            if hit["key_unique_index"] == special:
                return True
            if type(hit.get("gimmick_lookup_found")) is not bool:
                raise MissingState("缺少本次 getGimmickUniqueIndex 的对象查找结果")
            if not hit["gimmick_lookup_found"]:
                return True
            if type(hit.get("gimmick_game_object_valid")) is not bool:
                raise MissingState("缺少查到的 GimmickBaseApp.GameObject 有效性")
            if not hit["gimmick_game_object_valid"]:
                return True
            gimmick_id = hit.get("gimmick_id")
            through = context.get("self_occluded_check_through_gimmick_ids")
            if type(gimmick_id) is not int or not isinstance(through, list):
                raise MissingState("缺少实际 GmId 或 Target._OccludedCheckThroughGmIDs")
            if any(type(value) is not int for value in through):
                raise MissingState("遮挡穿透列表不是原生 GimmickDef.ID 数组")
            if gimmick_id not in through:
                return True
        except MissingState as error:
            unknown = error
    if unknown is not None:
        raise unknown
    return False


def recover_navigation_condition(node):
    command = node.get("commandType", node.get("expectedCommandType", ""))
    if not command.startswith(COMMON_COMMAND_PREFIX):
        return None
    name = command.rsplit(".", 1)[-1]
    guard = runtime(
        "enemy_command_work_valid",
        FIELDS["command_work_valid_short"],
    )
    if name == "cCheckDestinationRelation":
        result = destination_relation(node["argument"])
        if result is not None:
            result["expression"] = combined("all", guard, result["expression"])
        return result
    if name == "cCheckRise":
        expression = terrain_rise(node.get("argument") or {})
        if expression is None:
            return None
        return dict(
            expression=combined("all", guard, expression),
            summary="目标比自身高出指定高度，且头顶空间允许升高",
            semanticStatus="reviewed_native_semantics",
            semanticEvidence=deepcopy(receipt()["evidence"]["terrain_rise"]),
            detail="目标与自身的高度差须不小于参数 CheckHeight；Stage 1 Area 6 恒为假。体素管理器或体素查询不可用时为真；否则只有头顶净空大于 0 且小于高度差时为假。距离单位未核实。",
            queryContract=deepcopy(receipt()["queryContracts"]["voxel_terrain"]),
        )
    if name == "cCheckTerrainToDestination":
        return dict(
            expression=combined("all", guard, terrain_to_destination()),
            summary="自身所在体素地形允许到达目标高度",
            semanticStatus="reviewed_native_semantics",
            semanticEvidence=deepcopy(receipt()["evidence"]["terrain_to_destination"]),
            detail="需要体素管理器、查到自身位置的体素信息且途中没有墙阻挡。自身高于目标时，要求体素地面不高于目标；否则要求天花板距离为负或天花板高度不低于目标。",
            queryContract=deepcopy(receipt()["queryContracts"]["voxel_terrain"]),
        )
    if name == "cCheckUnfairRoutineActive":
        return dict(
            expression=combined("all", guard, unfair_guard()),
            summary="目标通过有效性与不公平行为资格检查",
            semanticStatus="reviewed_partial_native_semantics",
            semanticEvidence=deepcopy(receipt()["evidence"]["unfair_active"]),
            inputDefinitions=unfair_inputs(),
            queryContract=deepcopy(receipt()["queryContracts"]["unfair_active"]),
            detail="有效玩家及禁用标志、Stage/Area守卫通过后，按TARZAN_ATTACH动作属性、两次体素查询的实际返回和节点属性、ST103区域关系判断；真分支才写IsActiveUnfairRoutine=true。查询输入只表示具体查询的正常返回，缺失引用导致原生错误时不提供查询结果。",
        )
    if name == "cCheckOccludedToDest":
        selected = (
            "Target.getTarget(requireValid=True, slot=0) 的 TARGET_ACCESS_KEY.Category"
        )
        return dict(
            expression=combined(
                "all",
                guard,
                invert(
                    runtime(
                        "self_permanent_flag:128",
                        "cEnemyContext._PermanentFlag 中 DISABLE_CHECK_OCCLUDED 位",
                    )
                ),
                invert(
                    runtime(
                        "self_continue_flag:128",
                        "cEnemyContext.ContinueFlag 中 DISABLE_CHECK_OCCLUDED 位",
                    )
                ),
                combined(
                    "any",
                    *(
                        compare("selected_target_key_type", value, source=selected)
                        for value in (0, 1, 2, 4, 5)
                    ),
                ),
                compare(
                    "occlusion_ray_length_squared",
                    2500.0,
                    "lt",
                    source=FIELDS["occlusion_length"],
                ),
                dict(
                    kind="predicate",
                    predicate=dict(
                        status="verified",
                        kind="occlusion_hits",
                        values={},
                        summary="TERRAIN_EM_SIGHT至少有一项命中未被GIMMICK穿透列表过滤",
                    ),
                ),
            ),
            summary="目标与自身之间存在未被过滤的遮挡物",
            semanticStatus="reviewed_native_semantics",
            semanticEvidence=deepcopy(receipt()["evidence"]["occluded"]),
            detail="禁用遮挡检查的永久/持续标志均返回假；射线检测范围严格小于50的距离平方，命中物还需通过GIMMICK过滤。距离单位未核实。",
            queryContract=dict(
                queryType=OCCLUSION_QUERY["queryType"],
                queryTypeValue=33,
                targetKeysAccepted=[0, 1, 2, 4, 5],
                rayLengthSquaredLimit=2500.0,
                comparison="strictly_less",
                specialGimmickIndexGlobal=OCCLUSION_QUERY["specialGimmickIndexGlobal"],
                throughIdField=OCCLUSION_QUERY["throughIdField"],
                hitKeySource=OCCLUSION_QUERY["hitKeySource"],
                scope="只计算已知原始查询结果的分支；不模拟物理场景或读取_IsOccludedToDest作为命令结果",
            ),
        )
    return None
