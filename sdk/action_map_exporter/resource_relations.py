from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import PurePath
import re

from .models import (
    AmmoNameRecord,
    RequestSetIdentity,
    ShellEntryRecord,
    UnresolvedShellEntry,
)
from .pfb import PfbResourceCatalog
from .request_sets import RequestSetCatalog, canonical_rcol_path
from .scanners import AmmoItemMapCatalog
from .shell_collider_rules import shell_collider_rules
from .shells import ShellCatalog
from .collision_references import collision_conditions, collision_evidence
from .resource_families import find_named_family_members
from .shell_requests import (
    ResolvedShellRequest,
    ShellRequestResolution,
    reference_evidence,
    resolve_shell_requests,
)

_SEMANTIC_TOKEN = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|[^A-Za-z0-9]|$)|[A-Z]?[a-z]+|[0-9]+"
)
_MARKER_SUFFIX = re.compile(
    r"(?:_?MultiHit(?:Status)?(?:Rate)?Curve|_?MultiHitRate)$",
    re.IGNORECASE,
)
_MARKER_PREFIX = re.compile(r"^(?:Wp\d{2}|WpGun)_?", re.IGNORECASE)


@dataclass(slots=True)
class ResourceRelationResult:
    relations: list[dict[str, object]]
    resolved: list[ResolvedShellRequest]
    unresolved: list[UnresolvedShellEntry]
    entries: int
    entries_with_direct_relations: int
    derived_variant_relations: int
    rcol_fallback_relations: int
    derived_family_relations: int
    shell_collider_rule_relations: int = 0


@dataclass(frozen=True, slots=True)
class _ResourceDescriptor:
    identity: str
    order: int
    internal_name: str
    name_guid: str
    japanese_name: str
    name_source: str
    suffix: str
    fallback_name: str
    role: str


class _RelationBuilder:
    def __init__(
        self,
        descriptor: _ResourceDescriptor,
        request_set: RequestSetIdentity,
        confidence: str,
        conditions: tuple[dict[str, object], ...] = (),
    ) -> None:
        self.descriptor = descriptor
        self.request_set = request_set
        self.confidence = confidence
        self.conditions = list(conditions)
        self.sources: set[str] = set()
        self.methods: set[str] = set()
        self.evidence: dict[str, dict[str, object]] = {}

    def add_source(self, value: str) -> None:
        self.sources.add(value)

    def add_method(self, value: str) -> None:
        self.methods.add(value)

    def add_evidence(self, value: dict[str, object]) -> None:
        self.evidence.setdefault(repr(value), value)

    def add_conditions(self, values: tuple[dict[str, object], ...]) -> None:
        for value in values:
            if value not in self.conditions:
                self.conditions.append(value)

    def build(self) -> dict[str, object]:
        return {
            "scope": self.request_set.scope,
            "resourceIdentity": self.descriptor.identity,
            "resourceOrder": self.descriptor.order,
            "resourceInternalName": self.descriptor.internal_name,
            "resourceNameGuid": self.descriptor.name_guid,
            "resourceJapaneseName": self.descriptor.japanese_name,
            "resourceNameSource": self.descriptor.name_source,
            "resourceNameSuffix": self.descriptor.suffix,
            "fallbackName": self.descriptor.fallback_name,
            "resourceRole": self.descriptor.role,
            "confidence": self.confidence,
            "source": "+".join(sorted(self.sources)),
            "resolutionMethods": sorted(self.methods),
            "conditions": self.conditions,
            "rcol": self.request_set.rcol,
            "requestSetId": self.request_set.request_set_id,
            "keyHash": self.request_set.key_hash,
            "sourceRequestSetOrdinal": (self.request_set.source_request_set_ordinal),
            "evidence": sorted(self.evidence.values(), key=repr),
        }


