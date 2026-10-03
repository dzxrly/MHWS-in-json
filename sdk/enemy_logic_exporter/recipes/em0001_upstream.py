"""Freeze freshly reviewed Combat selection plus its verified local prefixes."""

import json
from copy import deepcopy
import re

from src.processed_data.enemy_battle_logic.resources import (
    Resources,
    typed,
    structure_signature,
)

COMMON = (
    "STM/GameDesign/Enemy/Em0001/00/BTable/Em0001_00_BTable_CommonAttack.user.3.json"
)
COMBAT = COMMON.replace("CommonAttack", "Combat")


def evidence(row):
    return {k: row[k] for k in ("type", "method", "address", "end", "nativeSha256")}


def main(work, natives, data, base_model):
    DATA = data

    def read_rows(name):
        document = json.loads((work / name).read_text(encoding="utf-8"))
        return document if isinstance(document, list) else document["methods"]

    old = read_rows("decompiled.json")
    current = read_rows("continued-python.json")
    weights = json.loads((work / "recovered-weights.json").read_text(encoding="utf-8"))
    source_rows = old + current
    resources = Resources(natives)
    bodies = {p: resources.read(p) for p in (COMMON, COMBAT)}
    factories = {p: resources.factories(bodies[p]) for p in bodies}
    by_label = {
        r["label"]: r
        for r in old
        if r["method"].startswith("table_")
        and r["type"].endswith("CommonAttack_Export")
    }
    guid = lambda row: re.match(r"table_([0-9a-f_]{36})", row["method"])[1].replace(
        "_", "-"
    )
    selected = {
        i: by_label[label]
        for i, label in {
            1: "mhws_ff6884737bedd3d6",
            6: "mhws_b27b122f6b524969",
            7: "mhws_f333775b215b4806",
            12: "mhws_7e79ff592c4e4b83",
            14: "mhws_57cbe316ff24dec8",
            73: "mhws_d4562df3f39c6b20",
        }.items()
    }
    landing = "9a583948-5083-460e-b71a-952eeacdccec"
    far = "01313943-0939-4717-b2a4-28a6086cc2c5"

    def condition(pc, arg, slot, yes, no):
        return dict(
            id=str(pc),
            kind="condition",
            argumentIndex=arg,
            commandIndex=slot,
            true=str(yes),
            false=str(no),
        )

    def call(pc, target, resume):
        return dict(
            id=str(pc),
            kind="call",
            targetTable=target,
            resume=str(resume),
            execution="push_return_position_then_call",
        )

    def action(pc, arg, resume):
        return dict(
            id=str(pc),
            kind="action",
            argumentIndex=arg,
            commandIndex=4,
            resume=str(resume),
            execution="request_then_yield",
        )

    def mutation(pc, arg, slot, next_node):
        return dict(
            id=str(pc),
            kind="mutation",
            argumentIndex=arg,
            commandIndex=slot,
            next=str(next_node),
            effect="set_timer_state" if slot == 101 else "set_float_value",
        )

    def end(pc):
        return dict(id=str(pc), kind="return", value=False)

    def unknown(pc, reason):
        return dict(id=str(pc), kind="unknown", reason=reason)

    definitions = {
        1: [call(0, landing, 1), action(1, 0, 2), end(2)],
        6: [
            call(0, landing, 1),
            condition(1, 21, 11, 2, 3),
            action(2, 22, 3),
            condition(3, 23, 104, 5, 8),
            condition(4, 23, 104, 5, 8),
            mutation(5, 24, 100, "5a"),
            action("5a", 25, 7),
            mutation(7, 27, 100, "return"),
            action(8, 26, 9),
            mutation(9, 27, 100, "return"),
            end("return"),
        ],
        12: [
            call(0, landing, 1),
            condition(1, 57, 104, 2, 35),
            mutation(2, 58, 101, "2a"),
            condition("2a", 59, 10, 4, 18),
            unknown(
                4, "已定位破坏部位判断及后续分支，尚未固化其部位状态语义和后续动作链"
            ),
            unknown(18, "远距离分支进入另一项部位破坏判断；后续尚未固化"),
            end(35),
            end(36),
        ],
        73: [
            call(0, guid(selected[6]), 1),
            condition(1, 256, 10, 2, 3),
            call(2, far, 3),
            end(3),
            end(4),
        ],
        7: [unknown(0, "已定位原生方法；此候选的局部控制流尚未固化")],
        14: [unknown(0, "已定位原生方法；此候选的局部控制流尚未固化")],
    }
    model = deepcopy(base_model)
    model["resources"] = {
        p: dict(structureSignature=structure_signature(bodies[p], factories[p]))
        for p in bodies
    }
    for table in model["tables"]:
        table["resource"] = COMMON
        table["flowStatus"] = "verified"
    added = []
    for index, nodes in definitions.items():
        row = selected[index]
        added.append(
            dict(
                tableGuid=guid(row),
                tableIndex=index,
                entry="0",
                nodes=nodes,
                resource=COMMON,
                flowStatus="partial" if index in (7, 12, 14) else "verified",
                evidence=evidence(row),
            )
        )
    combat = next(r for r in current if r["method"].startswith("table_b5e627d9"))
    combat_guid = guid(combat)
    nodes = [condition(0, 443, 14, 1, "0a"), condition("0a", 447, 14, 9, 15)]
    pools = [
        (1, 444, "0x1547ec588", [14, 1, 7], [2, 4, 6]),
        (9, 448, "0x1547ec430", [1, 12], [10, 12]),
        (15, 450, "0x1547ec530", [1, 12, 73], [16, 18, 20]),
    ]
    for state, arg, address, targets, pcs in pools:
        pool = weights["pools"][address]
        assert len(pool) == len(targets)
        candidates = [
            dict(
                id=str(pc),
                weight=raw["weight"],
                nativeKey=raw["hash"],
                targetTable=guid(selected[index]),
            )
            for raw, index, pc in zip(pool, targets, pcs)
        ]
        nodes.append(
            dict(
                id=str(state),
                kind="weighted_random",
                argumentIndex=arg,
                commandIndex=53,
                candidates=candidates,
                fallback=str(pcs[0]),
                staticPoolAddress=address,
                weightEvidence=weights["cctorEvidence"],
                eligibility="runtime_skip_list_match",
                selection="uint32_modulo_weight_sum",
                limits=[
                    "权重份额仅适用于进入此节点且候选筛选完成之后；不是无条件招式概率。",
                    "非空跳过列表须由运行时提供匹配结果，不能仅凭 GUID 推测原生字符串键。",
                    "记录选择键及设置运行时标记的副作用保留为证据，未模拟整个游戏状态。",
                ],
            )
        )
        for pc, index in zip(pcs, targets):
            nodes += [call(pc, guid(selected[index]), pc + 1), end(pc + 1)]
    added.append(
        dict(
            tableGuid=combat_guid,
            tableIndex=69,
            entry="0",
            nodes=nodes,
            resource=COMBAT,
            flowStatus="verified",
            evidence=evidence(combat),
        )
    )
    for table in added:
        for node in table["nodes"]:
            if "argumentIndex" in node:
                body = bodies[table["resource"]]
                node["expectedArgumentType"] = typed(
                    body["_CommandArgArray"][node["argumentIndex"]]
                )[0]
                node["expectedCommandType"] = factories[table["resource"]][
                    node["commandIndex"]
                ]["_OrderType"]
                if node["kind"] == "weighted_random":
                    assert (
                        node["expectedArgumentType"]
                        == "app.btable.EmCommonCommand.cSetSkipActionTblArg"
                    )
                    # This is an inline compiled operator, not a command execution.
                    del node["commandIndex"]
                    del node["expectedCommandType"]
    model["tables"] += added
    model["localEntry"] = model["entry"]
    model["entry"] = combat_guid
    model["scope"] = "Combat 表内一个真实选招点及其局部调用链，非整场战斗总入口"
    model["limits"][
        0
    ] = "已恢复一个选招点的疲劳、怒和通常分支；到达本选招点的全局入口仍未恢复。"
    model["limits"].append(
        "部位破坏判断及两个候选仍保留明确未知节点；请求动作后的内部执行条件未展开。"
    )
    (DATA / "em0001.upstream.v1.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rules = json.loads((DATA / "rules.v1.json").read_text(encoding="utf-8"))
    rule = next(r for r in rules["rules"] if r["kind"] == "self_status")
    rule["summary"] = (
        "自身状态分类检查；含站立状态、生命比例、部分 AI 状态及怒和疲劳状态"
    )
    rule["statusBindings"] = {
        "0": dict(contextKey="IsAngry", source="app.cEnemyContext.get_IsAngry"),
        "1": dict(contextKey="IsTired", source="app.cEnemyContext.get_IsTired"),
    }
    rule["statusEvidence"] = [
        evidence(r) for r in current if r["address"] in ("0x145cbd510", "0x145cc7880")
    ]
    rules["timerOperations"] = dict(
        setTypeMap={"0": 1, "1": 2, "2": 3},
        operations={
            "0": "reset_to_default_and_activate",
            "1": "deactivate_without_reset",
            "2": "activate_without_reset",
        },
        update="max(remaining - supplied_delta, 0); deactivate at zero",
        limits=[
            "传入时间增量的来源与单位由调用方决定，不据此断言秒。",
            "常量生命周期不可写；其他运行时所有权和锁不由构建器模拟。",
            "Python 数值运算表达逻辑，非原生 float32 的逐位仿真。",
        ],
        evidence=[
            evidence(r)
            for r in current
            if r["type"] == "ace.btable.cVariableStorage"
            and r["method"].startswith(("setValueTimer", "getValueTimer", "update"))
        ],
    )
    (DATA / "rules.v1.json").write_text(
        json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "FROZEN",
        len(model["tables"]),
        sum(len(t["nodes"]) for t in model["tables"]),
        "nodes",
        3,
        "pools",
    )
