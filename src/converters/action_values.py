from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config import WEAPON_TYPES
from src.data.action_map import ActionMapRelation, load_action_map
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

DEFAULT_COLUMNS = (
    "ActionName",
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
)


@dataclass(frozen=True, slots=True)
class ActionBinding:
    identity: str
    scope: str
    order: tuple[int, int, int, str]
    fallback_name: str
    name_guid: str = ""
    suffix: str = ""
    source: str = ""

    def display_name(self, resolve_text: Callable[[str], str]) -> str:
        localized = (resolve_text(self.name_guid) or "").strip() if self.name_guid else ""
        fallback = self.fallback_name.strip()
        return f"{localized or fallback}{self.suffix}".strip()


@dataclass(frozen=True, slots=True)
class ActionMapAudit:
    path: str
    relations: int
    named_relations: int
    unnamed_relations: int
    bound_request_sets: int
    bindings: int


@dataclass(frozen=True, slots=True)
class ActionValueCatalog:
    records: dict[str, tuple[RequestSetRecord, ...]]
    actions: dict[str, dict[int, Any]]
    bindings: dict[RequestSetKey, tuple[ActionBinding, ...]]
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
    action_groups: int


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
    unnamed_relations = 0
    relation_contracts: dict[tuple[RequestSetKey, str], ActionBinding] = {}
    for relation in document.relations:
        key = _request_set_key(relation)
        if key not in record_index:
            raise ValueError(
                "ActionMap relation does not resolve to an exact current requestSet: "
                f"{key}"
            )
        if not relation.action_name_guid:
            unnamed_relations += 1
            continue
        binding = _action_map_binding(relation)
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
        relations=len(document.relations),
        named_relations=len(document.relations) - unnamed_relations,
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
            tuple[ActionBinding, dict[RequestSetKey, RequestSetRecord]],
        ] = {}
        mapped_keys: set[RequestSetKey] = set()

        for record in records:
            for binding in catalog.bindings.get(record.key, ()):
                mapped_keys.add(record.key)
                existing = grouped.get(binding.identity)
                if existing is None:
                    grouped[binding.identity] = (
                        binding,
                        {record.key: record},
                    )
                    continue
                current_binding, group_records = existing
                if binding.order < current_binding.order:
                    current_binding = binding
                group_records[record.key] = record
                grouped[binding.identity] = (
                    current_binding,
                    group_records,
                )

        display_groups: dict[
            str,
            tuple[
                ActionBinding,
                dict[RequestSetKey, RequestSetRecord],
                set[str],
            ],
        ] = {}
        for binding, group_records in grouped.values():
            display_name = binding.display_name(resolve_text)
            existing = display_groups.get(display_name)
            if existing is None:
                display_groups[display_name] = (
                    binding,
                    dict(group_records),
                    {binding.identity},
                )
                continue
            current_binding, current_records, identities = existing
            if binding.order < current_binding.order:
                current_binding = binding
            current_records.update(group_records)
            identities.add(binding.identity)
            display_groups[display_name] = (
                current_binding,
                current_records,
                identities,
            )

        mapped_groups = sorted(
            (
                (display_name, binding, group_records, identities)
                for display_name, (
                    binding,
                    group_records,
                    identities,
                ) in display_groups.items()
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

        for action_name, _binding, group_records, identities in mapped_groups:
            ordered_records = sorted(
                group_records.values(),
                key=lambda record: record.sort_key,
            )
            if not ordered_records:
                continue
            start_row = next_excel_row
            for record in ordered_records:
                rows.append(_workbook_row(action_name, record, columns))
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
                    _workbook_row(None, record, columns)
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
            action_groups=len(mapped_groups),
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
            dict[str, ActionBinding],
        ] = defaultdict(dict)
        self.source_counts: Counter[str] = Counter()

    def add(self, key: RequestSetKey, binding: ActionBinding) -> None:
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

    def freeze(self) -> dict[RequestSetKey, tuple[ActionBinding, ...]]:
        return {
            key: tuple(
                sorted(
                    values.values(),
                    key=lambda binding: binding.order,
                )
            )
            for key, values in self.bindings.items()
        }


def _request_set_key(relation: ActionMapRelation) -> RequestSetKey:
    return RequestSetKey(
        scope=relation.scope,
        rcol=relation.rcol,
        request_set_id=relation.request_set_id,
        key_hash=relation.key_hash,
        source_ordinal=relation.source_request_set_ordinal,
    )


def _action_map_binding(relation: ActionMapRelation) -> ActionBinding:
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
    return ActionBinding(
        identity=relation.action_identity,
        scope=relation.scope,
        order=(0, relation.action_order, guide_order, relation.action_identity),
        fallback_name=fallback_name,
        name_guid=relation.action_name_guid,
        source=f"action_map:{relation.source}",
    )


def _sheet_columns(
    records: tuple[RequestSetRecord, ...],
) -> tuple[str, ...]:
    columns = ["ActionName"]
    seen = set(columns)
    for record in records:
        for key in record.properties:
            if key not in seen:
                columns.append(key)
                seen.add(key)
    if not records:
        return DEFAULT_COLUMNS
    return tuple(columns)


def _workbook_row(
    action_name: str | None,
    record: RequestSetRecord,
    columns: tuple[str, ...],
) -> dict[str, Any]:
    values = {
        "ActionName": action_name,
        **record.properties,
    }
    return {column: values.get(column) for column in columns}
