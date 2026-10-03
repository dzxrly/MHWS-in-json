"""Curate verified native semantics into data; never used by the build command."""

import json

from ..metadata import Il2cppMetadata


def evidence(row):
    return {k: row[k] for k in ("type", "method", "address", "end", "nativeSha256")}


def main(work, metadata, output, profile):
    document = json.loads((work / "decompiled.json").read_text(encoding="utf-8"))
    rows = document if isinstance(document, list) else document["methods"]
    rules = []
    specs = [
        (
            "app.btable.EmCommonCommand.cCheckDistance",
            "distance",
            "通用",
            "命令距离：XZ/XYZ 使用严格近远比较；Y 轴使用高度比较",
            {
                "threshold": 0x10,
                "compare": 0x18,
                "height": 0x20,
                "axis": 0x28,
                "base": 0x30,
            },
            None,
            None,
        ),
        (
            "app.btable.EmCommonCommand.cCheckAngle",
            "angle",
            "通用",
            "相对指定方向的夹角 ≤ 角度宽度 / 2；包含边界",
            {"base": 0x10, "width": 0x18, "option": 0x20, "option2": 0x28},
            None,
            None,
        ),
        (
            "ace.btable.cCheckTimerValue",
            "timer",
            "通用",
            "指定计时器的剩余值 ≤ 0",
            {"variable": 0x18},
            None,
            None,
        ),
        (
            "ace.btable.cCompareBoolValue",
            "variable_bool",
            "通用",
            "变量布尔值与指定值相等",
            {"variable": 0x18, "value": 0x20},
            None,
            None,
        ),
        (
            "app.btable.Em0021_00BTableCommand.cCheckMushroomType",
            "mushroom",
            "专用",
            "蘑菇类型相等，或当前类型为 5 且要求类型不为 0",
            {"value": 0x10},
            "app.cEm0021_00Extend",
            0x98,
        ),
        (
            "app.btable.Em0021_00BTableCommand.cCheckCatchMushroom",
            "catch_mushroom",
            "专用",
            "拿取物品内部值属于 0、1、2、3、4、5、7",
            {},
            "app.cEm0021_00Extend",
            0xA0,
        ),
        (
            "app.btable.Em0022_00BTableCommand.cCheckBreakFangCount",
            "fang_count",
            "专用",
            "断牙数量：比较类型 0 为 ≥，1 为 ≤，2 为 =",
            {"compare": 0x10, "value": 0x18},
            "app.cEm0022_00Extend",
            0x70,
        ),
        (
            "app.btable.Em0046_00BTableCommand.cCheckElectricLevel",
            "electric",
            "专用",
            "要求电力等级 2 时接受内部值 2 或 3；其余等级使用相等比较",
            {"value": 0x10},
            "app.cEm0046_00Extend",
            0x108,
        ),
        (
            "app.btable.Em0071_00BTableCommand.cCheckStateType",
            "unique_state",
            "专用",
            "专用内部状态相等；不将其解释为全局战斗阶段",
            {"value": 0x10},
            "app.cEm0071_00Extend",
            0xEC,
        ),
    ]
    specs.append(
        (
            "app.btable.EmCommonCommand.cCheckSelfStatus",
            "self_status",
            "通用",
            "自身状态分类检查；已核实站立状态、生命比例和部分 AI 状态",
            {"category": 0x18, "stand": 0x20, "health": 0x38, "ai": 0x40},
            None,
            None,
        )
    )
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
                    if r["type"] == "app.btable.EmCommonCommand.CheckStatus"
                    and any(
                        r["method"].startswith(prefix)
                        for prefix in (
                            "execute123",
                            "execute_StandState",
                            "execute_Health",
                            "execute_AIState",
                        )
                    )
                ]
            if kind == "distance":
                for type_name, field_name, offset in [
                    ("app.cEmAIStateManager", "_CurrentAIStateID", 0xFC),
                    ("app.cEmAIStateManager", "_NextAIStateID", 0xEC),
                    (
                        "app.cEmModuleCombatEm",
                        "<CombatRangeScale>k__BackingField",
                        0x14,
                    ),
                    (
                        "app.cEmModuleCombatEm",
                        "<CombatRangeOffset>k__BackingField",
                        0xB8,
                    ),
                ]:
                    assert (
                        int(m.fields(type_name)[field_name]["offset_from_base"], 16)
                        == offset
                    )
                rules[-1]["distanceModifiers"] = {
                    "triggerAIState": 3,
                    "aiStateEnum": m.enum("app.EnemyDef.AI_STATE_ID")[1],
                    "stateType": "app.cEmAIStateManager",
                    "currentField": "_CurrentAIStateID",
                    "pendingField": "_NextAIStateID",
                    "moduleType": "app.cEmModuleCombatEm",
                    "scaleField": "<CombatRangeScale>k__BackingField",
                    "offsetField": "<CombatRangeOffset>k__BackingField",
                    "defaultScale": 1.0,
                    "defaultOffset": 0.0,
                }
        command_result = {
            "type": "ace.btable.COMMAND_RESULT",
            "fields": m.fields("ace.btable.COMMAND_RESULT"),
            "resultType": m.enum("ace.btable.BTableDef.COMMAND_RESULT_TYPE")[1],
        }
        command_result["booleanFlagMeaning"] = (
            "布尔 cCommandFunc 的 Flag 为 onExecute 的真假；此结论不推广到所有返回类型。"
        )
        command_result["evidence"] = evidence(
            next(
                r
                for r in rows
                if r["type"]
                == "ace.btable.cCommandFunc`2<app.btable.EmCommonCommand.cCheckDistanceArg,System.Boolean>"
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
                    next(r for r in rows if r["type"] == "ace.btable.cOperatorRandom")
                ),
            },
            {
                "kind": "set_timer",
                "summary": "设置类型 0、1、2 分别传给变量存储状态 1、2、3；不从此调用推断默认时长。",
                "evidence": evidence(
                    next(r for r in rows if r["type"] == "ace.btable.cSetTimerValue")
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
