"""Recover resource-bound command sites and state writes for every monster.

Outputs remain research evidence. Semantic status, native location status and
whole-battle completeness are independent and are reported separately.
"""

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path

from .evidence import method_rows, evidence_key
from .metadata import Il2cppMetadata
from .native import PE, digest, verify_rows
from .native_bindings import bind_native
from .command_annotations import annotate_effects
from .resources import Resources, typed
from .predicates import RuleRegistry
from .extraction import extract_inventory


def command_binding(event, body, factories, registry):
    """Require both native object identity and the declared resource type."""
    commands, arguments = set(), set()
    for value in event["arguments"]:
        if (
            isinstance(value, tuple)
            and value[0] == "pointer"
            and value[2] == 0
            and isinstance(value[1], tuple)
        ):
            owner, index = value[1]
            if owner == "command":
                commands.add(index)
            if owner == "argument":
                arguments.add(index)
    target = event["target"]
    if isinstance(target, tuple) and target[0] == "command_method":
        commands.add(target[1])
    if len(commands) != 1:
        return None
    slot = next(iter(commands))
    if not 0 <= slot < len(factories):
        return dict(
            kind="boundary", site=event["site"], reason="command_index_out_of_range"
        )
    factory = factories[slot]
    if len(arguments) != 1:
        return dict(
            kind="command",
            site=event["site"],
            commandIndex=slot,
            commandType=factory["_OrderType"],
            bindingStatus="argument_not_uniquely_recovered",
            semanticStatus="unreviewed",
            summary=factory["_OrderType"].split(".")[-1],
        )
    index = next(iter(arguments))
    if not 0 <= index < len(body["_CommandArgArray"]):
        return dict(
            kind="boundary", site=event["site"], reason="argument_index_out_of_range"
        )
    argument_type, argument = typed(body["_CommandArgArray"][index])
    if argument_type != factory["_ArgumentType"]:
        return dict(
            kind="boundary",
            site=event["site"],
            reason="factory_argument_type_mismatch",
            commandIndex=slot,
            argumentIndex=index,
            actualArgumentType=argument_type,
            expectedArgumentType=factory["_ArgumentType"],
        )
    predicate = registry.bind(factory["_OrderType"], argument_type, argument)
    summary = predicate["summary"]
    if predicate["status"] != "verified":
        summary = (
            factory["_OrderType"].split(".")[-1] + "（命令和参数已绑定，语义待核对）"
        )
    return dict(
        kind="command",
        site=event["site"],
        commandIndex=slot,
        argumentIndex=index,
        commandType=factory["_OrderType"],
        argumentType=argument_type,
        argument=argument,
        bindingStatus="native_indices_and_resource_types_verified",
        semanticStatus=(
            "reviewed_rule" if predicate["status"] == "verified" else "unreviewed"
        ),
        predicate=predicate,
        summary=summary,
    )


