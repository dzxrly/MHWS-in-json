"""Offline analysis entry for EM0002_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0002_00_0"
NATIVE_OWNER = "Em0002_00"


def extract(context):
    """Select this monster's declared tables, imports and native method contexts."""
    return context.extract_enemy(ENEMY_ID, NATIVE_OWNER)


import re
from ..shared.resources import typed


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
    """Recover the declared closure, or the historical two-resource core."""
    if inventory_path is not None or context is not None:
        from ..shared.native_recipe import build_monster

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
    import json
    from collections import defaultdict
    from pathlib import Path

    from ..shared.btable_machine import Machine
    from ..shared.evidence import method_rows
    from ..shared.metadata import Il2cppMetadata
    from ..shared.native import PE, digest, verify_rows
    from ..shared.native_bindings import bind_native
    from ..shared.profile import SUPPORTED_PROFILE
    from ..shared.resources import Resources, structure_signature
    from ..shared.semantic_recovery import _artifact
    from ..shared.static_pools import native_initializer_pools

    index_path, helper_path = Path(native_index), Path(helper_index)
    index = json.loads(index_path.read_text(encoding="utf8"))
    helpers = json.loads(helper_path.read_text(encoding="utf8"))
    profile = index["profile"]
    if profile != helpers["profile"] or profile != SUPPORTED_PROFILE:
        raise ValueError("火龙配方与原生/辅助方法索引的已核查版本不匹配")
    if digest(exe) != profile["exeSha256"]:
        raise ValueError("火龙配方的 EXE 来源变化，必须重新核查")
    common = "STM/GameDesign/Enemy/Em0002/00/BTable/Em0002_00_BTable_CommonAttack.user.3.json"
    combat = common.replace("CommonAttack", "Combat")
    resources = Resources(natives)
    sources = {
        resources.read(source)["_ExportBTableType"]: source
        for source in (combat, common)
    }
    rows = [
        row
        for row in method_rows(index)
        if row["type"] in sources and row["method"].startswith("table_")
    ]
    initializers = [
        row
        for row in method_rows(helpers)
        if row["type"] == "app.Em0002_00_BTable_Combat_Export"
        and row["method"].startswith(".cctor")
    ]
    if len(initializers) != 1 or not rows:
        raise ValueError("火龙本体方法或静态初始化没有唯一来源")
    initializer = initializers[0]
    verify_rows(exe, rows + initializers)
    imports = {}
    with Il2cppMetadata(Path(metadata)) as dump:
        if dump.sha256 != profile["metadataSha256"]:
            raise ValueError("火龙配方的 IL2CPP 来源变化")
        for name in sources:
            imports[name] = {
                int(field["offset_from_base"], 16): field["type"]
                for field in dump.fields(name).values()
                if field.get("offset_from_base")
                and "default" not in field
                and field["type"] in sources
            }
    # Preserve every method context, even when multiple GUIDs share native bytes.
    records, native_cache, by_address = [], {}, defaultdict(list)
    with PE(exe) as pe:
        for row in rows:
            data = _artifact(index_path, index, row)
            start, end = int(row["address"], 16), int(row["end"], 16)
            key = (row["address"], row["nativeSha256"])
            if key not in native_cache:
                native = pe.read(start, end - start)
                native_cache[key] = (
                    native,
                    bind_native(native, start, data["controlFlow"]),
                )
            native, recovered = native_cache[key]
            indices = {
                position["tableIndex"]
                for events in recovered["blocks"].values()
                for event in events
                if event["kind"] == "call"
                for position in event.get("positionArguments", {}).values()
            }
            record = dict(
                row=row,
                native=native,
                code=data["code"].replace("\r", ""),
                tableGuid=row["method"][6:42].replace("_", "-"),
                resource=sources[row["type"]],
                tableIndex=next(iter(indices)) if len(indices) == 1 else -1,
            )
            records.append(record)
            by_address[start].append(record)
        _artifact(helper_path, helpers, initializer)
        pools = native_initializer_pools(
            pe.read(
                int(initializer["address"], 16),
                int(initializer["end"], 16) - int(initializer["address"], 16),
            ),
            int(initializer["address"], 16),
            initializer,
        )
        pools = {pool["address"]: pool for pool in pools}
        tables, selector_evidence = [], []
        for record in records:
            row, source = record["row"], record["resource"]
            body = resources.read(source)
            machine = Machine(
                row,
                record["native"],
                pe,
                body,
                resources.factories(body),
                by_address,
                imports[row["type"]],
            )
            moduli = {
                int(value, 0)
                for value in re.findall(r"% (0x[0-9a-f]+|\d+)", record["code"])
            }
            if len(moduli) == 1 and 0 < max(moduli) <= 100:
                machine.random_modulus = next(iter(moduli))
            machine.build()
            result, selectors = recover_selectors(machine, record["code"], pools, body)
            selector_evidence.extend(
                dict(resource=source, tableGuid=record["tableGuid"], **item)
                for item in selectors
            )
            # Player IDs are local sequence numbers; addresses remain evidence only.
            identities = {
                node["id"]: str(number) for number, node in enumerate(result["nodes"])
            }
            result["entry"] = identities[result["entry"]]
            for node in result["nodes"]:
                node["nativeNodeIdentity"] = node["id"]
                node["id"] = identities[node["id"]]
                for role in ("true", "false", "next", "resume", "fallback"):
                    if role in node:
                        node[role] = identities[node[role]]
                for candidate in node.get("candidates", []):
                    candidate["id"] = identities[candidate["id"]]
            category = "战斗决策" if source == combat else "行动与续招"
            tables.append(
                dict(
                    tableGuid=record["tableGuid"],
                    tableIndex=record["tableIndex"],
                    resource=source,
                    name=category
                    + (
                        f" · 子表 {record['tableIndex']}"
                        if record["tableIndex"] >= 0
                        else " · 共享方法别名"
                    ),
                    evidence={
                        key: row[key]
                        for key in ("type", "method", "address", "end", "nativeSha256")
                    },
                    nativeType=row["type"],
                    nativeMethod=row["method"],
                    flowStatus=(
                        "partial"
                        if any(node["kind"] == "unknown" for node in result["nodes"])
                        else "verified"
                    ),
                    **result,
                )
            )
    document = dict(
        schemaVersion=1,
        documentType="enemy_battle_logic",
        profile=profile,
        enemyId=ENEMY_ID,
        enemyName="火龙",
        entry="b5ab3e58-ebb9-4196-94c3-30b2df1ded6c",
        scope="火龙 Combat 与 CommonAttack 的真实条件、选招及保存恢复位置；整场事件仍在核查",
        limits=[
            "匹配版本的静态恢复，未在游戏中验证",
            "导航内部、尚未核实的条件及整场调度保留边界",
        ],
        tables=tables,
        resources={
            source: dict(
                structureSignature=structure_signature(
                    resources.read(source), resources.factories(resources.read(source))
                )
            )
            for source in (common, combat)
        },
        selectionRecovery=selector_evidence,
        semanticReviewComplete=False,
    )
    if requests_path is not None:
        requests = json.loads(Path(requests_path).read_text(encoding="utf8"))
        if requests["profile"] != profile:
            raise ValueError("火龙动作发现与模型来源版本不匹配")
        expected = {
            item["address"]
            for item in requests["actionRequestBindings"]
            if item["type"] in sources
        }
        actual = {
            node["requestSite"]
            for table in tables
            for node in table["nodes"]
            if node["kind"] == "action"
        }
        document["requestCoverage"] = dict(
            expected=len(expected),
            recovered=len(actual),
            missing=sorted(expected - actual),
            extra=sorted(actual - expected),
        )
    return document


