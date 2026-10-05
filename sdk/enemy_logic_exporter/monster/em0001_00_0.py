"""Freeze four freshly verified local state machines, not historical EM166 graphs."""

from ..shared.native.evidence import evidence, method_rows

from copy import deepcopy
from pathlib import Path
import json
import re

from ..shared.resources.reader import Resources, typed, structure_signature

SOURCE = (
    "STM/GameDesign/Enemy/Em0001/00/BTable/Em0001_00_BTable_CommonAttack.user.3.json"
)

COMMON = SOURCE
COMBAT = COMMON.replace("CommonAttack", "Combat")

# Version-specific native identities used by this recipe (game 1.42.0.2).
COMMON_ATTACK_EXPORT = "app.Em0001_00_BTable_CommonAttack_Export"
TABLE_METHOD_PREFIX = "table_"
# Reviewed CommonAttack tables, by GUID token of table_<GUID><suffix>.
TABLE_76 = "01313943_0939_4717_b2a4_28a6086cc2c5"
TABLE_48 = "897"
TABLE_11 = "9790fef1_99ef_430a_a05d_f9a41cc5c931"
TABLE_70 = "9a583948_5083_460e_b71a_952eeacdccec"
COMBAT_SELECTOR_TABLE = "b5e627d9"
# Ghidra labels of the six CommonAttack candidate tables, by table index.
CANDIDATE_LABELS = {
    1: "mhws_ff6884737bedd3d6",
    6: "mhws_b27b122f6b524969",
    7: "mhws_f333775b215b4806",
    12: "mhws_7e79ff592c4e4b83",
    14: "mhws_57cbe316ff24dec8",
    73: "mhws_d4562df3f39c6b20",
}
# (selector state, skip argument, static pool VA, candidate tables, PCs).
SELECTOR_POOLS = (
    (1, 444, "0x1547ec588", [14, 1, 7], [2, 4, 6]),
    (9, 448, "0x1547ec430", [1, 12], [10, 12]),
    (15, 450, "0x1547ec530", [1, 12, 73], [16, 18, 20]),
)
# app.cEnemyContext.get_IsAngry / get_IsTired.
STATUS_BINDINGS = {
    "0": dict(contextKey="IsAngry", source="app.cEnemyContext.get_IsAngry"),
    "1": dict(contextKey="IsTired", source="app.cEnemyContext.get_IsTired"),
}
STATUS_GETTERS = ("0x145cbd510", "0x145cc7880")
SKIP_ACTION_ARGUMENT = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
VARIABLE_STORAGE = "ace.btable.cVariableStorage"
TIMER_METHODS = ("setValueTimer", "getValueTimer", "update")


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


def build_local(work, natives, profile):
    document = json.loads((work / "decompiled.json").read_text(encoding="utf-8"))
    rows = method_rows(document)
    definitions = [
        (
            TABLE_76,
            76,
            [
                guard(0, 259, 11, 1, 11),
                guard(1, 260, 10, 2, 10),
                guard(2, 261, 10, 3, 8),
                guard(3, 262, 104, 4, 6),
                action(4, 263, 5),
                timer(5, 264),
                call(8, TABLE_48, 9),
            ],
            [6, 9, 10, 11],
        ),
        (
            TABLE_48,
            48,
            [
                guard(0, 200, 104, 1, 6),
                guard(1, 201, 11, 2, 5),
                action(2, 202, 3),
                call(3, TABLE_11, 4),
                timer(4, 203),
            ],
            [5, 6],
        ),
        (
            TABLE_11,
            11,
            [call(0, TABLE_70, 1), action(1, 56, 2)],
            [2],
        ),
        (
            TABLE_70,
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
            if r["type"] == COMMON_ATTACK_EXPORT
            and r["method"].startswith(TABLE_METHOD_PREFIX + token)
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
            if r["type"] == COMMON_ATTACK_EXPORT
            and r["method"].startswith(TABLE_METHOD_PREFIX + token)
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


# Freeze freshly reviewed Combat selection plus its verified local prefixes.


def build_upstream(work, natives, data, base_model, *, rules_path=None):
    from ..shared.config import MODEL_DIR, RULES_PATH

    data = Path(data)
    rules_path = (
        Path(rules_path)
        if rules_path is not None
        else (
            RULES_PATH
            if data.resolve() == MODEL_DIR.resolve()
            else data / "rules.v1.json"
        )
    )

    def read_rows(name):
        document = json.loads((work / name).read_text(encoding="utf-8"))
        return method_rows(document)

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
        for i, label in CANDIDATE_LABELS.items()
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
    combat = next(
        r
        for r in current
        if r["method"].startswith(TABLE_METHOD_PREFIX + COMBAT_SELECTOR_TABLE)
    )
    combat_guid = guid(combat)
    nodes = [condition(0, 443, 14, 1, "0a"), condition("0a", 447, 14, 9, 15)]
    for state, arg, address, targets, pcs in SELECTOR_POOLS:
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
                        == SKIP_ACTION_ARGUMENT
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
    (data / "em0001.upstream.v1.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rule = next(r for r in rules["rules"] if r["kind"] == "self_status")
    rule["summary"] = (
        "自身状态分类检查；含站立状态、生命比例、部分 AI 状态及怒和疲劳状态"
    )
    rule["statusBindings"] = {k: dict(v) for k, v in STATUS_BINDINGS.items()}
    rule["statusEvidence"] = [
        evidence(r) for r in current if r["address"] in STATUS_GETTERS
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
            if r["type"] == VARIABLE_STORAGE
            and r["method"].startswith(TIMER_METHODS)
        ],
    )
    rules_path.write_text(
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


ENEMY_ID = "EM0001_00_0"
NATIVE_OWNER = "Em0001_00"


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
