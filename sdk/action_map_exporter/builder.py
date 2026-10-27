from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .shared.json_io import write_json_atomic
from .action_data import ActionDataCatalog
from .action_relations import (
    build_action_relations,
    unresolved_action_to_dict,
    unresolved_coordinate_to_dict,
)
from .external_collisions import (
    EXTERNAL_COLLISION_TYPE,
    build_external_collision_relations,
    find_external_collision_method,
    handling_owner,
    scan_external_collisions,
)
from .motion_fields import ConstructorMotionScanner
from .motion_catalogs import (
    MOTLIST_FORMAT,
    MotbankCatalog,
    MotlistJsonCatalog,
    MotionTargetCatalog,
)
from .motion_groups import MotionGroupCatalog
from .pe import PeImage
from .pfb import PfbResourceCatalog, canonical_prefab_path
from .request_sets import RequestSetCatalog
from .insect_colliders import build_insect_attack_relations
from .resource_relations import _relation_sort_key as _resource_sort_key
from .resource_relations import build_resource_relations
from .shells import _resolve_enums_path
from .scanners import (
    DirectCallScanner,
    MotionSetScanner,
    _function_length,
    scan_ammo_item_map,
)
from .shell_relations import build_shell_relations, unresolved_shell_to_dict
from .shell_requests import resolve_shell_requests
from .shells import ShellCatalog
from .track_colliders import TrackColliderCatalog

FORMAT_NAME = "mhws_static_action_request_set_map_v2"
LogCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ActionMapOptions:
    executable_path: Path
    il2cpp_dump_path: Path
    natives_directory: Path = (
        Path(__file__).resolve().parents[2] / "MHWS-in-json" / "natives"
    )
    output_path: Path = (
        Path(__file__).resolve().parents[2] / "MHWS-in-json" / "ActionMap.json"
    )
    max_function_bytes: int = 4096

    def resolved(self) -> "ActionMapOptions":
        result = ActionMapOptions(
            executable_path=self.executable_path.expanduser().resolve(),
            il2cpp_dump_path=self.il2cpp_dump_path.expanduser().resolve(),
            natives_directory=self.natives_directory.expanduser().resolve(),
            output_path=self.output_path.expanduser().resolve(),
            max_function_bytes=self.max_function_bytes,
        )
        result.validate()
        return result

    def validate(self) -> None:
        if not self.natives_directory.is_dir():
            raise FileNotFoundError(
                f"natives JSON 目录不存在: {self.natives_directory}"
            )
        for label, path in (
            ("IL2CPP dump", self.il2cpp_dump_path),
            ("Dump EXE", self.executable_path),
        ):
            if not path.is_file():
                raise FileNotFoundError(f"{label}不存在: {path}")
        if not 128 <= self.max_function_bytes <= 65_536:
            raise ValueError("max_function_bytes 必须位于 128 到 65536 之间")


@dataclass(frozen=True, slots=True)
class ActionMapBuildResult:
    actions: int
    resolved_actions: int
    action_relations: int
    resource_relations: int
    output_path: Path