def _artifact(index_path, index, row):
    artifact = index["nativeBodyArtifacts"][evidence_key(row)]
    path = index_path.parent / artifact["path"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError("原生缓存摘要变化")
    data = json.loads(gzip.decompress(raw))
    if not data["completed"] or data["profile"] != index["profile"]:
        raise ValueError("原生缓存不完整或版本冲突")
    if any(data[k] != row[k] for k in ("address", "end", "nativeSha256")):
        raise ValueError("原生方法身份变化")
    return data


def recover_all(
    native_index,
    inventory,
    exe,
    metadata,
    natives,
    output,
    *,
    command_catalog=None,
    requests_path=None,
):
    output = Path(output).resolve()
    root = Path(__file__).resolve().parents[3]
    if not output.is_relative_to(root / ".agents"):
        raise ValueError("逐怪物研究输出必须位于 .agents")
    index_path = Path(native_index)
    index = json.loads(index_path.read_text(encoding="utf8"))
    inventory = json.loads(Path(inventory).read_text(encoding="utf8"))
    if (
        index["profile"] != inventory["profile"]
        or digest(exe) != index["profile"]["exeSha256"]
    ):
        raise ValueError("逐怪物分析来源不匹配")
    rows = method_rows(index)
    verify_rows(exe, rows)
    scopes = extract_inventory(inventory, rows)
    requests = (
        json.loads(Path(requests_path).read_text(encoding="utf8"))
        if requests_path
        else None
    )
    if requests is not None and requests["profile"] != index["profile"]:
        raise ValueError("动作请求与原生恢复来源不匹配")
    resources = Resources(natives)
    for source, expected in inventory["sourceHashes"].items():
        if digest(resources.root / resources.resolve(source)) != expected:
            raise ValueError("资源清单来源变化：" + source)
    registry = RuleRegistry.load()
    catalog = (
        json.loads(Path(command_catalog).read_text(encoding="utf8"))
        if command_catalog
        else {}
    )
    if catalog and catalog["profile"] != index["profile"]:
        raise ValueError("专有命令来源不匹配")
    leaf_by_type = defaultdict(list)
    for leaf in catalog.get("leafComparisons", []):
        leaf_by_type[leaf["commandType"]].append(leaf)
    pools = defaultdict(list)
    for initializer in catalog.get("initializers", []):
        for pool in initializer["staticPools"]:
            pools[pool["address"]].append(pool)
    if registry.data["profile"] != index["profile"]:
        raise ValueError("规则来源不匹配")
    by_type = {r["exportType"]: r for r in inventory["resources"]}
    by_address = defaultdict(list)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["type"]].append(row)
        by_address[int(row["address"], 16)].append(row)
    layouts = {}
    with Il2cppMetadata(Path(metadata)) as dump:
        if dump.sha256 != index["profile"]["metadataSha256"]:
            raise ValueError("元数据来源不匹配")
        operator = {
            int(v["offset_from_base"], 16): k
            for k, v in dump.fields("ace.btable.cOperatorWork").items()
            if v.get("offset_from_base") and "default" not in v
        }
        for name in by_type:
            layouts[name] = {
                int(v["offset_from_base"], 16): dict(name=k, type=v["type"])
                for k, v in dump.fields(name).items()
                if v.get("offset_from_base") and v["type"] in by_type
            }
    output.mkdir(parents=True, exist_ok=True)
    (output / "resources").mkdir(exist_ok=True)
    bindings, cache, counts = {}, {}, Counter()
    with PE(exe) as pe:
        for number, resource in enumerate(inventory["resources"], 1):
            source = resource["resource"]
            name = resource["exportType"]
            body = resources.read(source)
            if resources.hashes[source] != resource["resourceSha256"]:
                raise ValueError("行为表来源变化：" + source)
            factories = resources.factories(body)
            methods = []
            resource_counts = Counter()
            for row in grouped[name]:
                key = (evidence_key(row), row["method"].startswith("updateTableInpl"))
                if key not in cache:
                    data = _artifact(index_path, index, row)
                    start, end = int(row["address"], 16), int(row["end"], 16)
                    cache[key] = bind_native(
                        pe.read(start, end - start),
                        start,
                        data["controlFlow"],
                        dispatcher=row["method"].startswith("updateTableInpl"),
                    )
                recovered = cache[key]
                annotations = []
                for boundary in recovered.get("externalBranches", []):
                    annotations.append(
                        dict(
                            kind="native_range_boundary",
                            **boundary,
                            summary="跳转到已校验方法范围外；范围内证据保留，外部后续另行核查",
                        )
                    )
                for reference in recovered.get("memoryReferences", []):
                    if reference["address"] in pools:
                        annotations.append(
                            dict(
                                kind="static_pool_reference",
                                **reference,
                                pools=pools[reference["address"]],
                                summary="引用静态初始化权重常量；key、候选筛选与选招连接另行审核",
                            )
                        )
                for events in recovered["blocks"].values():
                    for event in events:
                        if event["kind"] == "call":
                            bound = command_binding(event, body, factories, registry)
                            if bound:
                                bound["sourceResource"] = source
                                if "argumentIndex" in bound:
                                    bound["sourceBodyPointer"] = (
                                        f"/_CommandArgArray/{bound['argumentIndex']}/{bound.get('argumentType','')}"
                                    )
                                if bound["kind"] == "command":
                                    bound["callTarget"] = (
                                        hex(event["target"])
                                        if isinstance(event["target"], int)
                                        else event["target"]
                                    )
                                    implementation = bound["commandType"]
                                    if implementation in catalog.get(
                                        "inheritedCommands", {}
                                    ):
                                        implementation = catalog["inheritedCommands"][
                                            implementation
                                        ]["implementationType"]
                                    bound["implementationAvailable"] = (
                                        implementation in catalog.get("commands", {})
                                    )
                                    candidates = [
                                        leaf
                                        for leaf in leaf_by_type[implementation]
                                        if leaf["argumentType"] is None
                                        or leaf["argumentType"]
                                        == bound.get("argumentType")
                                    ]
                                    if len(candidates) == 1 and (
                                        candidates[0]["argumentField"] is None
                                        or "argument" in bound
                                    ):
                                        leaf = candidates[0]
                                        value = (
                                            bound["argument"][leaf["argumentField"]]
                                            if leaf["argumentField"]
                                            else leaf["constant"]
                                        )
                                        bound["leafComparison"] = dict(
                                            rule=leaf, resourceValue=value
                                        )
                                        bound["semanticStatus"] = (
                                            "native_leaf_comparison_recovered"
                                        )
                                        bound["summary"] = (
                                            leaf["contextField"]
                                            + " "
                                            + leaf["operator"]
                                            + " "
                                            + json.dumps(
                                                value,
                                                ensure_ascii=False,
                                                separators=(",", ":"),
                                            )
                                            + "（自身 Extend；有效性与类型检查见命令实现）"
                                        )
                                annotate_effects(bound, catalog)
                                annotate_effects(bound, catalog)
                                annotations.append(bound)
                            target = event["target"]
                            if isinstance(target, int):
                                choices = by_address.get(target, [])
                                owner = event["arguments"][1]
                                owner_type = (
                                    name
                                    if owner == ("pointer", "export", 0)
                                    else (
                                        layouts[name].get(owner[1], {}).get("type")
                                        if isinstance(owner, tuple)
                                        and owner[0] == "export_field"
                                        else None
                                    )
                                )
                                targets = [
                                    dict(
                                        type=r["type"],
                                        method=r["method"],
                                        address=r["address"],
                                        resource=by_type[r["type"]]["resource"],
                                    )
                                    for r in choices
                                    if r["type"] == owner_type
                                ]
                                if targets:
                                    annotations.append(
                                        dict(
                                            kind="table_call",
                                            site=event["site"],
                                            targets=targets,
                                            ownerBinding="native_export_object_verified",
                                            targetBindingStatus=(
                                                "unique"
                                                if len(targets) == 1
                                                else "shared_code_alias_requires_position_review"
                                            ),
                                        )
                                    )
                            if event["positionArguments"]:
                                annotations.append(
                                    dict(
                                        kind="position",
                                        site=event["site"],
                                        targetAddress=(
                                            hex(target)
                                            if isinstance(target, int)
                                            else None
                                        ),
                                        positions=event["positionArguments"],
                                        summary="原生调用参数中的表编号与继续位置；压栈或切换含义另行核对",
                                    )
                                )
                        elif (
                            event["kind"] == "store"
                            and isinstance(event["destination"], tuple)
                            and event["destination"][:2] == ("pointer", "operator")
                        ):
                            offset = event["destination"][2]
                            summary = operator.get(
                                offset, "结构内部偏移 " + hex(offset)
                            )
                            annotations.append(
                                dict(
                                    kind="state_write",
                                    site=event["site"],
                                    field=summary,
                                    offset=hex(offset),
                                    size=event["size"],
                                    value=event["value"],
                                    summary="写入 " + summary,
                                )
                            )
                        elif event["kind"] == "comparison" and any(
                            v is not None for v in event["values"]
                        ):
                            annotations.append(
                                dict(
                                    **event,
                                    summary="原生比较 "
                                    + event["operation"]
                                    + " "
                                    + event["assembly"],
                                )
                            )
                        elif event["kind"] == "branch" and event["comparison"]:
                            annotations.append(
                                dict(
                                    **event,
                                    summary="条件跳转 "
                                    + event["operation"]
                                    + " → "
                                    + str(event["target"])
                                    + "；未跳转 → "
                                    + str(event["fallthrough"]),
                                )
                            )
                item = {
                    k: row[k]
                    for k in ("type", "method", "address", "end", "nativeSha256")
                }
                item.update(
                    dataflowStatus=recovered["status"],
                    annotations=annotations,
                    rangeBoundaryWarnings=recovered.get("rangeBoundaryWarnings", []),
                    externalBranches=recovered.get("externalBranches", []),
                    semanticReviewComplete=False,
                )
                item["nativeControlFlow"] = recovered.get("nativeControlFlow")
                methods.append(item)
                resource_counts["methodContexts"] += 1
                resource_counts[recovered["status"]] += 1
                for a in annotations:
                    resource_counts[a["kind"]] += 1
                    if a["kind"] == "command":
                        resource_counts[a["bindingStatus"]] += 1
                        resource_counts[a["semanticStatus"]] += 1
                        if a.get("partialImplementationEffects"):
                            resource_counts["partial_field_write_command"] += 1
                        if a.get("partialImplementationEffects"):
                            resource_counts["partial_field_write_command"] += 1
            identity = hashlib.sha256(source.encode()).hexdigest()[:20]
            path = output / "resources" / f"{identity}.json"
            path.write_text(
                json.dumps(
                    dict(
                        resource=source,
                        exportType=name,
                        methods=methods,
                        counts=dict(resource_counts),
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf8",
            )
            bindings[source] = dict(
                path="resources/" + path.name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                counts=dict(resource_counts),
            )
            counts.update(resource_counts)
            if number % 25 == 0:
                print(
                    "RESOURCE SEMANTICS",
                    number,
                    "/",
                    len(inventory["resources"]),
                    dict(counts),
                    flush=True,
                )
    monsters = []
    for monster in scopes:
        per_enemy = Counter()
        for source in monster["resources"]:
            per_enemy.update(bindings[source]["counts"])
        monsters.append(
            dict(
                enemyId=monster["enemyId"],
                extractorModule=monster["extractorModule"],
                combatResource=monster["slots"]["COMBAT"],
                slots=monster["slots"],
                resources=monster["resources"],
                nativeMethodContexts=len(monster["nativeMethods"]),
                counts=dict(per_enemy),
                wholeBattleRecovered=False,
                semanticReviewComplete=False,
            )
        )
    result = dict(
        schemaVersion=1,
        profile=index["profile"],
        monsters=monsters,
        resources=bindings,
        counts=dict(counts),
        releaseReady=False,
        scope="逐怪物原生调用参数、资源条件和状态写入恢复；整场战斗及专有命令语义仍须审核",
    )
    (output / "index.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(
        "RECOVERED ALL MONSTERS",
        json.dumps(
            dict(monsters=len(monsters), counts=dict(counts)), ensure_ascii=False
        ),
        flush=True,
    )
    return result
