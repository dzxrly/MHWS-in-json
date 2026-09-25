from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from config import WEAPON_TYPES
from src.shared.action_values.catalog import (
    ActionMapAudit,
    ActionValueCatalog,
    MappingBinding,
    load_action_value_catalog,
    mapping_names,
)
from src.shared.action_values.rcol import RequestSetKey, RequestSetRecord


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


def build_action_value_workbook(
    catalog: ActionValueCatalog,
    resolve_text: Callable[[str], str],
) -> ActionValueWorkbookData:
    names = mapping_names(catalog, resolve_text)
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
                    names[(scope, binding.identity)],
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