def build_action_map(
    options: ActionMapOptions,
    log: LogCallback | None = None,
) -> ActionMapBuildResult:
    settings = options.resolved()
    report = log or (lambda _message: None)

    from .shared.native_validation import load_native_metadata, verify_native_rules

    report("核对当前 EXE 与 IL2CPP 中的原生规则证据...")
    metadata = load_native_metadata(settings.il2cpp_dump_path)
    verify_native_rules(
        settings.executable_path, settings.il2cpp_dump_path, metadata=metadata
    )

    report("加载动作定义与 ActionGuide 名称...")
    action_catalog = ActionDataCatalog.load(settings.natives_directory)
    actions = action_catalog.actions
    report(f"动作定义: {len(actions)}")

    report("读取武器 MOTBANK JSON 索引...")
    banks = MotbankCatalog.load_from_directory(settings.natives_directory)
    report(f"MOTBANK 条目: {len(banks.entries)}")

    report("读取 Python 导出的 MOTLIST request-set 事件...")
    motlists = MotlistJsonCatalog.load(settings.natives_directory)
    motion_targets = MotionTargetCatalog.build(banks, motlists)
    report(
        f"MOTLIST 文档: {len(motlists.documents)}；"
        f"含 request-set 的 MotionSet: {len(motion_targets.targets)}"
    )

    report("读取武器 MotionGroupSet 表...")
    motion_groups = MotionGroupCatalog.load(action_catalog.natives_directory)
    report(
        f"MotionGroupSet: {len(motion_groups.groups)}；"
        f"MotionExtend 校验: {motion_groups.verified_extends}"
    )

    report("读取精确的 action-value requestSet 标识...")
    request_sets = RequestSetCatalog.load(action_catalog.natives_directory)
    report(f"可用 requestSet: {len(request_sets.records)}")

    report("读取武器与 Player PFB 的攻击轨道碰撞体...")
    track_colliders = TrackColliderCatalog.load(action_catalog.natives_directory)
    report(f"攻击轨道碰撞体路由: {len(track_colliders.routes)}")

    report("读取 Shell 列表、弹药名称与 PFB 资源...")
    shells = ShellCatalog.load(
        settings.natives_directory, action_catalog.natives_directory
    )
    prefabs = PfbResourceCatalog.load_from_directory(
        settings.natives_directory,
        [entry.prefab_path for entry in shells.entries],
    )
    report(f"Shell 条目: {len(shells.entries)}；已解析 PFB: {len(prefabs.documents)}")

    report("从已读取的 IL2CPP 索引选择动作方法与函数边界...")
    action_type_names = {action.class_name for action in actions}
    handling_type_names = {
        f"app.cHunterWp{index:02d}Handling" for index in range(14)
    } | {"app.cHunterWpGunHandling"}
    target_types = (
        action_type_names
        | handling_type_names
        | {
            "app.WeaponGunDef",
            EXTERNAL_COLLISION_TYPE,
        }
    )
    methods = metadata.select(target_types)
    del metadata
    classes_in_dump = sum(
        bool(methods.target_methods.get(type_name)) for type_name in action_type_names
    )
    method_count = sum(
        len(methods.target_methods.get(type_name, []))
        for type_name in action_type_names
    )
    report(
        f"IL2CPP 动作类: {classes_in_dump}/{len(action_type_names)}；"
        f"动作方法: {method_count}"
    )

    report("扫描 EXE 中的 MotionSet 常量、弹种表与直接调用...")
    hits_by_action = {}
    handling_calls_by_action = {}
    external_sources = []
    with PeImage(settings.executable_path) as image:
        initializer = next(
            (
                method
                for method in methods.target_methods.get("app.WeaponGunDef", [])
                if method.method_name.startswith(".cctor")
            ),
            None,
        )
        if initializer is None:
            raise ValueError(
                "il2cpp_dump.json 中未找到 app.WeaponGunDef 静态初始化方法"
            )
        ammo_item_map = scan_ammo_item_map(
            image, initializer, shells, settings.max_function_bytes
        )
        scanner = MotionSetScanner(
            image,
            motion_targets,
            methods.function_addresses,
            settings.max_function_bytes,
            motion_groups,
        )
        field_scanner = ConstructorMotionScanner(
            image,
            methods,
            motion_targets,
            settings.max_function_bytes,
        )
        handling_methods = [
            method
            for type_name in sorted(handling_type_names)
            for method in methods.target_methods.get(type_name, [])
        ]
        call_scanner = DirectCallScanner(
            image,
            methods.function_addresses,
            handling_methods,
            settings.max_function_bytes,
        )
        external_target = find_external_collision_method(methods.target_methods)

        def scan_external(method):
            return scan_external_collisions(
                image,
                method,
                external_target,
                _function_length(
                    methods.function_addresses,
                    method.function_address,
                    settings.max_function_bytes,
                ),
            )

        for action in actions:
            action_methods = methods.target_methods.get(action.class_name, [])
            inherited = methods.inherited_methods(
                action.class_name, _action_namespace(action.class_name)
            )
            hits_by_action[action] = [
                *(
                    hit
                    for method in action_methods
                    for hit in (
                        *scanner.scan(action.scope, method),
                        *field_scanner.scan(action.scope, method),
                    )
                ),
                *(
                    hit
                    for method in inherited
                    for hit in scanner.scan(action.scope, method)
                ),
            ]
            handling_calls_by_action[action] = [
                hit for method in action_methods for hit in call_scanner.scan(method)
            ]
            if external_target is not None:
                external_sources.append(
                    (
                        action,
                        [
                            hit
                            for method in (*action_methods, *inherited)
                            for hit in scan_external(method)
                        ],
                    )
                )
        if external_target is not None:
            for type_name in sorted(handling_type_names):
                scope = type_name.removeprefix("app.cHunter").removesuffix("Handling")
                if not (scope.startswith("Wp") and scope[2:].isdigit()):
                    continue
                external_sources.append(
                    (
                        handling_owner(scope, type_name),
                        [
                            hit
                            for method in methods.target_methods.get(type_name, [])
                            for hit in scan_external(method)
                        ],
                    )
                )
    report(
        f"弹种映射: {ammo_item_map.count}/{len(shells.core_ammo_types)}；"
        f"MotionSet 命中: {sum(len(items) for items in hits_by_action.values())}；"
        "直接调用: "
        f"{sum(len(items) for items in handling_calls_by_action.values())}"
    )

    report("构建动作关系并执行 requestSet 消歧...")
    action_result = build_action_relations(
        actions,
        hits_by_action,
        request_sets,
        methods.target_methods,
        guides=action_catalog.guides,
        track_colliders=track_colliders,
    )
    shell_resolution = resolve_shell_requests(shells, prefabs, request_sets)
    shell_result = build_shell_relations(
        shells,
        prefabs,
        request_sets,
        ammo_item_map,
        actions,
        handling_calls_by_action,
        resolution=shell_resolution,
    )
    resource_result = build_resource_relations(
        shells,
        prefabs,
        request_sets,
        ammo_item_map,
        resolution=shell_resolution,
    )
    external_relations = build_external_collision_relations(
        external_sources, request_sets, track_colliders
    )
    action_relations = _merge_action_relations(
        [*action_result.relations, *shell_result.relations, *external_relations]
    )
    insect_relations = build_insect_attack_relations(
        action_catalog.natives_directory,
        _resolve_enums_path(
            settings.natives_directory, action_catalog.natives_directory
        ),
        request_sets,
    )
    resource_relations = sorted(
        [*resource_result.relations, *insect_relations], key=_resource_sort_key
    )
    mapped_action_identities = {
        str(relation["actionIdentity"]) for relation in action_relations
    }
    shell_request_set_identities = {
        record.target_key
        for record in request_sets.records
        if record.user_data_type.endswith("AttackParamPlShell")
    }
    resource_target_identities = {
        (
            str(relation["scope"]),
            str(relation["rcol"]).casefold(),
            int(relation["requestSetId"]),
            int(relation["keyHash"]),
            int(relation["sourceRequestSetOrdinal"]),
        )
        for relation in resource_relations
    }
    mapped_shell_request_sets = len(
        shell_request_set_identities & resource_target_identities
    )

    document: dict[str, object] = {
        "_format": FORMAT_NAME,
        "inputs": {
            "motlistFormat": MOTLIST_FORMAT,
            "il2CppDumpFile": settings.il2cpp_dump_path.name,
            "il2CppDumpSize": settings.il2cpp_dump_path.stat().st_size,
            "executableFile": settings.executable_path.name,
            "executableSize": settings.executable_path.stat().st_size,
            "motbankMode": "json_resources",
        },
        "statistics": {
            "actionDefinitions": len(actions),
            "actionGuideNames": len(action_catalog.guides),
            "ambiguousNameHashes": len(action_result.unresolved_names),
            "actionClassesInDump": classes_in_dump,
            "actionMethods": method_count,
            "motionBanks": len(banks.entries),
            "motlistDocuments": len(motlists.documents),
            "motionTargetsWithRequestSets": len(motion_targets.targets),
            "motionGroupSets": len(motion_groups.groups),
            "motionGroupExtendChecks": motion_groups.verified_extends,
            "motionGroupHits": sum(
                bool(hit.motion_group)
                for items in hits_by_action.values()
                for hit in items
            ),
            "shellEntries": len(shells.entries),
            "shellEntriesWithDirectResourceRelations": (
                resource_result.entries_with_direct_relations
            ),
            "shellPrefabs": _shell_prefab_count(prefabs, shells),
            "missingShellPrefabs": len(prefabs.missing_prefabs),
            "coreAmmoItemMappings": ammo_item_map.count,
            "actionsWithMotionSets": action_result.actions_with_motion_sets,
            "actionsWithMappedRequestSets": len(mapped_action_identities),
            "actionRelations": len(action_relations),
            "resourceRelations": len(resource_relations),
            "derivedResourceVariantRelations": (
                resource_result.derived_variant_relations
            ),
            "derivedResourceFamilyRelations": resource_result.derived_family_relations,
            "shellColliderRuleRelations": (
                resource_result.shell_collider_rule_relations
            ),
            "rcolFallbackResourceRelations": (resource_result.rcol_fallback_relations),
            "insectAttackRelations": len(insect_relations),
            "shellRequestSets": len(shell_request_set_identities),
            "shellRequestSetsWithResourceRelations": mapped_shell_request_sets,
            "unmappedShellRequestSets": (
                len(shell_request_set_identities) - mapped_shell_request_sets
            ),
            "exactRequestSetIdentities": len(request_sets.records),
            "trackColliderRoutes": len(track_colliders.routes),
            "ambiguousCoordinates": len(action_result.ambiguous_coordinates),
            "missingCoordinates": len(action_result.missing_coordinates),
        },
        "actionRelations": action_relations,
        "resourceRelations": resource_relations,
        "unresolvedActions": [
            unresolved_action_to_dict(item) for item in action_result.unresolved_actions
        ],
        "unresolvedCoordinates": [
            unresolved_coordinate_to_dict(item)
            for item in action_result.unresolved_coordinates
        ],
        "unresolvedNames": [
            {
                "scope": item.scope,
                "keyHash": item.key_hash,
                "candidateGuideIds": list(item.guide_ids),
                "reason": "action_name_hash_ambiguous",
            }
            for item in action_result.unresolved_names
        ],
        "unresolvedShellEntries": [
            unresolved_shell_to_dict(item) for item in resource_result.unresolved
        ],
        "missingShellPrefabs": list(prefabs.missing_prefabs),
        "ammoItemMapEvidence": [
            {
                "actionClass": item.action_class,
                "methodName": item.method_name,
                "functionAddress": item.function_address,
                "callAddress": item.call_address,
                "callTarget": item.call_target,
                "shellTypeValue": item.shell_type_value,
                "shellTypeName": item.shell_type_name,
                "itemValue": item.item_value,
                "itemId": item.item_id,
            }
            for item in ammo_item_map.evidence
        ],
    }
    write_json_atomic(settings.output_path, document)
    report(
        f"ActionMap 已写入: {settings.output_path} "
        f"(动作关系 {len(action_relations)}，"
        f"资源关系 {len(resource_relations)})"
    )
    return ActionMapBuildResult(
        actions=len(actions),
        resolved_actions=len(mapped_action_identities),
        action_relations=len(action_relations),
        resource_relations=len(resource_relations),
        output_path=settings.output_path,
    )


