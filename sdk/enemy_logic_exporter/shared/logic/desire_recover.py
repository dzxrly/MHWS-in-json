"""Partial request effects of cRequestActionDesireRecover.

The source GUID is not the final converted ACTION_ID. The caller may continue
only after the explicitly retained conversion/cache boundary returns normally.
"""

from copy import deepcopy
from functools import lru_cache
import json
import uuid

from ..config import CONDITION_FIELDS as FIELDS, EVIDENCE_DIR
from ..native.symbols import method_stem
from .expressions import combined, compare, runtime
from .values import MissingState, scalar

COMMAND = "app.btable.EmCommonCommand.cRequestActionDesireRecover"
ARGUMENT = "app.btable.EmCommonCommand.cSelectActionDesireRecoverArg"
EVIDENCE_FILE = "desire_recover.v1.json"
STATE_UPDATES = {
    "context:_FlagArray[WAITING_REQUEST_ACTION_RANDOM_OPERATOR]": False,
    "context:Life._IsRequestClearLifeActInfo": True,
    "context:_FlagArray[NO_REQUEST_ACTION]": False,
}


@lru_cache(maxsize=1)
def receipt():
    return json.loads((EVIDENCE_DIR / EVIDENCE_FILE).read_text(encoding="utf8"))


def _method(metadata, row):
    name = row["methodBaseName"]
    found = [
        (method, details)
        for method, details in (metadata.get(row["type"]) or {})
        .get("methods", {})
        .items()
        if method_stem(method) == name
        and [parameter.get("type") for parameter in details.get("params", [])]
        == row["parameters"]
        and [parameter.get("modifier") for parameter in details.get("params", [])]
        == row["parameterModifiers"]
        and details.get("returns", {}).get("type") == row["returns"]
        and details.get("impl_flags", "") == row["implFlags"]
    ]
    if len(found) != 1:
        raise ValueError(
            "部分恢复请求的方法身份或签名不唯一：" + row["type"] + "." + name
        )
    return found[0]


def verify_desire_recover(pe, metadata):
    """Check suffix-independent identities, current bytes, fields and enums."""
    proof = receipt()
    if {row["key"]: row["value"] for row in proof["tailWrites"]} != STATE_UPDATES:
        raise ValueError("部分恢复请求的尾部写入声明不一致")
    for row in proof["methods"]:
        _, details = _method(metadata, row)
        start, end = int(row["address"], 16), int(row["end"], 16)
        expected = bytes.fromhex(row["nativeBytes"])
        if (
            int(details.get("function", "0"), 16) != start
            or len(expected) != end - start
            or pe.read(start, end - start) != expected
        ):
            raise ValueError(
                "部分恢复请求的原生实现变化："
                + row["type"]
                + "."
                + row["methodBaseName"]
            )
    for row in proof["fieldChecks"]:
        field = metadata.fields(row["type"]).get(row["field"], {})
        if (
            field.get("type") != row["fieldType"]
            or field.get("offset_from_base") != row["offset"]
        ):
            raise ValueError(
                "部分恢复请求的字段布局变化：" + row["type"] + "." + row["field"]
            )
    for row in proof["enumChecks"]:
        field = (
            (metadata.get(row["type"]) or {}).get("fields", {}).get(row["field"], {})
        )
        if field.get("default") != row["value"]:
            raise ValueError("部分恢复请求的标志位枚举变化：" + row["field"])
    # Resolve the type-guard global through the checked method's RIP operand.
    # No absolute class-symbol slot becomes a second dispatch identity.
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    for check in proof["classChecks"]:
        row = next(
            row
            for row in proof["methods"]
            if row["type"] == check["type"]
            and row["methodBaseName"] == check["methodBaseName"]
        )
        address = int(row["address"], 16) + check["instructionOffset"]
        instruction = next(decoder.disasm(pe.read(address, 15), address), None)
        if instruction is None or instruction.mnemonic != "cmp":
            raise ValueError("部分恢复请求的工作类型检查指令变化")
        operand = instruction.operands[check["operandIndex"]]
        if operand.type != CS_OP_MEM or instruction.reg_name(operand.mem.base) != "rip":
            raise ValueError("部分恢复请求的工作类型检查来源变化")
        slot = instruction.address + instruction.size + operand.mem.disp
        expected_type = (metadata.get(check["expectedType"]) or {}).get("address")
        if not expected_type or int.from_bytes(pe.read(slot, 8), "little") != int(
            expected_type, 16
        ):
            raise ValueError("部分恢复请求的工作类型检查身份变化")
    return True


def _evidence():
    return [
        {key: row[key] for key in ("type", "method", "address", "end")}
        for row in receipt()["methods"]
    ]


