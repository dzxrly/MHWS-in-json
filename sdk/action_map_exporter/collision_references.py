"""Preserve configured collider membership without inventing hit order."""

from __future__ import annotations

from .models import ShellCollisionReference, ShellEntryRecord


def additional_collision_references(
    document: object, source_path: str
) -> tuple[ShellCollisionReference, ...]:
    result: list[ShellCollisionReference] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for name, role in (
                ("_SubCollisionIDList", "sub_collision"),
                ("_AditionalColList", "additional_collision"),
            ):
                ids = value.get(name)
                if not isinstance(ids, list):
                    continue
                enabled = (
                    value.get("_DefaltEnable")
                    if role == "additional_collision"
                    else None
                )
                for index, collision_id in enumerate(ids):
                    if (
                        isinstance(collision_id, int)
                        and not isinstance(collision_id, bool)
                        and collision_id >= 0
                    ):
                        result.append(
                            ShellCollisionReference(
                                collision_id,
                                role,
                                name,
                                source_path,
                                index,
                                enabled if isinstance(enabled, bool) else None,
                            )
                        )
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    return tuple(dict.fromkeys(result))


def collision_evidence(entry: ShellEntryRecord, collision_id: int) -> dict[str, object]:
    refs = [
        ref for ref in entry.collision_references if ref.collision_id == collision_id
    ]
    if not refs:
        return {}
    return {
        "ammoLevel": entry.ammo_level,
        "collisionReferences": [
            {
                "role": ref.role,
                "sourceField": ref.source_field,
                "sourcePath": ref.source_path,
                "listIndex": ref.list_index,
                "enabledByDefault": ref.enabled_by_default,
            }
            for ref in refs
        ],
    }


def collision_conditions(
    entry: ShellEntryRecord, collision_id: int
) -> tuple[dict[str, object], ...]:
    roles = sorted(
        {
            ref.role
            for ref in entry.collision_references
            if ref.collision_id == collision_id
        }
    )
    if not roles:
        return ()
    return (
        {
            "kind": "collision_configuration",
            "roles": roles,
            "ammoLevel": entry.ammo_level,
        },
    )
