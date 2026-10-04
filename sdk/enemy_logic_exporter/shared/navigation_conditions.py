"""Reviewed navigation guards; unresolved physical filters stay explicit.

Inputs name query outputs and individual native fields, never the final command
or EnemyUtil result. The Boolean bit inputs are snapshots of the named raw bit,
not a substitute for running the whole condition helper.
"""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from .values import MissingState, enum_number


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        Path(__file__)
        .with_name("navigation_condition_evidence.v1.json")
        .read_text(encoding="utf8")
    )


def field(key, source):
    return dict(kind="runtime", key=key, source=source)


def compare(key, value, operator="eq", *, source):
    return dict(
        kind="compare",
        operator=operator,
        left=field(key, source),
        right=dict(kind="constant", value=value),
    )


def combine(kind, *items):
    return dict(kind=kind, items=list(items))


def invert(item):
    return dict(kind="not", item=item)


def bit(member, index):
    return field(
        f"destination_wall:{member}:bit:{index}",
        f"本次 getWallInfoNearVector 输出 WALL_INFO._Data.{member} 的 bit {index}；原始位值",
    )


def category(value, operator="eq"):
    return compare(
        "self_basic_category",
        value,
        operator,
        source="cEnemyContext.Basic.Category（0x108→0x54）；0 BOSS、1 ZAKO、2 ANIMAL",
    )