def _guid(argument, field):
    value = scalar(argument.get(field))
    if not isinstance(value, str):
        raise MissingState("部分恢复请求缺少来源 GUID：" + field)
    try:
        uuid.UUID(value)
    except ValueError as error:
        raise MissingState("部分恢复请求的来源 GUID 无效：" + field) from error
    return value


def desire_recover_effect(bound, evidence, *, metadata=None, pe=None):
    """Return a guarded partial mutation and separately guarded tail writes.

    ``stateUpdates`` belong after normal return of the unresolved boundary,
    including when the actor/network guard skips the core request. They are
    instantaneous context facts, not persistent BTable history.
    """
    if bound.get("commandType") != COMMAND:
        return None
    command = receipt()["methods"][0]
    if (
        not evidence
        or evidence.get("type") != COMMAND
        or method_stem(evidence.get("method", "")) != command["methodBaseName"]
        or any(evidence.get(key) != command[key] for key in ("address", "end"))
    ):
        raise ValueError("部分恢复请求与已核实原生入口不匹配")
    if (metadata is None) != (pe is None):
        raise ValueError("核对部分恢复请求需要同时提供 PE 与元数据")
    if pe is not None:
        verify_desire_recover(pe, metadata)
    if bound.get("argumentType") != ARGUMENT:
        raise ValueError("部分恢复请求的参数类型不匹配")
    argument = bound.get("argument") or {}
    asset = scalar(argument.get("_EditAssetIndex"))
    if type(asset) is not int:
        raise MissingState("部分恢复请求缺少整数资产索引")
    source = dict(
        kind="resource_action_selection",
        assetIndex=asset,
        actionGuid=_guid(argument, "_EditActionGuid"),
        parameterVariantGuid=_guid(argument, "_EditBranchedParamGuid"),
        argumentType=ARGUMENT,
        finalActionIdentityKnown=False,
        branchedParamGuidReadByCommand=False,
        editTypeReadByCommand=False,
    )
    guard = combined(
        "all",
        runtime("enemy_command_work_valid", FIELDS["command_work_valid_request"]),
        dict(
            kind="not",
            item=runtime("btable_request_action_mask", FIELDS["request_mask"]),
        ),
    )
    actor_guard = combined(
        "any",
        dict(
            kind="not",
            item=runtime("request_actor_net_info_exists", FIELDS["actor_net_info"]),
        ),
        compare(
            "request_actor_host_member_index", -1, source=FIELDS["actor_host_index"]
        ),
        dict(
            kind="compare",
            operator="eq",
            left=runtime("request_actor_host_member_index", FIELDS["actor_host_index"]),
            right=runtime(
                "request_actor_self_member_index", FIELDS["actor_self_index"]
            ),
        ),
    )
    flags = receipt()["tailWrites"]
    effects = [
        dict(
            field=row["field"],
            value=row["value"],
            offset=row["offset"],
            sourceKey=row["key"],
            applyWhen="requestGuard true and command returns normally; independent of actorRequestGuard",
        )
        for row in flags
    ]
    boundary = "请求来源经过参数缓存和 Extend.convertAction 后，最终 ACTION_ID 仍未知；转换可重定向动作并修改 FieldPitfall 状态。保留这一边界，正常返回后才应用已核实尾部写入并沿调用方真实 next 继续。"
    return dict(
        kind="mutation",
        effect="request_desire_recovery",
        summary="登记部分已核实的动作恢复请求",
        requestImplementation="desire_recovery_partial",
        requestGuard=guard,
        actorRequestGuard=actor_guard,
        requestSource=source,
        convertedActionId=dict(
            status="unknown",
            source="app.cEnemyExtendBase.convertAction output",
            resourceGuidIsFinalIdentity=False,
        ),
        requestEffects=effects,
        stateUpdates=dict(STATE_UPDATES),
        stateUpdateTiming="after_unresolved_boundary_normal_return",
        stateUpdatesPersistent=False,
        writeFacts=deepcopy(flags),
        actorRequestContract=deepcopy(receipt()["actorRequestContract"]),
        argumentCacheBoundary=deepcopy(receipt()["argumentCacheBoundary"]),
        conversionBoundary=deepcopy(receipt()["conversionBoundary"]),
        executionOrder=[
            "requestGuard",
            "getActionID cache/asset lookup",
            "Extend.convertAction",
            "actorRequestGuard controls requestActionCore only",
            "three tail writes after normal return",
            "native caller next",
        ],
        semanticEvidence=[dict(evidence), *_evidence()[1:]],
        commandEffectsComplete=False,
        implementationBoundary=boundary,
        invalidateSnapshot=True,
        returnType="System.Void",
        continuationStatus="native_caller_continuation",
        continuationAfterBoundary="only after normal return; no Boolean success and no action-completion guarantee",
    )
