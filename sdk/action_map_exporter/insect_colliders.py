from __future__ import annotations

import json
from pathlib import Path

from .request_sets import RequestSetCatalog, canonical_rcol_path
from .resource_relations import _RelationBuilder, _ResourceDescriptor
from .track_colliders import (
    _collider_groups,
    _instances,
    _load_pfb,
    _WEAPON_PREFAB_ROOT,
)

# app.Wp10Insect.requestActiveAttackCol(INSECT_ATK_TYPE type) enables request
# set `type` on the kinsect's own RequestSetCollider, so every ID of the
# kinsect RCOL is named by app.Wp10InsectDef.INSECT_ATK_TYPE.
INSECT_COMPONENT = "app.Wp10Insect"
INSECT_ATTACK_TYPE_ENUM = "app.Wp10InsectDef.INSECT_ATK_TYPE"
INSECT_SCOPE = "Wp10"
GAME_FUNCTION = "app.Wp10Insect.requestActiveAttackCol"


def build_insect_attack_relations(
    natives_directory: Path,
    enums_path: Path,
    request_sets: RequestSetCatalog,
) -> list[dict[str, object]]:
    attack_types = _attack_types(enums_path)
    rcols = _insect_rcols(natives_directory)
    builders: dict[tuple[object, ...], _RelationBuilder] = {}
    for (canonical, display_path), prefabs in sorted(rcols.items()):
        for value, name in sorted(attack_types.items()):
            matches = request_sets.find_by_resource(INSECT_SCOPE, canonical, value)
            if len(matches) != 1:
                continue
            request_set = matches[0]
            descriptor = _ResourceDescriptor(
                identity=f"insect:{INSECT_SCOPE}:{name.casefold()}",
                order=3_000_000 + value,
                internal_name=f"INSECT_{name}",
                name_guid="",
                japanese_name="",
                name_source="insect_attack_type_enum",
                suffix="",
                fallback_name=f"INSECT_{name}",
                role="insect",
            )
            key = (descriptor.identity, *request_set.target_key)
            builder = builders.get(key)
            if builder is None:
                builder = builders[key] = _RelationBuilder(
                    descriptor,
                    request_set,
                    "proven",
                    ({"kind": "insect_attack_type", "attackType": name},),
                )
            builder.add_source("static_insect_attack_collider")
            builder.add_method("insect_attack_type_request_set")
            builder.add_evidence(
                {
                    "gameFunction": GAME_FUNCTION,
                    "attackTypeEnum": INSECT_ATTACK_TYPE_ENUM,
                    "attackTypeValue": value,
                    "rcolResourcePath": display_path,
                    "prefabCount": len(prefabs),
                    "prefabExample": prefabs[0],
                }
            )
    return [builder.build() for builder in builders.values()]


def _attack_types(enums_path: Path) -> dict[int, str]:
    document = json.loads(enums_path.read_text(encoding="utf-8"))
    values = document.get(INSECT_ATTACK_TYPE_ENUM)
    if not isinstance(values, dict):
        raise ValueError(f"{enums_path} 缺少 {INSECT_ATTACK_TYPE_ENUM}")
    return {
        value: name
        for name, value in values.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def _insect_rcols(natives_directory: Path) -> dict[tuple[str, str], list[str]]:
    root = natives_directory.joinpath(*_WEAPON_PREFAB_ROOT)
    output: dict[tuple[str, str], list[str]] = {}
    for path in sorted(root.rglob("*.pfb.*.json"), key=lambda p: str(p).casefold()):
        document = _load_pfb(path)
        instances = _instances(document, path)
        for game_object in document.get("gameObjects", []):
            components = [
                instances[i] for i in game_object.get("componentInstanceIds", [])
            ]
            if not any(c.get("class") == INSECT_COMPONENT for c in components):
                continue
            for component in components:
                if component.get("class") != "via.physics.RequestSetCollider":
                    continue
                for rcol in _collider_groups(component, instances):
                    output.setdefault((canonical_rcol_path(rcol), rcol), []).append(
                        path.relative_to(natives_directory).as_posix()
                    )
    return output
