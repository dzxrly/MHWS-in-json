import json
from pathlib import Path
import tempfile
import unittest

from sdk.action_map_exporter.action_relations import build_action_relations
from sdk.action_map_exporter.models import (
    ActionSeed,
    Il2CppMethod,
    MotionSetHit,
    MotionTarget,
    MotlistRequestSetEvent,
    RequestSetIdentity,
)
from sdk.action_map_exporter.request_sets import RequestSetCatalog
from sdk.action_map_exporter.track_colliders import (
    WEAPON_BODY_TRACK,
    WEAPON_TRACK,
    TrackColliderCatalog,
    TrackColliderRoute,
)

ATTACK = "Wp06/Collision/Collider/Wp06_Attack.rcol.38.json"
PHYSICAL = "Wp06/Collision/Collider/Wp06_PhysicalAttack.rcol.38.json"
SHELL = "Wp06/Collision/Collider/Wp06_Shell.rcol.38.json"


def _pfb(instances, game_objects):
    return {
        "_format": "mhws_pfb_v1",
        "gameObjects": game_objects,
        "instances": instances,
    }


def _weapon_prefab(wp_type, is_sub, rcol):
    return _pfb(
        [
            {"id": 1, "class": "via.GameObject", "fields": {}},
            {
                "id": 2,
                "class": "app.Weapon",
                "fields": {"_WpType": wp_type, "_IsSubWeapon": is_sub},
            },
            {
                "id": 3,
                "class": "via.physics.RequestSetCollider.RequestSetGroup",
                "fields": {"v0": f"GameDesign/Player/ActionData/{rcol}"},
            },
            {
                "id": 4,
                "class": "via.physics.RequestSetCollider",
                "fields": {
                    "v0": 1,
                    "v2": [""],
                    "v3": [[3, 0, 0, 0]],
                    "v5": [4, 0, 0, 0],
                },
            },
        ],
        [{"instanceId": 1, "componentInstanceIds": [2, 4]}],
    )


