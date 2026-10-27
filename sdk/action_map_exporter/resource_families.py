"""Conservative ammo-family membership, independent of runtime activation."""

from __future__ import annotations

from collections import defaultdict

from .models import AmmoNameRecord, RequestSetIdentity
from .request_sets import RequestSetCatalog, canonical_rcol_path
from .shell_requests import ResolvedShellRequest, ShellRequestResolution


def find_named_family_members(
    resolution: ShellRequestResolution,
    request_sets: RequestSetCatalog,
    names: dict[tuple[str, int], AmmoNameRecord],
) -> list[tuple[ResolvedShellRequest, RequestSetIdentity]]:
    by_owner_resource: dict[tuple[str, int, str], list[ResolvedShellRequest]] = (
        defaultdict(list)
    )
    for item in resolution.resolved:
        if item.entry.target_scope == "Ammo":
            by_owner_resource[
                (
                    item.entry.source_scope,
                    item.entry.entry_index,
                    canonical_rcol_path(item.rcol_resource_path),
                )
            ].append(item)

    def has_role(item: ResolvedShellRequest, role: str) -> bool:
        return any(
            ref.collision_id == item.collision_id and ref.role == role
            for ref in item.entry.collision_references
        )

    # Learn only shape transitions explicitly configured as primary/additional
    # in the current inputs. Shared numerical damage/curve is insufficient.
    shape_pairs = set()
    for items in by_owner_resource.values():
        for main in (x for x in items if has_role(x, "primary")):
            for extra in (x for x in items if has_role(x, "additional_collision")):
                if main.request_set.shape_types and extra.request_set.shape_types:
                    shape_pairs.add(
                        (main.request_set.shape_types, extra.request_set.shape_types)
                    )

    result = []
    for (scope, rcol), references in sorted(resolution.references.items()):
        if scope != "Ammo":
            continue
        owners = {
            (str(ref["sourceScope"]), int(ref["entryIndex"])) for ref in references
        }
        owner_items = [
            by_owner_resource.get((*owner, rcol), []) for owner in sorted(owners)
        ]
        if not owner_items or any(not items for items in owner_items):
            continue
        if any(owner not in names for owner in owners):
            continue
        identities = {names[owner].name_guid.casefold() for owner in owners}
        ammo_types = {items[0].entry.ammo_type_name for items in owner_items}
        if (
            len(identities) != 1
            or "" in identities
            or len(ammo_types) != 1
            or "" in ammo_types
        ):
            continue
        primaries = [
            item for items in owner_items for item in items if has_role(item, "primary")
        ]
        for target in request_sets.find_in_resource(scope, rcol):
            if not target.attack_payload_hash or not target.user_data_type.endswith(
                "AttackParamPlShell"
            ):
                continue
            anchors = [
                item
                for item in primaries
                if item.request_set.attack_payload_hash == target.attack_payload_hash
                and (item.request_set.shape_types, target.shape_types) in shape_pairs
                and item.request_set.target_key != target.target_key
            ]
            if len({a.request_set.target_key for a in anchors}) != 1:
                continue
            if len({a.entry.ammo_level for a in anchors}) != 1:
                continue
            result.extend((anchor, target) for anchor in anchors)
    return result
