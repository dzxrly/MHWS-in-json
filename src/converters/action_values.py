from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from config import WEAPON_TYPES
from src.data.action_map import (
    ActionMapRelation,
    ResourceMapRelation,
    load_action_map,
)
from src.data.rcol import (
    RequestSetKey,
    RequestSetRecord,
    load_action_value_request_sets,
)


ACTION_DATA_RELATIVE = Path("STM/GameDesign/Player/ActionData")

SHEET_NAMES = {
    **{
        f"Wp{index:02d}": f"Wp{index:02d}_{weapon_name}"
        for index, weapon_name in enumerate(WEAPON_TYPES)
    },
    "Ammo": "Ammo",
}

LEADING_MAPPING_COLUMNS = ("MappingName", "MappingInternalName", "MappingConfidence")
LEADING_COLUMNS = (*LEADING_MAPPING_COLUMNS, "_Attack", "_FixAttack")

TRAILING_MAPPING_COLUMNS = (
    "MappingKind",
    "MappingIdentity",
    "MappingNameSource",
    "ResourceRole",
    "MappingCondition",
    "MappingSource",
)

MAPPING_COLUMNS = (*LEADING_MAPPING_COLUMNS, *TRAILING_MAPPING_COLUMNS)

DEFAULT_COLUMNS = (
    *LEADING_COLUMNS,
    "sourceRequestSetOrdinal",
    "requestSetID",
    "groupIndex",
    "status",
    "requestSetIndex",
    "keyHash",
    "KeyNameMMHash",
    "name",
    "keyName",
    "userDataType",
    *TRAILING_MAPPING_COLUMNS,
)


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
    actions: dict[str, dict[int, Any]]
    bindings: dict[RequestSetKey, tuple[MappingBinding, ...]]
    mapping_source_counts: dict[str, int]
    action_map_audit: ActionMapAudit | None = None


@dataclass(frozen=True, slots=True)
class RowGroup:
    start_row: int
    end_row: int
    identity: str
    unmapped: bool = False


@dataclass(frozen=True, slots=True)
class SheetAudit:
    eligible_request_sets: int
    mapped_request_sets: int
    unmapped_request_sets: int
    displayed_rows: int
    mapping_groups: int


@dataclass(frozen=True, slots=True)
class ActionValueWorkbookData:
    sheets: dict[str, list[dict[str, Any]]]
    columns: dict[str, tuple[str, ...]]
    sources: dict[str, tuple[str, ...]]
    groups: dict[str, tuple[RowGroup, ...]]
    audits: dict[str, SheetAudit]


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
        actions={},
        bindings=bindings,
        mapping_source_counts=dict(sorted(collector.source_counts.items())),
        action_map_audit=audit,
    )


