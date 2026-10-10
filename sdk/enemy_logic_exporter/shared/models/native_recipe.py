"""Build each monster from its own declared resources and matched native bytes.

This is the common extraction machinery, not a shared monster behaviour recipe.
Every table and selector is checked against its own method/object context. Failed
checks retain semantic boundaries and never grant release review status.
"""

from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
from ..native.evidence import evidence, method_rows, digest
from ..native.metadata import Il2cppMetadata
from ..native.pe import PE
from ..config import (
    EXTRA_STATE_ENUM,
    FN_STACK_COOKIE_CHECK,
    POSITION_ROW,
    POSITION_TABLE,
    STAND_STATE_ENUM,
    SUPPORTED_PROFILE,
    VOID_TYPE,
)
from ..resources.reader import Resources, structure_signature
from .catalog import EXPECTED_ENEMY_IDS
from ..workflow.semantic_recovery import _artifact
from ..logic.predicates import RuleRegistry


def local_identities(result):
    """Keep native identities as evidence while giving the UI stable local IDs."""
    identities = {node["id"]: str(i) for i, node in enumerate(result["nodes"])}
    result["entry"] = identities[result["entry"]]
    for node in result["nodes"]:
        node["nativeNodeIdentity"] = node["id"]
        node["id"] = identities[node["id"]]
        for role in ("true", "false", "next", "resume", "fallback"):
            if role in node:
                node[role] = identities[node[role]]
        for candidate in node.get("candidates", []):
            field = "nodeId" if "nodeId" in candidate else "id"
            candidate[field] = identities[candidate[field]]
    return result


def resource_table_identities(records):
    """Keep equal GUIDs in distinct resources as distinct executable tables."""
    records = [dict(record) for record in records]
    guid_resources = defaultdict(set)
    for record in records:
        guid_resources[record["tableGuid"]].add(record["resource"])
    for record in records:
        if len(guid_resources[record["tableGuid"]]) > 1:
            record["nativeTableGuid"] = record["tableGuid"]
            suffix = hashlib.sha256(record["resource"].encode("utf8")).hexdigest()[:12]
            record["tableGuid"] += "@" + suffix
    return records


def request_coverage(tables, bindings, sources):
    """Count byte sites separately from resource/type/argument contexts."""
    fields = ("resource", "type", "method", "address", "commandIndex", "argumentIndex")
    expected = {
        tuple(item[key] for key in fields): {key: item[key] for key in fields}
        for item in bindings
        if item["resource"] in sources
    }
    actual = {}
    for table in tables:
        for node in table["nodes"]:
            if node["kind"] != "action" and "parameterBindingBoundary" not in node:
                continue
            item = dict(
                resource=table["resource"],
                type=table["nativeType"],
                method=table["nativeMethod"],
                address=node["requestSite"],
                commandIndex=node["commandIndex"],
                argumentIndex=node["argumentIndex"],
            )
            actual[tuple(item[key] for key in fields)] = item
    expected_sites = {key[3] for key in expected}
    actual_sites = {key[3] for key in actual}
    return dict(
        expected=len(expected_sites),
        recovered=len(actual_sites),
        missing=sorted(expected_sites - actual_sites),
        extra=sorted(actual_sites - expected_sites),
        expectedContexts=len(expected),
        recoveredContexts=len(actual),
        missingContexts=[
            expected[key] for key in sorted(expected.keys() - actual.keys())
        ],
        extraContexts=[actual[key] for key in sorted(actual.keys() - expected.keys())],
        scope="原生字节位置和独立资源、类型、方法、命令与参数上下文分别统计；不表示语义审核完成",
    )