def build_resource_relations(
    shells: ShellCatalog,
    prefabs: PfbResourceCatalog,
    request_sets: RequestSetCatalog,
    ammo_item_map: AmmoItemMapCatalog,
    *,
    resolution: ShellRequestResolution | None = None,
) -> ResourceRelationResult:
    resolution = resolution or resolve_shell_requests(shells, prefabs, request_sets)
    resolved, references, unresolved = (
        resolution.resolved,
        resolution.references,
        resolution.unresolved,
    )
    ammo_names = _resolve_ammo_names(resolved, shells, ammo_item_map)
    builders: dict[tuple[object, ...], _RelationBuilder] = {}
    covered: set[tuple[object, ...]] = set()

    for item in resolved:
        descriptor = _resource_descriptor(
            item.entry,
            ammo_names.get(_entry_key(item.entry)),
        )
        relation_key = (
            descriptor.identity,
            descriptor.suffix,
            *item.request_set.target_key,
        )
        builder = builders.get(relation_key)
        if builder is None:
            builder = _RelationBuilder(descriptor, item.request_set, "proven")
            builders[relation_key] = builder
        builder.add_source("static_shell_list_pfb_rcol")
        builder.add_method("shell_list_prefab_rcol_request_set")
        builder.add_method(descriptor.name_source)
        builder.add_evidence(_shell_evidence(item, descriptor.name_source))
        builder.add_conditions(collision_conditions(item.entry, item.collision_id))
        covered.add(item.request_set.target_key)

    rule_count = _add_shell_collider_rules(
        shells,
        resolution,
        request_sets,
        ammo_names,
        builders,
        covered,
    )
    derived_count = _add_derived_variants(
        resolved,
        references,
        request_sets,
        ammo_names,
        builders,
        covered,
    )
    family_count = _add_named_family_members(
        resolution,
        request_sets,
        ammo_names,
        builders,
        covered,
    )
    fallback_count = _add_rcol_fallbacks(
        references,
        request_sets,
        builders,
        covered,
    )
    relations = [builder.build() for builder in builders.values()]
    relations.sort(key=_relation_sort_key)
    return ResourceRelationResult(
        relations=relations,
        resolved=resolved,
        unresolved=sorted(
            unresolved,
            key=lambda item: (
                item.source_scope,
                item.entry_index,
                item.collision_id,
                item.reason,
            ),
        ),
        entries=len(shells.entries),
        entries_with_direct_relations=len(
            {_entry_key(item.entry) for item in resolved}
        ),
        derived_variant_relations=derived_count,
        rcol_fallback_relations=fallback_count,
        derived_family_relations=family_count,
        shell_collider_rule_relations=rule_count,
    )


def _resolve_ammo_names(
    resolved: list[ResolvedShellRequest],
    shells: ShellCatalog,
    ammo_item_map: AmmoItemMapCatalog,
) -> dict[tuple[str, int], AmmoNameRecord]:
    output: dict[tuple[str, int], AmmoNameRecord] = {}
    for item in resolved:
        core_type = shells.get_core_ammo_type_name(item.entry.fixed_name)
        ammo_name = ammo_item_map.find(core_type) if core_type else None
        if ammo_name is not None:
            output[_entry_key(item.entry)] = ammo_name
    return output


def _resource_descriptor(
    entry: ShellEntryRecord,
    ammo_name: AmmoNameRecord | None,
) -> _ResourceDescriptor:
    fallback, name_source = _entry_fallback_name(entry)
    if ammo_name is not None:
        return _ResourceDescriptor(
            identity=f"ammo:item:{ammo_name.name_guid.casefold()}",
            order=ammo_name.order,
            internal_name=entry.fixed_name or fallback,
            name_guid=ammo_name.name_guid,
            japanese_name=ammo_name.japanese_name,
            name_source="weapon_gun_static_item_table",
            suffix="",
            fallback_name=fallback,
            role="ammo",
        )
    scope_index = (
        int(entry.source_scope[2:])
        if entry.source_scope.startswith("Wp") and entry.source_scope[2:].isdigit()
        else 99
    )
    return _ResourceDescriptor(
        identity=f"shell:{entry.source_scope}:{entry.fixed_id}",
        order=1_000_000 + scope_index * 10_000 + entry.entry_index,
        internal_name=fallback,
        name_guid="",
        japanese_name="",
        name_source=name_source,
        suffix="",
        fallback_name=fallback,
        role="shell",
    )


def _entry_fallback_name(entry: ShellEntryRecord) -> tuple[str, str]:
    if entry.fixed_name.strip():
        return entry.fixed_name.strip(), "shell_fixed_enum"
    if entry.main_param_path.strip():
        return PurePath(entry.main_param_path).stem, "main_param_stem"
    if entry.prefab_path.strip():
        return PurePath(entry.prefab_path).stem, "prefab_stem"
    return (
        f"{entry.source_scope}_SHELL_{entry.fixed_id}",
        "generated_shell_identity",
    )


