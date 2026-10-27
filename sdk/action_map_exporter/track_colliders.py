from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path

from .request_sets import canonical_rcol_path

PFB_FORMAT = "mhws_pfb_v1"
WEAPON_TRACK = "app.motion_track.AttackCollision_PlWp"
WEAPON_BODY_TRACK = "app.motion_track.AttackCollision_PlWpBody"
# HunterCharacter.cMotionSupporter.evMotionTrack_WpBodyAttackCollision sets the
# hunter ColliderSwitcher._AttackResourceIndex to WpType + 5 before activating
# the track's request set; Player.pfb lists PlBody/PlAttack/PlSensor/PlZone/
# PlPhysics ahead of the per-weapon PhysicalAttack groups.
WEAPON_BODY_GROUP_OFFSET = 5

_REQUEST_SET_COLLIDER = "via.physics.RequestSetCollider"
_REQUEST_SET_GROUP = "via.physics.RequestSetCollider.RequestSetGroup"
_WEAPON_COMPONENT = "app.Weapon"
_WEAPON_PREFAB_ROOT = ("STM", "GameDesign", "Equip", "_Prefab", "Weapon")
_PLAYER_PREFAB_ROOT = ("STM", "GameDesign", "Player", "_Prefab", "Runtime")


@dataclass(frozen=True, slots=True)
class TrackColliderRoute:
    track_name: str
    owner: str
    rcols: tuple[str, ...]


class TrackColliderCatalog:
    """Request-set colliders that each player attack track activates in game.

    app.Weapon.evMotionTrack_AttackCollision handles AttackCollision_PlWp on
    every equipped Weapon component (main and sub weapon) through that weapon's
    own ColliderSwitcher, so the track can only reach the RCOLs referenced by the
    weapon prefabs' RequestSetCollider. AttackCollision_PlWpBody goes through the
    hunter's RequestSetCollider group selected by WEAPON_BODY_GROUP_OFFSET.
    """

    def __init__(self, routes: dict[tuple[str, str], TrackColliderRoute]) -> None:
        self.routes = routes

    @classmethod
    def load(cls, natives_directory: Path) -> "TrackColliderCatalog":
        weapon_root = natives_directory.joinpath(*_WEAPON_PREFAB_ROOT)
        player_root = natives_directory.joinpath(*_PLAYER_PREFAB_ROOT)
        if not weapon_root.is_dir():
            raise FileNotFoundError(f"武器 PFB JSON 目录不存在: {weapon_root}")
        player_paths = sorted(player_root.glob("Player.pfb.*.json"))
        if len(player_paths) != 1:
            raise FileNotFoundError(
                f"需要唯一的 Player.pfb JSON，实际找到 {len(player_paths)} 个: {player_root}"
            )

        weapon_rcols: dict[str, dict[str, str]] = defaultdict(dict)
        for path in sorted(
            weapon_root.rglob("*.pfb.*.json"), key=lambda p: str(p).casefold()
        ):
            for wp_type, groups in _weapon_collider_groups(_load_pfb(path), path):
                scope = f"Wp{wp_type:02d}"
                for rcol in groups:
                    weapon_rcols[scope].setdefault(canonical_rcol_path(rcol), rcol)

        routes: dict[tuple[str, str], TrackColliderRoute] = {}
        for scope, rcols in weapon_rcols.items():
            routes[(scope, WEAPON_TRACK)] = TrackColliderRoute(
                track_name=WEAPON_TRACK,
                owner="weapon_prefab",
                rcols=tuple(sorted(rcols, key=str.casefold)),
            )

        player_groups = _player_collider_groups(
            _load_pfb(player_paths[0]), player_paths[0]
        )
        for scope in weapon_rcols:
            index = int(scope[2:]) + WEAPON_BODY_GROUP_OFFSET
            if index >= len(player_groups):
                raise ValueError(
                    f"Player.pfb RequestSetCollider 组数 {len(player_groups)} "
                    f"不足以覆盖 {scope} 的 WpBody 组 {index}"
                )
            routes[(scope, WEAPON_BODY_TRACK)] = TrackColliderRoute(
                track_name=WEAPON_BODY_TRACK,
                owner=f"player_prefab_group_{index}",
                rcols=(canonical_rcol_path(player_groups[index]),),
            )
        return cls(routes)

    def route(self, scope: str, track_name: str) -> TrackColliderRoute | None:
        return self.routes.get((scope, track_name))


def _load_pfb(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("_format") != PFB_FORMAT:
        raise ValueError(f"不是 {PFB_FORMAT} PFB JSON: {path}")
    return document


def _weapon_collider_groups(
    document: dict[str, object],
    path: Path,
) -> list[tuple[int, list[str]]]:
    instances = _instances(document, path)
    output: list[tuple[int, list[str]]] = []
    for game_object in document.get("gameObjects", []):
        components = [instances[i] for i in game_object.get("componentInstanceIds", [])]
        weapons = [c for c in components if c.get("class") == _WEAPON_COMPONENT]
        if not weapons:
            continue
        if len(weapons) != 1:
            raise ValueError(f"同一 GameObject 含多个 app.Weapon: {path}")
        wp_type = weapons[0].get("fields", {}).get("_WpType")
        if not isinstance(wp_type, int) or isinstance(wp_type, bool):
            raise ValueError(f"app.Weapon 缺少整数 _WpType: {path}")
        groups = [
            group
            for component in components
            if component.get("class") == _REQUEST_SET_COLLIDER
            for group in _collider_groups(component, instances)
        ]
        output.append((wp_type, groups))
    return output


def _player_collider_groups(document: dict[str, object], path: Path) -> list[str]:
    instances = _instances(document, path)
    colliders = [
        instance
        for instance in instances.values()
        if instance.get("class") == _REQUEST_SET_COLLIDER
    ]
    if len(colliders) != 1:
        raise ValueError(
            f"Player.pfb 应只有一个 RequestSetCollider，实际 {len(colliders)}: {path}"
        )
    return _collider_groups(colliders[0], instances)


def _collider_groups(
    collider: dict[str, object],
    instances: dict[int, dict[str, object]],
) -> list[str]:
    # RequestSetCollider fields are unnamed in the RSZ template; the group list
    # is the field whose elements are instance references to RequestSetGroup.
    group_lists = []
    for value in collider.get("fields", {}).values():
        if not isinstance(value, list) or not value:
            continue
        references = [
            item[0]
            for item in value
            if isinstance(item, list) and item and isinstance(item[0], int)
        ]
        if len(references) == len(value) and all(
            instances.get(ref, {}).get("class") == _REQUEST_SET_GROUP
            for ref in references
        ):
            group_lists.append(references)
    if len(group_lists) != 1:
        raise ValueError(
            f"RequestSetCollider 应只有一个 RequestSetGroup 列表，实际 {len(group_lists)}"
        )
    output = []
    for reference in group_lists[0]:
        path = next(iter(instances[reference].get("fields", {}).values()), "")
        if not isinstance(path, str):
            raise ValueError(f"RequestSetGroup {reference} 缺少 RCOL 路径")
        output.append(path)
    return output


def _instances(document: dict[str, object], path: Path) -> dict[int, dict[str, object]]:
    values = document.get("instances")
    if not isinstance(values, list):
        raise ValueError(f"PFB JSON 缺少 instances: {path}")
    return {
        int(item["id"]): item
        for item in values
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
