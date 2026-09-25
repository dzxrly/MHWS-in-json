"""Exact action bindings and display names shared by export products."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from .action_map import ActionMapRelation, ResourceMapRelation, load_action_map
from .rcol import RequestSetKey, RequestSetRecord, load_action_value_request_sets


ACTION_DATA_RELATIVE = Path("STM/GameDesign/Player/ActionData")


@dataclass(frozen=True, slots=True)
class MappingBinding:
    identity: str
    scope: str
    order: tuple[int, int, int, str]
    kind: str
    fallback_name: str
    internal_name: str
    name_guid: str = ""
    suffix: str = ""
    name_source: str = ""
    resource_role: str = ""
    confidence: str = ""
    condition: str = ""
    source: str = ""

    def display_name(self, resolve_text: Callable[[str], str]) -> str:
        localized = (resolve_text(self.name_guid) or "").strip() if self.name_guid else ""
        fallback = self.fallback_name.strip()
        base = localized or fallback
        return f"{base} {self.suffix}".strip() if self.suffix else base


@dataclass(frozen=True, slots=True)
class ActionMapAudit:
    path: str
    relations: int
    action_relations: int
    resource_relations: int
    named_relations: int
    unnamed_relations: int
    bound_request_sets: int
    bindings: int


@dataclass(frozen=True, slots=True)
class ActionValueCatalog:
    records: dict[str, tuple[RequestSetRecord, ...]]
    bindings: dict[RequestSetKey, tuple[MappingBinding, ...]]
    mapping_source_counts: dict[str, int]
    action_map_audit: ActionMapAudit | None = None


def load_action_value_catalog(
    natives_dir: Path,
    action_map_path: Path,
) -> ActionValueCatalog:
    natives_dir = Path(natives_dir)
    records = load_action_value_request_sets(
        natives_dir / ACTION_DATA_RELATIVE
    )
    record_index: dict[RequestSetKey, RequestSetRecord] = {}
    for scope_records in records.values():
        for record in scope_records:
            if record.key in record_index:
                raise ValueError(f"Duplicate requestSet identity: {record.key}")
            record_index[record.key] = record

    document = load_action_map(Path(action_map_path))
    collector = _BindingCollector(record_index)
    relation_contracts: dict[tuple[RequestSetKey, str], MappingBinding] = {}
    relation_bindings = [
        *(
            (relation, _action_map_binding(relation))
            for relation in document.action_relations
        ),
        *(
            (relation, _resource_map_binding(relation))
            for relation in document.resource_relations
        ),
    ]
    unnamed_relations = sum(
        not binding.name_guid for _relation, binding in relation_bindings
    )
    for relation, binding in relation_bindings:
        key = _request_set_key(relation)
        if key not in record_index:
            raise ValueError(
                "ActionMap relation does not resolve to an exact current requestSet: "
                f"{key}"
            )
        contract_key = (key, binding.identity)
        current = relation_contracts.get(contract_key)
        if current is not None and current != binding:
            raise ValueError(
                "Conflicting ActionMap relations for the same action/requestSet: "
                f"{binding.identity} -> {key}"
            )
        relation_contracts[contract_key] = binding
        collector.add(key, binding)

    bindings = collector.freeze()
    audit = ActionMapAudit(
        path=str(document.path),
        relations=len(relation_bindings),
        action_relations=len(document.action_relations),
        resource_relations=len(document.resource_relations),
        named_relations=len(relation_bindings) - unnamed_relations,
        unnamed_relations=unnamed_relations,
        bound_request_sets=len(bindings),
        bindings=sum(len(values) for values in bindings.values()),
    )
    return ActionValueCatalog(
        records=records,
        bindings=bindings,
        mapping_source_counts=dict(sorted(collector.source_counts.items())),
        action_map_audit=audit,
    )


def mapping_names(
    catalog: ActionValueCatalog,
    resolve_text: Callable[[str], str],
) -> dict[tuple[str, str], str]:
    """Resolve the representative MappingName per scope and mapping identity."""
    representatives: dict[tuple[str, str], MappingBinding] = {}
    for scope, records in catalog.records.items():
        for record in records:
            for binding in catalog.bindings.get(record.key, ()):
                key = (scope, binding.identity)
                current = representatives.get(key)
                if current is None or binding.order < current.order:
                    representatives[key] = binding
    return {key: binding.display_name(resolve_text) for key, binding in representatives.items()}


class _BindingCollector:
    def __init__(self, records: dict[RequestSetKey, RequestSetRecord]):
        self.record_keys = set(records)
        self.bindings: dict[
            RequestSetKey,
            dict[str, MappingBinding],
        ] = defaultdict(dict)
        self.source_counts: Counter[str] = Counter()

    def add(self, key: RequestSetKey, binding: MappingBinding) -> None:
        if key not in self.record_keys:
            raise ValueError(f"Unknown requestSet identity: {key}")
        current = self.bindings[key].get(binding.identity)
        if current is not None:
            if current != binding:
                raise ValueError(
                    "Conflicting bindings for the same action/requestSet: "
                    f"{binding.identity} -> {key}"
                )
            return
        self.bindings[key][binding.identity] = binding
        self.source_counts[binding.source] += 1

    def freeze(self) -> dict[RequestSetKey, tuple[MappingBinding, ...]]:
        return {
            key: tuple(
                sorted(
                    values.values(),
                    key=lambda binding: binding.order,
                )
            )
            for key, values in self.bindings.items()
        }


def _request_set_key(
    relation: ActionMapRelation | ResourceMapRelation,
) -> RequestSetKey:
    return RequestSetKey(
        scope=relation.scope,
        rcol=relation.rcol,
        request_set_id=relation.request_set_id,
        key_hash=relation.key_hash,
        source_ordinal=relation.source_request_set_ordinal,
    )


def _action_map_binding(relation: ActionMapRelation) -> MappingBinding:
    guide_order = (
        relation.action_guide_id
        if relation.action_guide_id is not None
        else 2**31 - 1
    )
    fallback_name = (
        relation.action_japanese_name
        or relation.fallback_name
        or relation.action_internal_name
    )
    return MappingBinding(
        identity=relation.action_identity,
        scope=relation.scope,
        order=(0, relation.action_order, guide_order, relation.action_identity),
        kind="Action",
        fallback_name=fallback_name,
        internal_name=relation.action_internal_name,
        name_guid=relation.action_name_guid,
        name_source=(
            "action_guide_message"
            if relation.action_name_guid
            else "action_internal_fallback"
        ),
        confidence=relation.confidence,
        condition=_format_conditions(relation.conditions),
        source=f"action_map:{relation.source}",
    )


def _resource_map_binding(relation: ResourceMapRelation) -> MappingBinding:
    fallback_name = (
        relation.resource_japanese_name
        or relation.fallback_name
        or relation.resource_internal_name
    )
    return MappingBinding(
        identity=relation.resource_identity,
        scope=relation.scope,
        order=(
            1,
            relation.resource_order,
            0,
            relation.resource_identity,
        ),
        kind="Resource",
        fallback_name=fallback_name,
        internal_name=relation.resource_internal_name,
        name_guid=relation.resource_name_guid,
        suffix=relation.resource_name_suffix,
        name_source=relation.resource_name_source,
        resource_role=relation.resource_role,
        confidence=relation.confidence,
        condition=_format_conditions(relation.conditions),
        source=f"action_map:{relation.source}",
    )


def _format_conditions(conditions: tuple[dict[str, Any], ...]) -> str:
    return "; ".join(
        json.dumps(
            condition,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for condition in conditions
    )