def build_action_value_workbook(
    catalog: ActionValueCatalog,
    resolve_text: Callable[[str], str],
) -> ActionValueWorkbookData:
    sheets: dict[str, list[dict[str, Any]]] = {}
    columns_by_sheet: dict[str, tuple[str, ...]] = {}
    sources_by_sheet: dict[str, tuple[str, ...]] = {}
    groups_by_sheet: dict[str, tuple[RowGroup, ...]] = {}
    audits: dict[str, SheetAudit] = {}

    for scope, sheet_name in SHEET_NAMES.items():
        records = catalog.records.get(scope, ())
        record_by_key = {record.key: record for record in records}
        grouped: dict[
            str,
            tuple[
                MappingBinding,
                dict[RequestSetKey, tuple[MappingBinding, RequestSetRecord]],
            ],
        ] = {}
        mapped_keys: set[RequestSetKey] = set()

        for record in records:
            for binding in catalog.bindings.get(record.key, ()):
                mapped_keys.add(record.key)
                existing = grouped.get(binding.identity)
                if existing is None:
                    grouped[binding.identity] = (
                        binding,
                        {record.key: (binding, record)},
                    )
                    continue
                current_binding, group_records = existing
                if binding.order < current_binding.order:
                    current_binding = binding
                group_records[record.key] = (binding, record)
                grouped[binding.identity] = (
                    current_binding,
                    group_records,
                )

        mapped_groups = sorted(
            (
                (
                    binding.display_name(resolve_text),
                    binding,
                    group_records,
                    {binding.identity},
                )
                for binding, group_records in grouped.values()
            ),
            key=lambda item: (
                item[1].order,
                item[0].casefold(),
                sorted(item[3]),
            ),
        )
        columns = _sheet_columns(records)
        rows: list[dict[str, Any]] = []
        row_groups: list[RowGroup] = []
        next_excel_row = 3

        for mapping_name, binding, group_records, identities in mapped_groups:
            ordered_records = sorted(
                group_records.values(),
                key=lambda item: item[1].sort_key,
            )
            if not ordered_records:
                continue
            start_row = next_excel_row
            for edge_binding, record in ordered_records:
                rows.append(
                    _workbook_row(
                        mapping_name,
                        edge_binding,
                        record,
                        columns,
                    )
                )
                next_excel_row += 1
            row_groups.append(
                RowGroup(
                    start_row=start_row,
                    end_row=next_excel_row - 1,
                    identity="|".join(sorted(identities)),
                )
            )

        unmapped_records = [
            record for record in records if record.key not in mapped_keys
        ]
        if unmapped_records:
            start_row = next_excel_row
            for record in sorted(
                unmapped_records,
                key=lambda item: item.sort_key,
            ):
                rows.append(
                    _workbook_row(None, None, record, columns)
                )
                next_excel_row += 1
            row_groups.append(
                RowGroup(
                    start_row=start_row,
                    end_row=next_excel_row - 1,
                    identity=f"unmapped:{scope}",
                    unmapped=True,
                )
            )

        sheets[sheet_name] = rows
        columns_by_sheet[sheet_name] = columns
        sources_by_sheet[sheet_name] = tuple(
            sorted(
                {record.key.rcol for record in records},
                key=str.casefold,
            )
        )
        groups_by_sheet[sheet_name] = tuple(row_groups)
        audits[sheet_name] = SheetAudit(
            eligible_request_sets=len(records),
            mapped_request_sets=len(mapped_keys),
            unmapped_request_sets=len(records) - len(mapped_keys),
            displayed_rows=len(rows),
            mapping_groups=len(mapped_groups),
        )

        if len(record_by_key) != len(records):
            raise ValueError(f"Duplicate requestSet identity in {scope}")

    return ActionValueWorkbookData(
        sheets=sheets,
        columns=columns_by_sheet,
        sources=sources_by_sheet,
        groups=groups_by_sheet,
        audits=audits,
    )


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


def _sheet_columns(
    records: tuple[RequestSetRecord, ...],
) -> tuple[str, ...]:
    columns = list(LEADING_COLUMNS)
    seen = set(MAPPING_COLUMNS) | set(LEADING_COLUMNS)
    for record in records:
        for key in record.properties:
            if key not in seen:
                columns.append(key)
                seen.add(key)
    if not records:
        return DEFAULT_COLUMNS
    return (*columns, *TRAILING_MAPPING_COLUMNS)


def _workbook_row(
    mapping_name: str | None,
    binding: MappingBinding | None,
    record: RequestSetRecord,
    columns: tuple[str, ...],
) -> dict[str, Any]:
    values = {
        "MappingName": mapping_name,
        "MappingKind": binding.kind if binding else None,
        "MappingIdentity": binding.identity if binding else None,
        "MappingInternalName": binding.internal_name if binding else None,
        "MappingNameSource": binding.name_source if binding else None,
        "ResourceRole": binding.resource_role if binding else None,
        "MappingConfidence": binding.confidence if binding else None,
        "MappingCondition": binding.condition if binding else None,
        "MappingSource": binding.source if binding else None,
        **record.properties,
    }
    return {column: values.get(column) for column in columns}