def recover_selectors(machine, code, pools, body):
    start = int(machine.row["address"], 16)
    evidence = []
    cases = list(re.finditer(r"^( +)case (0x[0-9a-f]+|\d+):", code, re.M))
    outer = min((len(m[1]) for m in cases), default=999)
    cases = [m for m in cases if len(m[1]) == outer]
    blocks = {
        int(m[2], 0): code[
            m.end() : cases[i + 1].start() if i + 1 < len(cases) else len(code)
        ]
        for i, m in enumerate(cases)
    }
    for pc, block in blocks.items():
        refs = set(re.findall(r"lRam0000000(1[0-9a-f]+) \+ 0x24", block))
        if len(refs) != 1:
            continue
        address = hex(int(next(iter(refs)), 16))
        pool = pools.get(address)
        skip_offset = re.search(r"\+ 0x18\) \+ (0x[0-9a-f]+|\d+)", block)
        if not pool or not skip_offset:
            continue
        argument_index = (int(skip_offset[1], 0) - 0x20) // 8
        argument_type, argument = typed(body["_CommandArgArray"][argument_index])
        if not argument_type.endswith("cSetSkipActionTblArg"):
            raise ValueError("selector filter argument type changed")
        # The inner switch/if uses the original stored candidate index. Each
        # candidate's outer state is checked against the real native call path.
        first = pc + 1
        candidate_pcs = [first + 2 * i for i in range(len(pool["entries"]))]
        if any(p not in blocks for p in candidate_pcs):
            raise ValueError("native candidate states require review")
        boundary = machine.walk(start, machine.initial(pc))
        if machine.nodes[boundary]["kind"] != "unknown":
            raise ValueError("random block prefix requires review")
        candidates = []
        for i, p in enumerate(candidate_pcs):
            entry = machine.walk(start, machine.initial(p))
            selected = machine.nodes[entry]
            if selected["kind"] != "call":
                raise ValueError("candidate does not bind a child call")
            candidates.append(
                dict(
                    id=machine.state(p),
                    targetTable=selected["targetTable"],
                    weight=pool["entries"][i]["weight"],
                    nativeKey=pool["entries"][i]["nativeKey"],
                    nativeCandidateIndex=i,
                    nativeProgramCounter=p,
                )
            )
        machine.nodes[boundary] = dict(
            id=boundary,
            kind="weighted_random",
            argumentIndex=argument_index,
            expectedArgumentType=argument_type,
            candidates=candidates,
            fallback=machine.state(first),
            staticArray=address,
            initializerEvidence=pool["initializerEvidence"],
            execution="filter_candidates_then_uint32_mod_total_weight_then_first_strict_less_weight",
            selectionEffects={
                "previousTableHash": "原生选择器的具体写入保留在来源代码中",
                "contextFlag14": "候选分支写入的控制标记保留；未转换成招式概率",
            },
        )
        evidence.append(
            dict(
                programCounter=pc,
                staticArray=address,
                entries=pool["entries"],
                candidateStates=candidate_pcs,
            )
        )
    random_choices = re.findall(
        r"\(uint\)\((0x[0-9a-f]+|\d+) < (\w+) % (100)\) \* (0x[0-9a-f]+|\d+) \+ (0x[0-9a-f]+|\d+)",
        code,
    )
    random_boundaries = [
        n
        for n in machine.nodes.values()
        if n["kind"] == "unknown" and n["reason"] == "辅助调用的作用尚未核实：None"
    ]
    if len(random_choices) == len(random_boundaries) == 1:
        threshold, _, modulus, difference, base = random_choices[0]
        node = random_boundaries[0]
        node.update(
            kind="condition",
            expression=dict(
                kind="compare",
                operator="le",
                left=dict(
                    kind="runtime",
                    key="random_uint32_mod_100:" + node["nativeSite"],
                    source="当前原生调用返回的 uint32 随机整数 % 100",
                ),
                right=dict(kind="constant", value=int(threshold, 0)),
            ),
            summary=f"本次随机整数 % 100 ≤ {int(threshold, 0)}",
            detail="按原生整数余数比较选择；随机源分布未在本模型中模拟",
            true=machine.state(int(base, 0)),
            false=machine.state(int(base, 0) + int(difference, 0)),
        )
        node.pop("reason", None)
    result = machine.build()

    def resolve(key):
        while key in machine.states:
            key = machine.states[key]
        return key

    for node in result["nodes"]:
        if node["kind"] == "weighted_random":
            for c in node["candidates"]:
                c["id"] = resolve(c["id"])
            node["fallback"] = resolve(node["fallback"])
    return result, evidence
