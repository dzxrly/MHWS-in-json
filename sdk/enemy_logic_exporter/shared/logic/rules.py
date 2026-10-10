"""Curate verified native semantics into data; never used by the build command."""

from ..native.evidence import evidence, method_rows
import json
from ..native.metadata import Il2cppMetadata
from .monster_rules import rule_specs
from ..config import (
    AI_STATE_ENUM,
    BOOLEAN_COMMAND_FUNC,
    CHECK_STATUS_METHOD_PREFIXES,
    CHECK_STATUS_TYPE,
    COMMAND_RESULT_ENUM,
    COMMAND_RESULT_TYPE,
    DISTANCE_MODIFIER_FIELDS,
    RANDOM_OPERATOR_TYPE,
    RULE_SPECS,
    SET_TIMER_TYPE,
)


def main(work, metadata, output, profile):
    document = json.loads((work / "decompiled.json").read_text(encoding="utf-8"))
    rows = method_rows(document)
    rules = []
    specs = RULE_SPECS + rule_specs()
    with Il2cppMetadata(metadata) as m:
        for (
            type_name,
            kind,
            scope,
            summary,
            offsets,
            context_type,
            context_offset,
        ) in specs:
            row = next(
                r
                for r in rows
                if r["type"] == type_name and r["method"].startswith("onExecute")
            )
            parameters = row.get("parameters", [])
            argument_type = parameters[-1]["type"] if len(parameters) == 2 else None
            fields = m.fields(argument_type) if argument_type else {}
            bindings = {}
            for role, offset in offsets.items():
                matches = [
                    n
                    for n, f in fields.items()
                    if n != "Null"
                    and int(f.get("offset_from_base", "-1"), 16) == offset
                    and not f.get("static")
                ]
                assert len(matches) == 1, (type_name, argument_type, role, matches)
                bindings[role] = matches[0]
            context = None
            if context_type:
                context_fields = m.fields(context_type)
                matches = [
                    n
                    for n, f in context_fields.items()
                    if int(f.get("offset_from_base", "-1"), 16) == context_offset
                    and not f.get("static")
                ]
                assert len(matches) == 1, (context_type, context_offset, matches)
                context = {
                    "type": context_type,
                    "field": matches[0],
                    "offset": hex(context_offset),
                }
            rules.append(
                {
                    "commandType": type_name,
                    "argumentType": argument_type,
                    "kind": kind,
                    "scope": scope,
                    "summary": summary,
                    "bindings": bindings,
                    "contextBinding": context,
                    "evidence": evidence(row),
                }
            )
            if kind == "self_status":
                rules[-1]["relatedEvidence"] = [
                    evidence(r)
                    for r in rows
                    if r["type"] == CHECK_STATUS_TYPE
                    and any(
                        r["method"].startswith(prefix)
                        for prefix in CHECK_STATUS_METHOD_PREFIXES
                    )
                ]
            if kind == "distance":
                for type_name, field_name, offset in DISTANCE_MODIFIER_FIELDS:
                    assert (
                        int(m.fields(type_name)[field_name]["offset_from_base"], 16)
                        == offset
                    )
                rules[-1]["distanceModifiers"] = {
                    "triggerAIState": 3,
                    "aiStateEnum": m.enum(AI_STATE_ENUM)[1],
                    "stateType": DISTANCE_MODIFIER_FIELDS[0][0],
                    "currentField": DISTANCE_MODIFIER_FIELDS[0][1],
                    "pendingField": DISTANCE_MODIFIER_FIELDS[1][1],
                    "moduleType": DISTANCE_MODIFIER_FIELDS[2][0],
                    "scaleField": DISTANCE_MODIFIER_FIELDS[2][1],
                    "offsetField": DISTANCE_MODIFIER_FIELDS[3][1],
                    "defaultScale": 1.0,
                    "defaultOffset": 0.0,
                }
        command_result = {
            "type": COMMAND_RESULT_TYPE,
            "fields": m.fields(COMMAND_RESULT_TYPE),
            "resultType": m.enum(COMMAND_RESULT_ENUM)[1],
        }
        command_result["booleanFlagMeaning"] = (
            "布尔 cCommandFunc 的 Flag 为 onExecute 的真假；此结论不推广到所有返回类型。"
        )
        command_result["evidence"] = evidence(
            next(
                r
                for r in rows
                if r["type"] == BOOLEAN_COMMAND_FUNC
                and r["method"].startswith("execute")
            )
        )
    source_profile = dict(profile)
    semantics = {
        "schemaVersion": 1,
        "profile": source_profile,
        "rules": rules,
        "commandResult": command_result,
        "operatorSemantics": [
            {
                "kind": "weighted_random",
                "summary": "从已筛选候选中按整数权重抽签；随机值低 32 位对总权重取模。候选排除及重复抑制依赖运行时记忆。",
                "evidence": evidence(
                    next(r for r in rows if r["type"] == RANDOM_OPERATOR_TYPE)
                ),
            },
            {
                "kind": "set_timer",
                "summary": "设置类型 0、1、2 分别传给变量存储状态 1、2、3；不从此调用推断默认时长。",
                "evidence": evidence(
                    next(r for r in rows if r["type"] == SET_TIMER_TYPE)
                ),
            },
        ],
        "researchCoverage": {
            "decompiledMethods": len(rows),
            "semanticallyVerifiedRules": len(rules),
        },
        "limits": [
            "缺少运行时状态时返回未知，不默认通过。",
            "原生命令的类型和空指针检查作为有效上下文前提。",
            "距离单位未标定；目标位置不保证始终是玩家。",
            "角度方向计算的特殊 Option 分支尚未固化。",
            "随机抽样函数的分布未核实，权重占比不能当作无条件招式概率。",
        ],
    }
    out = output / "rules.v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(semantics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("FROZEN", len(rules), "rules", out)