def _shell_evidence(
    item: ResolvedShellRequest,
    name_resolution: str,
) -> dict[str, object]:
    evidence = reference_evidence(
        item.entry,
        item.prefab_chain,
        item.rcol_resource_path,
    )
    evidence.update(
        {
            "shellNameHash": item.entry.shell_name_hash,
            "ammoTypeName": item.entry.ammo_type_name,
            "mainParamPath": item.entry.main_param_path,
            "collisionId": item.collision_id,
            "nameResolution": name_resolution,
        }
    )
    evidence.update(collision_evidence(item.entry, item.collision_id))
    return evidence


def _add_named_family_members(
    resolution: ShellRequestResolution,
    request_sets: RequestSetCatalog,
    ammo_names: dict[tuple[str, int], AmmoNameRecord],
    builders: dict[tuple[object, ...], _RelationBuilder],
    covered: set[tuple[object, ...]],
) -> int:
    initial_coverage = set(covered)
    family_targets = set()
    for anchor, target in find_named_family_members(
        resolution, request_sets, ammo_names
    ):
        if target.target_key in initial_coverage:
            continue
        descriptor = _resource_descriptor(
            anchor.entry, ammo_names[_entry_key(anchor.entry)]
        )
        # Consumers group display names by identity. Keep inferred members in
        # their own group so the activation caveat cannot be merged away by
        # the primary collider's proven name.
        descriptor = replace(
            descriptor,
            identity=f"{descriptor.identity}:family",
            suffix=" [family; activation unverified]",
        )
        key = (descriptor.identity, descriptor.suffix, *target.target_key)
        if key not in builders:
            builders[key] = _RelationBuilder(
                descriptor,
                target,
                "derived",
                (
                    {
                        "kind": "resource_family_membership",
                        "activation": "unverified",
                        "hitOrdinal": None,
                        "ammoLevel": anchor.entry.ammo_level,
                    },
                ),
            )
        builder = builders[key]
        builder.add_source("static_shell_resource_family")
        builder.add_method("exclusive_ammo_resource_family")
        builder.add_method("matching_attack_payload_and_configured_shape_role")
        builder.add_method(descriptor.name_source)
        builder.add_evidence(
            {
                "anchor": _shell_evidence(anchor, descriptor.name_source),
                "anchorTarget": {
                    "scope": anchor.request_set.scope,
                    "rcol": anchor.request_set.rcol,
                    "requestSetId": anchor.request_set.request_set_id,
                    "keyHash": anchor.request_set.key_hash,
                    "sourceRequestSetOrdinal": anchor.request_set.source_request_set_ordinal,
                },
                "attackPayloadSha256": target.attack_payload_hash,
                "anchorShapeTypes": list(anchor.request_set.shape_types),
                "memberShapeTypes": list(target.shape_types),
                "activationConfirmed": False,
            }
        )
        covered.add(target.target_key)
        family_targets.add(target.target_key)
    return len(family_targets)


def _entry_key(entry: ShellEntryRecord) -> tuple[str, int]:
    return entry.source_scope, entry.entry_index


def _relation_sort_key(relation: dict[str, object]) -> tuple[object, ...]:
    return (
        str(relation["scope"]),
        int(relation["resourceOrder"]),
        str(relation["resourceIdentity"]),
        str(relation["resourceNameSuffix"]),
        str(relation["rcol"]).casefold(),
        int(relation["requestSetId"]),
        int(relation["keyHash"]),
        int(relation["sourceRequestSetOrdinal"]),
    )