class TrackColliderRoutingTests(unittest.TestCase):
    def setUp(self):
        self.action = ActionSeed(
            "Wp06", "app.Wp06Action.cStab1", 1, 1, "WP06_STAB_1", "", "中段突き", ()
        )
        self.records = [
            RequestSetIdentity("Wp06", ATTACK, 0, 4160249040, 0),
            RequestSetIdentity("Wp06", ATTACK, 700, 819825863, 49),
            RequestSetIdentity("Wp06", PHYSICAL, 0, 1929819279, 0),
            RequestSetIdentity("Wp06", SHELL, 1, 719562787, 1),
        ]
        self.routes = TrackColliderCatalog(
            {
                ("Wp06", WEAPON_TRACK): TrackColliderRoute(
                    WEAPON_TRACK,
                    "weapon_prefab",
                    ("wp06/collision/collider/wp06_attack.rcol",),
                ),
                ("Wp06", WEAPON_BODY_TRACK): TrackColliderRoute(
                    WEAPON_BODY_TRACK,
                    "player_prefab_group_11",
                    ("wp06/collision/collider/wp06_physicalattack.rcol",),
                ),
            }
        )

    def resolve(self, events, routes):
        target = MotionTarget(
            "Wp06",
            (20 << 12) | 210,
            20,
            210,
            "wp06_00.motlist",
            "wp06_00",
            tuple(events),
        )
        hit = MotionSetHit(
            self.action.class_name, ".ctor", 0x1000, 0x1004, "Mov_rm32_imm32", 1, target
        )
        methods = {
            self.action.class_name: [
                Il2CppMethod(self.action.class_name, ".ctor", 0x1000)
            ]
        }
        return build_action_relations(
            [self.action],
            {self.action: [hit]},
            RequestSetCatalog(self.records),
            methods,
            guides=[],
            track_colliders=routes,
        )

    @staticmethod
    def event(request_set_id, track):
        return MotlistRequestSetEvent(
            210, "wp06_00_210", request_set_id, "clip", 0, track, 0, track, 25.0, 32.0
        )

    def test_weapon_track_selects_weapon_collider_instead_of_body_rcol(self):
        events = [self.event(0, WEAPON_TRACK), self.event(700, WEAPON_TRACK)]
        unrouted = self.resolve(events, None)
        self.assertEqual([r["requestSetId"] for r in unrouted.relations], [700])
        self.assertEqual(unrouted.ambiguous_coordinates, {("Wp06", 0)})

        routed = self.resolve(events, self.routes)
        relations = {r["requestSetId"]: r for r in routed.relations}
        self.assertEqual(sorted(relations), [0, 700])
        self.assertEqual(relations[0]["rcol"], ATTACK)
        self.assertEqual(relations[0]["resolutionMethods"], ["track_owner_collider"])
        self.assertEqual(
            relations[0]["evidence"][0]["trackColliderOwner"], "weapon_prefab"
        )
        self.assertEqual(routed.ambiguous_coordinates, set())

    def test_weapon_body_track_selects_player_weapon_group(self):
        routed = self.resolve([self.event(0, WEAPON_BODY_TRACK)], self.routes)
        self.assertEqual([r["rcol"] for r in routed.relations], [PHYSICAL])

    def test_id_outside_track_collider_is_reported_separately(self):
        routed = self.resolve([self.event(1, WEAPON_TRACK)], self.routes)
        self.assertEqual(routed.relations, [])
        self.assertEqual(
            [item.reason for item in routed.unresolved_coordinates],
            ["request_set_not_in_track_collider"],
        )

    def test_catalog_reads_weapon_prefabs_and_player_group_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            natives = Path(temporary).resolve() / "natives"
            weapon_dir = natives / "STM/GameDesign/Equip/_Prefab/Weapon/Wp06/00/0000"
            player_dir = natives / "STM/GameDesign/Player/_Prefab/Runtime"
            weapon_dir.mkdir(parents=True)
            player_dir.mkdir(parents=True)
            for side, is_sub, rcol in (
                (0, False, "Wp06/Collision/Collider/Wp06_Attack.rcol"),
                (1, True, "Wp06/Collision/Collider/Wp06_SubAttack.rcol"),
            ):
                (weapon_dir / f"it0600_0000_{side}.pfb.18.json").write_text(
                    json.dumps(_weapon_prefab(6, is_sub, rcol)), encoding="utf-8"
                )
            names = [
                "PlBody",
                "PlAttack",
                "PlSensor",
                "PlZone_Master",
                "PlPhysics",
                *(f"Wp{index:02d}_PhysicalAttack" for index in range(12)),
            ]
            groups = [
                {
                    "id": 10 + index,
                    "class": "via.physics.RequestSetCollider.RequestSetGroup",
                    "fields": {"v0": f"GameDesign/Player/ActionData/X/{name}.rcol"},
                }
                for index, name in enumerate(names)
            ]
            collider = {
                "id": 2,
                "class": "via.physics.RequestSetCollider",
                "fields": {"v3": [[group["id"], 0, 0, 0] for group in groups]},
            }
            (player_dir / "Player.pfb.18.json").write_text(
                json.dumps(_pfb([collider, *groups], [])), encoding="utf-8"
            )

            catalog = TrackColliderCatalog.load(natives)

        self.assertEqual(
            catalog.route("Wp06", WEAPON_TRACK).rcols,
            (
                "wp06/collision/collider/wp06_attack.rcol",
                "wp06/collision/collider/wp06_subattack.rcol",
            ),
        )
        self.assertEqual(
            catalog.route("Wp06", WEAPON_BODY_TRACK).rcols,
            ("x/wp06_physicalattack.rcol",),
        )
        self.assertIsNone(catalog.route("Wp00", WEAPON_TRACK))


if __name__ == "__main__":
    unittest.main()