def _shell_prefab_count(prefabs: PfbResourceCatalog, shells: ShellCatalog) -> int:
    """Count the former Shell/ActionData selection, excluding extra dependencies."""
    requested = {
        canonical_prefab_path(entry.prefab_path).casefold() for entry in shells.entries
    }
    return sum(
        canonical_prefab_path(document.prefab_path).casefold() in requested
        or canonical_prefab_path(document.prefab_path)
        .casefold()
        .startswith("gamedesign/player/actiondata/")
        for document in prefabs.documents
    )


def _action_namespace(class_name: str) -> str:
    # "app.Wp05Action.cMStart1" -> "app.Wp05Action."
    head, separator, _tail = class_name.rpartition(".")
    return f"{head}{separator}" if separator else class_name


def _merge_action_relations(
    relations: list[dict[str, object]],
) -> list[dict[str, object]]:
    confidence_order = {"structural": 0, "derived": 1, "proven": 2}
    merged: dict[tuple[object, ...], dict[str, object]] = {}
    for relation in relations:
        key = (
            str(relation["scope"]),
            str(relation["actionIdentity"]),
            str(relation["rcol"]).casefold(),
            int(relation["requestSetId"]),
            int(relation["keyHash"]),
            int(relation["sourceRequestSetOrdinal"]),
        )
        current = merged.get(key)
        if current is None:
            current = dict(relation)
            current.setdefault("confidence", "proven")
            current.setdefault("conditions", [])
            merged[key] = current
            continue

        sources = {
            value
            for source in (str(current["source"]), str(relation["source"]))
            for value in source.split("+")
            if value
        }
        current["source"] = "+".join(sorted(sources))
        current["resolutionMethods"] = sorted(
            {
                *current.get("resolutionMethods", []),
                *relation.get("resolutionMethods", []),
            }
        )
        for list_name in ("conditions", "evidence", "shellEvidence"):
            values: dict[str, object] = {}
            for value in [
                *current.get(list_name, []),
                *relation.get(list_name, []),
            ]:
                values.setdefault(repr(value), value)
            current[list_name] = sorted(values.values(), key=repr)
        current_confidence = str(current.get("confidence", "proven"))
        incoming_confidence = str(relation.get("confidence", "proven"))
        if confidence_order[incoming_confidence] > confidence_order[current_confidence]:
            current["confidence"] = incoming_confidence

    output = list(merged.values())
    output.sort(key=_relation_sort_key)
    return output


def _relation_sort_key(relation: dict[str, object]) -> tuple[object, ...]:
    guide = relation.get("actionGuideId")
    return (
        str(relation["scope"]),
        int(relation["actionOrder"]),
        (0, 0) if guide is None else (1, int(guide)),
        str(relation["actionIdentity"]),
        str(relation["rcol"]).upper(),
        int(relation["requestSetId"]),
        int(relation["keyHash"]),
        int(relation["sourceRequestSetOrdinal"]),
    )