def _add_shell_collider_rules(
    shells: ShellCatalog,
    resolution: ShellRequestResolution,
    request_sets: RequestSetCatalog,
    ammo_names: dict[tuple[str, int], AmmoNameRecord],
    builders: dict[tuple[object, ...], _RelationBuilder],
    covered: set[tuple[object, ...]],
) -> int:
    before = len(builders)
    for entry in shells.entries:
        rules = shell_collider_rules(entry)
        if not rules:
            continue
        rcols = resolution.entry_rcols.get(_entry_key(entry), [])
        base = _resource_descriptor(entry, ammo_names.get(_entry_key(entry)))
        for rule in rules:
            # The shell swaps colliders on its own RequestSetCollider, so the
            # ID must exist in the entry's own prefab RCOL.
            matches: dict[
                tuple[object, ...],
                tuple[RequestSetIdentity, tuple[object, ...], str],
            ] = {}
            for chain, resource in rcols:
                for request_set in request_sets.find_by_resource(
                    entry.target_scope, resource, rule.collision_id
                ):
                    matches.setdefault(
                        request_set.target_key, (request_set, chain, resource)
                    )
            if len(matches) != 1:
                continue
            request_set, chain, resource = next(iter(matches.values()))
            descriptor = replace(
                _variant_descriptor(base, rule.marker),
                name_source=f"{base.name_source}+shell_collider_rule",
            )
            relation_key = (
                descriptor.identity,
                descriptor.suffix,
                *request_set.target_key,
            )
            builder = builders.get(relation_key)
            if builder is None:
                builder = _RelationBuilder(
                    descriptor, request_set, "proven", rule.conditions
                )
                builders[relation_key] = builder
            builder.add_source("static_shell_collider_rule")
            builder.add_method(rule.method)
            evidence = reference_evidence(entry, chain, resource)
            evidence.update(
                {
                    "mainParamPath": entry.main_param_path,
                    "baseCollisionIds": list(entry.collision_ids),
                    "collisionId": rule.collision_id,
                    "gameFunction": rule.game_function,
                }
            )
            builder.add_evidence(evidence)
            covered.add(request_set.target_key)
    return len(builders) - before


def _add_derived_variants(
    resolved: list[ResolvedShellRequest],
    references: dict[tuple[str, str], list[dict[str, object]]],
    request_sets: RequestSetCatalog,
    ammo_names: dict[tuple[str, int], AmmoNameRecord],
    builders: dict[tuple[object, ...], _RelationBuilder],
    covered: set[tuple[object, ...]],
) -> int:
    direct_by_rcol: dict[
        tuple[str, str], dict[tuple[object, ...], RequestSetIdentity]
    ] = defaultdict(dict)
    for item in resolved:
        key = (
            item.request_set.scope,
            canonical_rcol_path(item.request_set.rcol),
        )
        direct_by_rcol[key][item.request_set.target_key] = item.request_set

    records_by_rcol: dict[tuple[str, str], list[RequestSetIdentity]] = {}
    delta_counts: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    for rcol_key in references:
        scope, resource = rcol_key
        records = [
            record
            for record in request_sets.find_in_resource(scope, resource)
            if record.user_data_type.endswith("AttackParamPlShell")
        ]
        records_by_rcol[rcol_key] = records
        direct_records = direct_by_rcol.get(rcol_key, {})
        for candidate in records:
            if candidate.target_key in direct_records:
                continue
            marker = _request_set_marker(candidate)
            if not marker:
                continue
            for base in direct_records.values():
                if _request_set_marker(base) == marker:
                    continue
                delta = candidate.request_set_id - base.request_set_id
                if delta:
                    delta_counts[(scope, marker)][delta] += 1

    selected_deltas: dict[tuple[str, str], int] = {}
    for family, counts in delta_counts.items():
        ranked = counts.most_common(2)
        if (
            ranked
            and ranked[0][1] >= 2
            and (len(ranked) == 1 or ranked[0][1] > ranked[1][1])
        ):
            selected_deltas[family] = ranked[0][0]

    before = len(builders)
    directly_covered = set(covered)
    distinct_resolved: dict[tuple[object, ...], ResolvedShellRequest] = {}
    for item in resolved:
        key = (*_entry_key(item.entry), *item.request_set.target_key)
        distinct_resolved.setdefault(key, item)

    for item in distinct_resolved.values():
        rcol_key = (
            item.request_set.scope,
            canonical_rcol_path(item.request_set.rcol),
        )
        base_marker = _request_set_marker(item.request_set)
        for candidate in records_by_rcol.get(rcol_key, []):
            candidate_key = candidate.target_key
            if candidate_key in directly_covered:
                continue
            marker = _request_set_marker(candidate)
            delta = selected_deltas.get((candidate.scope, marker))
            if (
                not marker
                or delta is None
                or marker == base_marker
                or candidate.request_set_id != item.request_set.request_set_id + delta
            ):
                continue
            descriptor = _variant_descriptor(
                _resource_descriptor(
                    item.entry,
                    ammo_names.get(_entry_key(item.entry)),
                ),
                marker,
            )
            relation_key = (
                descriptor.identity,
                descriptor.suffix,
                *candidate_key,
            )
            builder = builders.get(relation_key)
            if builder is None:
                builder = _RelationBuilder(
                    descriptor,
                    candidate,
                    "derived",
                    (
                        {
                            "kind": "request_set_resource_marker",
                            "value": marker,
                            "resourcePaths": list(candidate.resource_paths),
                        },
                    ),
                )
                builders[relation_key] = builder
            builder.add_source("derived_shell_request_set_variant")
            builder.add_method("dominant_request_set_id_delta")
            builder.add_method("request_set_resource_marker")
            evidence = _shell_evidence(item, "derived_request_set_variant")
            evidence.update(
                {
                    "baseRequestSetId": item.request_set.request_set_id,
                    "derivedRequestSetId": candidate.request_set_id,
                    "inferredRequestSetIdDelta": delta,
                    "resourceMarker": marker,
                    "requestSetResourcePaths": list(candidate.resource_paths),
                }
            )
            builder.add_evidence(evidence)
            covered.add(candidate_key)
    return len(builders) - before