class NativeRecipeContext:
    """One bounded, read-only source session for a complete extraction batch."""

    def __init__(
        self,
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        *,
        inventory_path,
        requests_path=None,
    ):
        self.exe, self.metadata_path = Path(exe), Path(metadata)
        self.index_path, self.helper_path = Path(native_index), Path(helper_index)
        self.index = json.loads(self.index_path.read_text(encoding="utf8"))
        self.helpers = json.loads(self.helper_path.read_text(encoding="utf8"))
        self.inventory = json.loads(Path(inventory_path).read_text(encoding="utf8"))
        self.profile = self.index["profile"]
        documents = [self.helpers, self.inventory]
        self.requests = None
        if requests_path is not None:
            self.requests = json.loads(Path(requests_path).read_text(encoding="utf8"))
            documents.append(self.requests)
        if self.profile != SUPPORTED_PROFILE or any(
            d["profile"] != self.profile for d in documents
        ):
            raise ValueError("原生配方、辅助方法、资源发现及动作请求来源版本不匹配")
        if digest(exe) != self.profile["exeSha256"]:
            raise ValueError("原生配方的 EXE 来源变化，必须重新核查")
        self.resources = Resources(natives)
        self.monsters = {m["enemyId"]: m for m in self.inventory["monsters"]}
        if set(self.monsters) != set(
            EXPECTED_ENEMY_IDS
        ) or self.resources.large_enemy_ids() != set(EXPECTED_ENEMY_IDS):
            raise ValueError("实际资源发现与完整大型怪物范围不一致")
        self.resource_records = {r["resource"]: r for r in self.inventory["resources"]}
        self.rows, self.helper_rows = defaultdict(list), defaultdict(list)
        for row in method_rows(self.index):
            self.rows[row["type"]].append(row)
        for row in method_rows(self.helpers):
            self.helper_rows[row["type"]].append(row)
        self.native_cache, self.record_cache, self.pool_cache = {}, {}, {}
        self.command_cache = {}
        self.leaf_cache = {}
        self.stack = ExitStack()

    def __enter__(self):
        try:
            self.pe = self.stack.enter_context(PE(self.exe))
            self.metadata = self.stack.enter_context(Il2cppMetadata(self.metadata_path))
            if self.metadata.sha256 != self.profile["metadataSha256"]:
                raise ValueError("原生配方的 IL2CPP 来源变化，必须重新核查")
        except BaseException:
            self.stack.close()
            raise
        return self

    def __exit__(self, *args):
        self.stack.close()

    def native(self, row):
        # The profile pins the EXE; cache rows may still carry a byte digest.
        key = row["address"], row["end"], row.get("nativeSha256")
        if key not in self.native_cache:
            start, end = int(row["address"], 16), int(row["end"], 16)
            data = (
                self.pe.read(start, end - start)
                if 0 < end - start <= 2 * 1024 * 1024
                else b""
            )
            if (
                len(data) != end - start
                or "nativeSha256" in row
                and hashlib.sha256(data).hexdigest() != row["nativeSha256"]
            ):
                raise ValueError("原生字节不匹配：" + row["type"] + ":" + row["method"])
            self.native_cache[key] = data
        return self.native_cache[key]

    def record(self, row, source):
        from ..native.bindings import bind_native

        key = row["type"], row["method"], source
        if key not in self.record_cache:
            artifact = _artifact(self.index_path, self.index, row)
            native = self.native(row)
            recovered = bind_native(
                native, int(row["address"], 16), artifact["controlFlow"]
            )
            indices = {
                p["tableIndex"]
                for events in recovered["blocks"].values()
                for e in events
                if e["kind"] == "call"
                for p in e.get("positionArguments", {}).values()
            }
            self.record_cache[key] = dict(
                row=row,
                native=native,
                code=artifact["code"].replace("\r", ""),
                tableGuid=row["method"][6:42].replace("_", "-"),
                resource=source,
                tableIndex=next(iter(indices)) if len(indices) == 1 else -1,
            )
        return self.record_cache[key]

    def pools(self, owner):
        from ..logic.static_pools import native_initializer_pools

        if owner not in self.pool_cache:
            values = {}
            initializers = [
                r for r in self.helper_rows[owner] if r["method"].startswith(".cctor")
            ]
            if not initializers:
                # Missing cached initializers are located in the matched metadata,
                # then parsed from their actual PE bytes; no old pool is reused.
                for method, info in (
                    (self.metadata.get(owner) or {}).get("methods", {}).items()
                ):
                    if method.startswith(".cctor"):
                        start = int(info["function"], 16)
                        end = self.pe.end(start)
                        initializers.append(
                            dict(
                                type=owner,
                                method=method,
                                address=hex(start),
                                end=hex(end),
                                source="matched_metadata_and_current_PE",
                            )
                        )
            for row in initializers:
                if not row["method"].startswith(".cctor"):
                    continue
                if row.get("source") != "matched_metadata_and_current_PE":
                    _artifact(self.helper_path, self.helpers, row)
                for pool in native_initializer_pools(
                    self.native(row),
                    int(row["address"], 16),
                    row,
                    read_memory=self.pe.read,
                ):
                    if pool["address"] in values and values[pool["address"]] != pool:
                        raise ValueError("同一静态选择池有冲突的初始化证据")
                    values[pool["address"]] = pool
            self.pool_cache[owner] = values
        return self.pool_cache[owner]

    def dispatch_root(self, row, records):
        """Trace the actual dispatcher with POSITION.Table=0 to a typed method."""
        from ..logic.machine import Machine, Boundary
        from ..native.bindings import pointer

        machine = Machine(row, self.native(row), self.pe, {}, [], {}, {})
        state = machine.initial(0)
        state["regs"].update(
            r8=pointer("dispatch_position"), r9=pointer("command_work")
        )
        state["mem"].update(
            {
                ("dispatch_position", POSITION_TABLE, 4): 0,
                ("dispatch_position", POSITION_ROW, 4): 0,
                ("stack", 0x28, 8): pointer("operator"),
            }
        )
        address = int(row["address"], 16)
        targets = defaultdict(list)
        for record in records:
            targets[int(record["row"]["address"], 16)].append(record)
        for _ in range(1024):
            if address in targets:
                candidates = targets[address]
                if len(candidates) != 1:
                    candidates = [r for r in candidates if r["tableIndex"] == 0]
                if len(candidates) == 1:
                    return dict(
                        tableGuid=candidates[0]["tableGuid"],
                        status="native_dispatch_table_zero_verified",
                        evidence=evidence(row),
                        nativeTarget=hex(address),
                    )
                raise ValueError("调度器根方法的同地址别名无法唯一归属")
            ins = machine.ins.get(address)
            if ins is None:
                break
            if ins.mnemonic == "call":
                event = machine.event(ins, state)
                if event["target"] in targets:
                    address = event["target"]
                    continue
                if event["target"] != FN_STACK_COOKIE_CHECK:
                    break
                state = machine.complete_call(state, event)
                address += ins.size
            else:
                try:
                    address = machine.step(ins, state)
                except Boundary:
                    break
        raise ValueError("实际原生调度器的 table=0 入口尚未能唯一恢复：" + row["type"])

    def non_dispatch_entry(self, row):
        """Recognize an actual void entry that returns before touching any state."""
        if (
            not row["method"].startswith("updateTableInpl")
            or self.native(row)[:1] != b"\xc3"
        ):
            return None
        method = (
            (self.metadata.get(row["type"]) or {}).get("methods", {}).get(row["method"])
        )
        if (
            not method
            or int(method.get("function", "0"), 16) != int(row["address"], 16)
            or method.get("returns", {}).get("type") != VOID_TYPE
        ):
            return None
        return dict(
            nativeType=row["type"],
            status="native_no_dispatch_verified",
            reason="当前调度函数入口第一条指令直接返回，没有执行行为子表分派",
            evidence=evidence(row),
            entryInstruction=dict(address=row["address"], bytes="c3", mnemonic="ret"),
        )

    def command_leaf(self, command_type):
        """A recovered "Extend field OP argument" rule for the actual implementation."""
        from ..logic.commands import recover_context_leaf, recover_leaf
        from ..logic.formula import recover_formula_leaf

        if command_type not in self.leaf_cache:
            current, visited, found = command_type, set(), None
            while current and current not in visited:
                visited.add(current)
                rows = [
                    r for r in self.helper_rows[current] if r["method"].startswith("onExecute")
                ]
                if rows:
                    if len(rows) == 1:
                        code = _artifact(self.helper_path, self.helpers, rows[0])["code"]
                        found = recover_leaf(
                            rows[0], code, self.metadata, self.pe
                        ) or recover_context_leaf(rows[0], code, self.metadata)
                        found = found or recover_formula_leaf(
                            rows[0], code, self.metadata
                        )
                        if found is not None and found.get("contextFieldType"):
                            found["enumType"], found["enumValues"] = self.metadata.enum(
                                found["contextFieldType"]
                            )
                    break
                current = (self.metadata.get(current) or {}).get("parent")
            self.leaf_cache[command_type] = found
        return self.leaf_cache[command_type]

    def stand_states(self, enemy_id):
        """Enum names of the three stand-state layers, values as int32.

        The unique layer is the species' UNIQUE_STATE_Fixed; resources store
        those values as signed Int32 while metadata spells them unsigned.
        """

        def signed(values):
            return {
                name: value - (1 << 32) if value & 0x80000000 else value
                for name, value in values.items()
                if name != "NONE" and type(value) is int
            }

        species = "Em" + enemy_id[2:6]
        return dict(
            common=signed(self.metadata.enum(STAND_STATE_ENUM)[1]),
            extra=signed(self.metadata.enum(EXTRA_STATE_ENUM)[1]),
            unique=signed(
                self.metadata.enum(f"app.{species}Def.UNIQUE_STATE_Fixed")[1]
            ),
        )

    def command_evidence(self, command_type):
        """Resolve inherited implementations while retaining their native owner."""
        if command_type not in self.command_cache:
            current, visited, found = command_type, set(), None
            while current and current not in visited:
                visited.add(current)
                rows = [
                    r
                    for r in self.helper_rows[current]
                    if r["method"].startswith("onExecute")
                ]
                if rows:
                    if len(rows) != 1:
                        break
                    row = rows[0]
                    details = (
                        (self.metadata.get(current) or {})
                        .get("methods", {})
                        .get(row["method"])
                    )
                    if not details or int(details["function"], 16) != int(
                        row["address"], 16
                    ):
                        raise ValueError("命令实现与当前元数据不匹配：" + current)
                    self.native(row)
                    found = evidence(row)
                    break
                current = (self.metadata.get(current) or {}).get("parent")
            self.command_cache[command_type] = found
        return self.command_cache[command_type]

    def build_enemy(self, enemy_id, native_owner):
        from ..logic.machine import Machine
        from ..logic.selectors import recover_selectors

        monster = self.monsters[enemy_id]
        combat = monster["slots"]["COMBAT"]
        sources, imports, records = {}, {}, []
        for source in monster["tableImportClosure"]:
            expected = self.resource_records[source]
            body = self.resources.read(source)
            factories = self.resources.factories(body)
            if (
                self.resources.hashes[source] != expected["resourceSha256"]
                or structure_signature(body, factories)
                != expected["structureSignature"]
            ):
                raise ValueError("资源发现后行为表发生变化：" + source)
            owner = body["_ExportBTableType"]
            if owner in sources and sources[owner] != source:
                raise ValueError("相同导出类型对应多份资源，需要核查实例绑定")
            sources[owner] = source
        if not self.resources.read(combat)["_ExportBTableType"].startswith(
            "app." + native_owner + "_"
        ):
            raise ValueError("Combat 的真实资源归属与独立怪物模块不匹配")
        for owner, source in sources.items():
            imports[owner] = {
                int(f["offset_from_base"], 16): f["type"]
                for f in self.metadata.fields(owner).values()
                if f.get("offset_from_base")
                and "default" not in f
                and f["type"] in sources
            }
            rows = [r for r in self.rows[owner] if r["method"].startswith("table_")]
            if len(rows) != self.resource_records[source]["nativeTableMethods"]:
                raise ValueError("本怪物导入闭包的方法证据没有完整覆盖：" + owner)
            records.extend(dict(self.record(row, source)) for row in rows)
        records = resource_table_identities(records)
        by_address = defaultdict(list)
        by_type = defaultdict(list)
        for record in records:
            by_address[int(record["row"]["address"], 16)].append(record)
            by_type[record["row"]["type"]].append(record)
        roots, entry_boundaries, non_dispatch_entries = {}, [], []
        for owner in sources:
            dispatchers = [
                r for r in self.rows[owner] if r["method"].startswith("updateTableInpl")
            ]
            if len(dispatchers) != 1:
                if sources[owner] == combat:
                    raise ValueError("Combat 缺少唯一原生调度器：" + owner)
                entry_boundaries.append(
                    dict(
                        resource=sources[owner],
                        nativeType=owner,
                        dispatcherCount=len(dispatchers),
                        tableMethodCount=len(by_type[owner]),
                        reason="资源没有唯一自声明的原生调度器；未核实继承调度，不猜测入口",
                        evidence=[evidence(row) for row in dispatchers],
                        status="unreviewed_dispatch_boundary",
                    )
                )
                continue
            if (non_dispatch := self.non_dispatch_entry(dispatchers[0])) is not None:
                if sources[owner] == combat:
                    raise ValueError(
                        "Combat 调度函数直接返回，不能构造战斗入口：" + owner
                    )
                non_dispatch_entries.append(
                    dict(resource=sources[owner], **non_dispatch)
                )
                continue
            try:
                roots[sources[owner]] = self.dispatch_root(
                    dispatchers[0], by_type[owner]
                )
            except ValueError as error:
                if sources[owner] == combat:
                    raise
                entry_boundaries.append(
                    dict(
                        resource=sources[owner],
                        reason=str(error),
                        evidence=evidence(dispatchers[0]),
                        status="unreviewed_dispatch_boundary",
                    )
                )
        tables, selectors, selector_boundaries = [], [], []
        for record in records:
            row, source = record["row"], record["resource"]
            body = self.resources.read(source)
            machine = Machine(
                row,
                record["native"],
                self.pe,
                body,
                self.resources.factories(body),
                by_address,
                imports[row["type"]],
            )
            machine.metadata = self.metadata
            machine.command_evidence = {
                factory["_OrderType"]: proof
                for factory in self.resources.factories(body)
                if (proof := self.command_evidence(factory["_OrderType"])) is not None
            }
            moduli = {
                int(v, 0) for v in re.findall(r"% (0x[0-9a-f]+|\d+)", record["code"])
            }
            if len(moduli) == 1 and 0 < max(moduli) <= 100:
                machine.random_modulus = next(iter(moduli))
            machine.build()
            result, selected, boundaries = recover_selectors(
                machine, record["code"], self.pools(row["type"]), body
            )
            selectors.extend(
                dict(resource=source, tableGuid=record["tableGuid"], **item)
                for item in selected
            )
            selector_boundaries.extend(
                dict(resource=source, tableGuid=record["tableGuid"], **item)
                for item in boundaries
            )
            result = local_identities(result)
            tables.append(
                dict(
                    tableGuid=record["tableGuid"],
                    nativeTableGuid=record.get("nativeTableGuid", record["tableGuid"]),
                    tableIndex=record["tableIndex"],
                    resource=source,
                    name=Path(source)
                    .name.split("_BTable_")[-1]
                    .split("_Btable_")[-1]
                    .split(".user")[0]
                    + (
                        f" · 子表 {record['tableIndex']}"
                        if record["tableIndex"] >= 0
                        else " · 原生子表"
                    ),
                    evidence=evidence(row),
                    nativeType=row["type"],
                    nativeMethod=row["method"],
                    flowStatus=(
                        "partial"
                        if any(n["kind"] == "unknown" for n in result["nodes"])
                        else "verified"
                    ),
                    **result,
                )
            )
        if len({t["tableGuid"] for t in tables}) != len(tables):
            raise ValueError("导入闭包存在重复子表 GUID，需要保留资源实例身份")
        document = dict(
            schemaVersion=1,
            documentType="enemy_battle_logic",
            profile=self.profile,
            enemyId=enemy_id,
            enemyName=enemy_id,
            entry=roots[combat]["tableGuid"],
            scope="本怪物实际 BTableList、导入闭包与原生方法中的条件、动作请求、调用及恢复位置；未核实分支明确保留",
            limits=[
                "匹配版本的静态恢复，未在游戏中验证",
                "专项命令与全局调度尚未完成的部分保留未知",
            ],
            tables=tables,
            resources={
                source: dict(
                    structureSignature=self.resource_records[source][
                        "structureSignature"
                    ]
                )
                for source in sources.values()
            },
            resourceEntries=roots,
            resourceEntryBoundaries=entry_boundaries,
            resourceNonDispatchEntries=non_dispatch_entries,
            selectionRecovery=selectors,
            selectionBoundaries=selector_boundaries,
            semanticReviewComplete=False,
        )
        if self.requests is not None:
            document["requestCoverage"] = request_coverage(
                tables, self.requests["actionRequestBindings"], set(sources.values())
            )
        registry = RuleRegistry.load()
        leaf_rules = {}
        for table in tables:
            for node in table["nodes"]:
                command = node.get("expectedCommandType")
                if (
                    node["kind"] == "condition"
                    and command
                    and command not in registry.by_command
                    and command not in leaf_rules
                ):
                    leaf = self.command_leaf(command)
                    if leaf is not None:
                        leaf_rules[command] = leaf
        document["leafRules"] = leaf_rules
        document["standStates"] = self.stand_states(enemy_id)
        document["methodCoverage"] = dict(
            expected=len(records),
            recovered=len(tables),
            methods=[r["row"]["type"] + ":" + r["row"]["method"] for r in records],
        )
        document["bindEnemyNameFromResources"] = True
        from ..logic.combat_entry import attach_combat_entries

        attach_combat_entries(document, monster, self.metadata, self.pe)
        from ..logic.scheduler_slots import scheduler_slots

        document["schedulerSlots"] = scheduler_slots(document)
        from ..resources.variables import referenced_variables

        document["variableCatalog"] = referenced_variables(document, self.resources)
        return document


def build_monster(
    enemy_id,
    native_owner,
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
    if context is not None:
        return context.build_enemy(enemy_id, native_owner)
    if inventory_path is None:
        raise ValueError("全闭包配方需要同版本 --inventory，不能只按类型前缀猜测来源")
    with NativeRecipeContext(
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        inventory_path=inventory_path,
        requests_path=requests_path,
    ) as context:
        return context.build_enemy(enemy_id, native_owner)
