"""Discover actual BTable owners, imports and metadata coverage for all monsters."""

from collections import Counter
import hashlib
import json

from .metadata import Il2cppMetadata
from src.processed_data.enemy_battle_logic.resources import (
    Resources,
    typed,
    structure_signature,
)
from src.processed_data.enemy_battle_logic.definitions import (
    EXPECTED_ENEMY_IDS,
    TRAINING_ENEMY_ID,
)
from src.processed_data.enemy_battle_logic.action_names import ActionNames


def table_references(resources, value):
    if isinstance(value, dict):
        for name, body in value.items():
            if (
                name == "ace.btable.user_data.BTable"
                and isinstance(body, dict)
                and body.get("path")
            ):
                yield resources.resolve(body["path"])
            else:
                yield from table_references(resources, body)
    elif isinstance(value, list):
        for item in value:
            yield from table_references(resources, item)


def discover_inventory(natives, metadata_path, profile):
    resources = Resources(natives)
    records, monsters, factory_catalog, name_catalog = {}, [], {}, {}
    with Il2cppMetadata(metadata_path) as metadata:
        if metadata.sha256 != profile["metadataSha256"]:
            raise ValueError("资源审计的元数据版本与索引不匹配")
        for enemy_id in EXPECTED_ENEMY_IDS:
            prefix = "Em" + enemy_id[2:9]
            path = resources.resolve(
                f"STM/GameDesign/Enemy/{prefix[:6]}/{prefix[7:]}/BTable/{prefix}_BTableList.user.3.json"
            )
            listed = resources.read(path)
            slots = {
                key[7:]: resources.reference(value)
                for key, value in listed.items()
                if key.startswith("_Table_")
                and list(table_references(resources, value))
            }
            if "COMBAT" not in slots:
                raise ValueError("大型怪物缺少 Combat 资源引用：" + enemy_id)
            pending, closure = list(slots.values()), set()
            while pending:
                source = pending.pop()
                if source in closure:
                    continue
                closure.add(source)
                if source not in records:
                    body = resources.read(source)
                    export_type = body["_ExportBTableType"]
                    metadata_type = metadata.get(export_type)
                    if metadata_type is None:
                        raise ValueError("行为资源导出类不存在：" + export_type)
                    methods = metadata_type.get("methods", {})
                    table_methods = [
                        (key, value)
                        for key, value in methods.items()
                        if key.startswith("table_")
                    ]
                    factories = resources.factories(body)
                    types = dict(Counter(f["_OrderType"] for f in factories))
                    identity = hashlib.sha256(
                        json.dumps(types, sort_keys=True).encode()
                    ).hexdigest()[:24]
                    if (
                        identity in factory_catalog
                        and factory_catalog[identity] != types
                    ):
                        raise ValueError("命令目录身份冲突")
                    factory_catalog[identity] = types
                    root = (
                        min(table_methods, key=lambda item: item[1]["id"])
                        if table_methods
                        else None
                    )
                    records[source] = dict(
                        resource=source,
                        resourceSha256=resources.hashes[source],
                        structureSignature=structure_signature(body, factories),
                        exportType=export_type,
                        metadataPresent=True,
                        nativeTableMethods=len(table_methods),
                        dispatcherCount=sum(
                            key.startswith("updateTableInpl") for key in methods
                        ),
                        arguments=len(body["_CommandArgArray"]),
                        imports=sorted(
                            set(table_references(resources, body["_ImportBTableList"]))
                        ),
                        commandFactoryTypeCatalogId=identity,
                        rootCandidate=(
                            dict(
                                method=root[0],
                                address="0x" + root[1]["function"].removeprefix("0x"),
                                status="metadata_candidate_requires_dispatcher_verification",
                            )
                            if root
                            else None
                        ),
                    )
                pending.extend(records[source]["imports"])
            names = ActionNames(resources, enemy_id).catalog()
            for entry in names["shellCatalog"]:
                source = entry["source"]
                catalog = name_catalog.setdefault(
                    source,
                    dict(resource=source, sha256=entry["sourceSha256"], entries=[]),
                )
                if entry not in catalog["entries"]:
                    catalog["entries"].append(entry)
            monsters.append(
                dict(
                    enemyId=enemy_id,
                    btableList=path,
                    slots=slots,
                    tableImportClosure=sorted(closure),
                    shellNameResources=sorted(
                        {entry["source"] for entry in names["shellCatalog"]}
                    ),
                    shellSourceStatus=names["shellSourceStatus"],
                    entireBattleRecovered=False,
                )
            )
    if any(item["enemyId"] == TRAINING_ENEMY_ID for item in monsters):
        raise ValueError("训练靶不能进入大型怪物审计")
    return dict(
        schemaVersion=2,
        profile=profile,
        monsterCount=len(monsters),
        uniqueBTableResources=len(records),
        nativeTableMethodBindings=sum(
            r["nativeTableMethods"] for r in records.values()
        ),
        monsters=monsters,
        resources=list(records.values()),
        commandFactoryTypeCatalog=factory_catalog,
        shellNameCatalog=list(name_catalog.values()),
        sourceHashes=resources.hashes,
        scope="资源、名称和元数据发现；入口候选及资源槽位不代表已恢复执行流程",
    )