def _variant_descriptor(
    base: _ResourceDescriptor,
    marker: str,
) -> _ResourceDescriptor:
    slug = re.sub(r"[^a-z0-9]+", "-", marker.casefold()).strip("-")
    return _ResourceDescriptor(
        identity=f"{base.identity}:variant:{slug}",
        order=base.order,
        internal_name=f"{base.internal_name}_{marker}",
        name_guid=base.name_guid,
        japanese_name=base.japanese_name,
        name_source=f"{base.name_source}+request_set_resource_marker",
        suffix=f" [{marker}]",
        fallback_name=base.fallback_name,
        role=base.role,
    )


def _request_set_marker(request_set: RequestSetIdentity) -> str:
    markers: set[str] = set()
    for path in request_set.resource_paths:
        stem = PurePath(path).stem
        stem = _MARKER_PREFIX.sub("", stem)
        stem = _MARKER_SUFFIX.sub("", stem).strip("_")
        tokens = [
            match.group(0).upper()
            for match in _SEMANTIC_TOKEN.finditer(stem)
            if not match.group(0).isdigit()
        ]
        if tokens:
            markers.add("_".join(tokens))
    return "+".join(sorted(markers))


def _add_rcol_fallbacks(
    references: dict[tuple[str, str], list[dict[str, object]]],
    request_sets: RequestSetCatalog,
    builders: dict[tuple[object, ...], _RelationBuilder],
    covered: set[tuple[object, ...]],
) -> int:
    before = len(builders)
    for order, ((scope, resource), evidence_items) in enumerate(
        sorted(references.items())
    ):
        records = [
            record
            for record in request_sets.find_in_resource(scope, resource)
            if record.user_data_type.endswith("AttackParamPlShell")
            and record.target_key not in covered
        ]
        if not records:
            continue
        display_path = str(evidence_items[0].get("rcolResourcePath", resource))
        internal_name = PurePath(display_path).stem
        descriptor = _ResourceDescriptor(
            identity=f"rcol:{scope}:{resource}",
            order=2_000_000 + order,
            internal_name=internal_name,
            name_guid="",
            japanese_name="",
            name_source="rcol_filename",
            suffix=" [RCOL supplemental]",
            fallback_name=internal_name,
            role="rcol_fallback",
        )
        for record in records:
            relation_key = (
                descriptor.identity,
                descriptor.suffix,
                *record.target_key,
            )
            builder = builders.get(relation_key)
            if builder is None:
                builder = _RelationBuilder(
                    descriptor,
                    record,
                    "structural",
                )
                builders[relation_key] = builder
            builder.add_source("static_pfb_rcol_fallback")
            builder.add_method("prefab_rcol_resource_table")
            for evidence_item in evidence_items:
                evidence = dict(evidence_item)
                evidence["requestSetId"] = record.request_set_id
                evidence["requestSetResourcePaths"] = list(record.resource_paths)
                builder.add_evidence(evidence)
            covered.add(record.target_key)
    return len(builders) - before
