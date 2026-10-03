"""Freeze four freshly verified local state machines, not historical EM166 graphs."""

from ..evidence import method_rows

from pathlib import Path
import json
import re

from src.processed_data.enemy_battle_logic.resources import (
    Resources,
    typed,
    structure_signature,
)

SOURCE = (
    "STM/GameDesign/Enemy/Em0001/00/BTable/Em0001_00_BTable_CommonAttack.user.3.json"
)


def guard(state, argument, command, yes, no):
    return {
        "id": str(state),
        "kind": "condition",
        "argumentIndex": argument,
        "commandIndex": command,
        "true": str(yes),
        "false": str(no),
    }


def action(state, argument, resume):
    return {
        "id": str(state),
        "kind": "action",
        "argumentIndex": argument,
        "commandIndex": 4,
        "resume": str(resume),
        "execution": "request_then_yield",
    }


def timer(state, argument):
    return {
        "id": str(state),
        "kind": "mutation",
        "argumentIndex": argument,
        "commandIndex": 101,
        "next": "return",
        "effect": "set_timer_state",
    }


def call(state, target, resume):
    return {
        "id": str(state),
        "kind": "call",
        "targetTable": target,
        "resume": str(resume),
        "execution": "push_return_position_then_call",
    }


def build(work, natives, profile):
    document = json.loads((work / "decompiled.json").read_text(encoding="utf-8"))
    rows = method_rows(document)
    definitions = [
        (
            "01313943_0939_4717_b2a4_28a6086cc2c5",
            76,
            [
                guard(0, 259, 11, 1, 11),
                guard(1, 260, 10, 2, 10),
                guard(2, 261, 10, 3, 8),
                guard(3, 262, 104, 4, 6),
                action(4, 263, 5),
                timer(5, 264),
                call(8, "897", 9),
            ],
            [6, 9, 10, 11],
        ),
        (
            "897",
            48,
            [
                guard(0, 200, 104, 1, 6),
                guard(1, 201, 11, 2, 5),
                action(2, 202, 3),
                call(3, "9790fef1_99ef_430a_a05d_f9a41cc5c931", 4),
                timer(4, 203),
            ],
            [5, 6],
        ),
        (
            "9790fef1_99ef_430a_a05d_f9a41cc5c931",
            11,
            [call(0, "9a583948_5083_460e_b71a_952eeacdccec", 1), action(1, 56, 2)],
            [2],
        ),
        (
            "9a583948_5083_460e_b71a_952eeacdccec",
            70,
            [guard(0, 254, 14, 1, 2), action(1, 255, 2)],
            [2, 3],
        ),
    ]
    selected = {}
    for token, table_index, nodes, returns in definitions:
        matches = [
            r
            for r in rows
            if r["type"] == "app.Em0001_00_BTable_CommonAttack_Export"
            and r["method"].startswith("table_" + token)
        ]
        assert len(matches) == 1, token
        row = matches[0]
        guid = re.match(r"table_([0-9a-f_]{36})", row["method"])[1].replace("_", "-")
        selected[token] = guid
    resources = Resources(natives)
    body = resources.read(SOURCE)
    factories = resources.factories(body)
    tables = []
    for token, table_index, nodes, returns in definitions:
        row = next(
            r
            for r in rows
            if r["type"] == "app.Em0001_00_BTable_CommonAttack_Export"
            and r["method"].startswith("table_" + token)
        )
        for node in nodes:
            if node["kind"] == "call":
                node["targetTable"] = selected[node["targetTable"]]
            if "argumentIndex" in node:
                node["expectedArgumentType"] = typed(
                    body["_CommandArgArray"][node["argumentIndex"]]
                )[0]
                node["expectedCommandType"] = factories[node["commandIndex"]][
                    "_OrderType"
                ]
        nodes.extend({"id": str(i), "kind": "return", "value": False} for i in returns)
        nodes.append({"id": "return", "kind": "return", "value": False})
        tables.append(
            {
                "tableGuid": selected[token],
                "tableIndex": table_index,
                "entry": "0",
                "nodes": nodes,
                "evidence": {
                    k: row[k]
                    for k in ("type", "method", "address", "end", "nativeSha256")
                },
            }
        )
    model = {
        "schemaVersion": 1,
        "profile": profile,
        "resource": SOURCE,
        "structureSignature": structure_signature(body, factories),
        "referenceResourceSha256": resources.hashes[SOURCE],
        "enemyId": "EM0001_00_0",
        "exportType": body["_ExportBTableType"],
        "tables": tables,
        "entry": selected[definitions[0][0]],
        "scope": "已核实的局部调用链，非怪物战斗总入口",
        "limits": [
            "尚未恢复上层选招、阶段与随机路径，不能据此给出整场战斗的招式概率。",
            "正常执行路径：重启标记以节点 0 开始；终止标记和中断处理未展开。",
            "动作请求之后保留恢复位置，实际动作执行和中断由游戏运行时负责。",
        ],
    }
    print(
        "FROZEN", len(tables), "tables", sum(len(t["nodes"]) for t in tables), "nodes"
    )
    print(
        "GUARDS",
        [
            (n["expectedCommandType"], n["expectedArgumentType"])
            for t in tables
            for n in t["nodes"]
            if n["kind"] == "condition"
        ],
    )
    return model