def destination_relation(argument):
    relation = enum_number(argument["_EditType"])
    if relation not in (0, 1):
        return None
    source = "本次目标/Nullable 覆盖位置减去 holder.Transform.Pos 的 vec3"
    prefix = [
        field(
            "self_target_context_valid",
            "Accessor.TargetContext 存在（命令工作0x28→0x68）",
        ),
        field(
            "destination_nav_query_succeeded",
            "getDataInfoForNav（0x14563bf40）查询自身位置成功",
        ),
        field(
            "self_target_module_valid",
            "holder.Em.Target（0x40→0x100）非空；覆盖位置存在时仍检查",
        ),
        combine(
            "any",
            field(
                "destination_override_has_value",
                "命令复制的 Nullable<vec3>._HasValue；0x1547cabf0，不假定其运行时值",
            ),
            field(
                "destination_target_position_has_value",
                "Target.getTargetPosition(0, false)（0x1469cc720）的 Nullable 有值",
            ),
        ),
        field(
            "destination_wall_query_succeeded",
            "getWallInfoNearVector（0x145507880）查询目标位移方向成功",
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
            left=field("destination_wall_distance", "WALL_INFO._Data._Dist"),
            right=field(
                "destination_displacement_length",
                source + "的长度；原生 sqrt(x²+y²+z²)",
            ),
        ),
    ]
    if relation == 1:
        classification = combine(
            "any",
            bit("_Attribute1", 4),
            combine("all", category(0), bit("_MaskBits", 8)),
            combine("all", category(0, "ne"), bit("_MaskBits", 13)),
        )
        detail = "LOW 要求目标位移Y严格小于0；墙属性位或按大型/其他怪物分类选择的 MaskBits 也必须匹配。查询失败、禁止导航属性或墙距离越界均返回假。"
    else:
        classification = combine(
            "any",
            combine("all", category(0), bit("_NaviAttribute", 5)),
            combine("all", category(1), bit("_NaviAttribute", 6)),
            bit("_Attribute1", 1),
            bit("_Attribute1", 8),
            bit("_Attribute1", 9),
            combine(
                "all",
                compare(
                    "self_current_area_no",
                    2,
                    source="cEnemyContext.Area._CurrentAreaNo（0x1d8→0xe0）；不是AI状态",
                ),
                compare(
                    "self_current_stage_no",
                    0,
                    source="cEnemyContext.Area._CurrentStageNo（0x1d8→0x14）",
                ),
                combine("any", bit("_Attribute1", 7), bit("_MaskBits", 31)),
                dict(
                    kind="unknown",
                    reason="HIGH 物理回退要求本次 TERRAIN_CHARACTER 射线至少命中一个有效对象且包含全局0x1547277c8指定的有效组件；组件类型与查询构造仍未完整核实",
                ),
            ),
        )
        detail = "HIGH 常规路径按怪物分类、导航属性与墙属性检查；只有这些路径均不成立时才进入特定区域的物理回退。所有成功路径都要求目标位移Y严格大于0。未把回退命中简化成最终布尔输入。"
    expression = combine(
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


def unfair_guard():
    return combine(
        "all",
        field("self_target_context_valid", "Accessor.TargetContext 存在（0x28→0x68）"),
        compare(
            "selected_target_key_type",
            0,
            source="Target.getTarget(requireValid=True, slot=0)：命令只接受PLAYER键",
        ),
        field(
            "selected_target_key_unique_high_bit_clear",
            "所选 TARGET_ACCESS_KEY.UniqueIndex 的最高位为0；命令掩码0x80000000ffffffff",
        ),
        field(
            "selected_hunter_lookup_found",
            "findHunterContext 返回非空对象（0x1484a3c10）",
        ),
        field(
            "selected_hunter_character_valid",
            "返回对象0x18的HunterCharacter存在，且角色0x10对象非空",
        ),
        invert(
            field(
                "self_permanent_flag:129",
                "cEnemyContext._PermanentFlag 中 DISABLE_CHECK_UNFAIR 位",
            )
        ),
        invert(
            field(
                "self_continue_flag:129",
                "cEnemyContext.ContinueFlag 中 DISABLE_CHECK_UNFAIR 位",
            )
        ),
        invert(
            combine(
                "any",
                compare(
                    "self_current_stage_no",
                    13,
                    source="Area._CurrentStageNo（0x14）；原生命令最后参数=true",
                ),
                combine(
                    "all",
                    compare(
                        "self_current_stage_no",
                        10,
                        source="Area._CurrentStageNo（0x14）",
                    ),
                    compare(
                        "self_current_area_no", 4, source="Area._CurrentAreaNo（0xe0）"
                    ),
                ),
            )
        ),
        dict(
            kind="unknown",
            reason="checkTargetCharaUnfair 后续玩家状态、体素查询、区域属性及阶段资格尚未完整核实；命令实际参数为false、Nullable<float>、false、true",
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
                raise MissingState("缺少全局0x15480a9b0的特殊GIMMICK索引")
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


def recover_navigation_condition(node, profile):
    if profile != receipt()["profile"]:
        raise ValueError("导航条件配方与来源版本不匹配")
    command = node.get("commandType", node.get("expectedCommandType", ""))
    if not command.startswith("app.btable.EmCommonCommand."):
        return None
    name = command.rsplit(".", 1)[-1]
    guard = field(
        "enemy_command_work_valid",
        "命令工作存在且原生类型身份匹配 cEnemyBTableCommandWork",
    )
    if name == "cCheckDestinationRelation":
        result = destination_relation(node["argument"])
        if result is not None:
            result["expression"] = combine("all", guard, result["expression"])
        return result
    if name == "cCheckUnfairRoutineActive":
        return dict(
            expression=combine("all", guard, unfair_guard()),
            summary="目标通过有效性与不公平行为资格检查",
            semanticStatus="reviewed_partial_native_semantics",
            semanticEvidence=deepcopy(receipt()["evidence"]["unfair_active"]),
            detail="目标必须是有效玩家；禁用标志及特定Stage/Area会拒绝。完整资格仍有未知，真分支才写IsActiveUnfairRoutine=true。",
        )
    if name == "cCheckOccludedToDest":
        selected = (
            "Target.getTarget(requireValid=True, slot=0) 的 TARGET_ACCESS_KEY.Category"
        )
        return dict(
            expression=combine(
                "all",
                guard,
                invert(
                    field(
                        "self_permanent_flag:128",
                        "cEnemyContext._PermanentFlag 中 DISABLE_CHECK_OCCLUDED 位",
                    )
                ),
                invert(
                    field(
                        "self_continue_flag:128",
                        "cEnemyContext.ContinueFlag 中 DISABLE_CHECK_OCCLUDED 位",
                    )
                ),
                combine(
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
                    source="getRayTargetBasePos(_This)/Nullable覆盖位置与getRayTargetBasePos(目标键)之差的 x²+y²+z²；常量0x14dc43cd0=2500",
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
                queryType="app.RAY_CAST_TYPE.TERRAIN_EM_SIGHT",
                queryTypeValue=33,
                targetKeysAccepted=[0, 1, 2, 4, 5],
                rayLengthSquaredLimit=2500.0,
                comparison="strictly_less",
                specialGimmickIndexGlobal="0x15480a9b0",
                throughIdField="app.cEmModuleTarget._OccludedCheckThroughGmIDs (0x70)",
                hitKeySource="app.TargetAccessKeyUtil.makeTargetAccessKey (0x14841eb30)",
                scope="只计算已知原始查询结果的分支；不模拟物理场景或读取_IsOccludedToDest作为命令结果",
            ),
        )
    return None
