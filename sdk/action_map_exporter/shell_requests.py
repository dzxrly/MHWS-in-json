from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import (
    PfbResourceDocument,
    RequestSetIdentity,
    ShellEntryRecord,
    UnresolvedShellEntry,
)
from .pfb import PfbResourceCatalog
from .request_sets import RequestSetCatalog, canonical_rcol_path
from .shells import ShellCatalog


@dataclass(frozen=True, slots=True)
class ResolvedShellRequest:
    entry: ShellEntryRecord
    prefab_chain: tuple[PfbResourceDocument, ...]
    rcol_resource_path: str
    collision_id: int
    request_set: RequestSetIdentity


@dataclass(slots=True)
class ShellRequestResolution:
    resolved: list[ResolvedShellRequest]
    references: dict[tuple[str, str], list[dict[str, object]]]
    unresolved: list[UnresolvedShellEntry]
    # (source_scope, entry_index) -> (prefab chain, RCOL resource) pairs.
    entry_rcols: dict[
        tuple[str, int], list[tuple[tuple[PfbResourceDocument, ...], str]]
    ] = field(default_factory=dict)


def resolve_shell_requests(
    shells: ShellCatalog,
    prefabs: PfbResourceCatalog,
    request_sets: RequestSetCatalog,
) -> ShellRequestResolution:
    resolved: list[ResolvedShellRequest] = []
    references: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    unresolved: list[UnresolvedShellEntry] = []
    entry_rcols: dict[
        tuple[str, int], list[tuple[tuple[PfbResourceDocument, ...], str]]
    ] = {}

    for entry in shells.entries:
        if not entry.prefab_path.strip():
            unresolved.append(_unresolved(entry, -1, "prefab_path_missing"))
            continue
        prefab = prefabs.find(entry.prefab_path)
        if prefab is None:
            unresolved.append(_unresolved(entry, -1, "prefab_not_resolved"))
            continue

        rcol_paths = prefabs.find_rcol_resources(entry.prefab_path)
        entry_rcols[(entry.source_scope, entry.entry_index)] = rcol_paths
        resources = tuple(
            sorted({resource for _chain, resource in rcol_paths}, key=str.casefold)
        )
        for chain, resource in rcol_paths:
            reference_key = (entry.target_scope, canonical_rcol_path(resource))
            evidence = reference_evidence(entry, chain, resource)
            known = {repr(item) for item in references[reference_key]}
            if repr(evidence) not in known:
                references[reference_key].append(evidence)

        if not rcol_paths:
            unresolved.append(
                _unresolved(
                    entry,
                    -1,
                    "prefab_has_no_rcol_resource",
                    resources=resources,
                )
            )
            continue
        if not entry.collision_ids:
            unresolved.append(
                _unresolved(
                    entry,
                    -1,
                    "shell_entry_has_no_collision_id",
                    resources=resources,
                )
            )
            continue

        for collision_id in entry.collision_ids:
            candidates: dict[
                tuple[object, ...],
                list[
                    tuple[
                        tuple[PfbResourceDocument, ...],
                        str,
                        RequestSetIdentity,
                    ]
                ],
            ] = defaultdict(list)
            for chain, resource in rcol_paths:
                for request_set in request_sets.find_by_resource(
                    entry.target_scope,
                    resource,
                    collision_id,
                ):
                    candidates[request_set.target_key].append(
                        (chain, resource, request_set)
                    )
            selected = list(candidates)
            if len(selected) != 1:
                named = [
                    key
                    for key, values in candidates.items()
                    if values[0][2].key_hash != 0
                ]
                if len(named) == 1:
                    selected = named
            if len(selected) != 1:
                unresolved.append(
                    _unresolved(
                        entry,
                        collision_id,
                        (
                            "rcol_request_set_not_found"
                            if not candidates
                            else "rcol_request_set_ambiguous"
                        ),
                        candidate_count=len(candidates),
                        resources=resources,
                    )
                )
                continue
            for chain, resource, request_set in candidates[selected[0]]:
                resolved.append(
                    ResolvedShellRequest(
                        entry=entry,
                        prefab_chain=chain,
                        rcol_resource_path=resource,
                        collision_id=collision_id,
                        request_set=request_set,
                    )
                )
    return ShellRequestResolution(resolved, dict(references), unresolved, entry_rcols)


def reference_evidence(
    entry: ShellEntryRecord,
    chain: tuple[PfbResourceDocument, ...],
    resource: str,
) -> dict[str, object]:
    return {
        "sourceScope": entry.source_scope,
        "shellListPath": entry.shell_list_path,
        "entryIndex": entry.entry_index,
        "fixedId": entry.fixed_id,
        "fixedName": entry.fixed_name,
        "prefabPath": entry.prefab_path,
        "prefabTraversal": [document.prefab_path for document in chain],
        "prefabArchivePaths": [document.archive_path for document in chain],
        "rcolResourcePath": resource,
    }


def _unresolved(
    entry: ShellEntryRecord,
    collision_id: int,
    reason: str,
    candidate_count: int = 0,
    resources: tuple[str, ...] = (),
) -> UnresolvedShellEntry:
    return UnresolvedShellEntry(
        source_scope=entry.source_scope,
        entry_index=entry.entry_index,
        fixed_name=entry.fixed_name,
        prefab_path=entry.prefab_path,
        collision_id=collision_id,
        reason=reason,
        candidate_count=candidate_count,
        rcol_resources=resources,
    )
