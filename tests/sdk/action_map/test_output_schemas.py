"""Validate sample ActionMap and MOTLIST output against the published schemas."""

import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from sdk.action_map_exporter.action_relations import build_action_relations
from sdk.action_map_exporter.builder import FORMAT_NAME, _merge_action_relations
from sdk.action_map_exporter.external_collisions import (
    ExternalCollisionHit,
    build_external_collision_relations,
    handling_owner,
)
from sdk.action_map_exporter.insect_colliders import build_insect_attack_relations
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


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3] / "sdk/action_map_exporter/data" / name
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _assert_valid(test: unittest.TestCase, validator, document) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    test.assertEqual([f"{list(error.path)}: {error.message}" for error in errors], [])


class ActionMapSchemaTests(unittest.TestCase):
    def test_sample_action_map_matches_schema(self):
        attack = "Wp06/Collision/Collider/Wp06_Attack.rcol.38.json"
        physical = "Wp06/Collision/Collider/Wp06_PhysicalAttack.rcol.38.json"
        cb_attack = "Wp09/Collision/Collider/Wp09_Attack.rcol.38.json"
        insect = "Wp10/Collision/Collider/Wp10_Insect_Attack.rcol.38.json"
        request_sets = RequestSetCatalog(
            [
                RequestSetIdentity("Wp06", attack, 0, 4160249040, 0),
                RequestSetIdentity("Wp06", physical, 0, 1929819279, 0),
                RequestSetIdentity("Wp09", cb_attack, 99, 123, 5),
                RequestSetIdentity("Wp10", insect, 0, 11, 0),
                RequestSetIdentity("Wp10", insect, 2, 12, 2),
            ]
        )
        routes = TrackColliderCatalog(
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
                ("Wp09", WEAPON_TRACK): TrackColliderRoute(
                    WEAPON_TRACK,
                    "weapon_prefab",
                    ("wp09/collision/collider/wp09_attack.rcol",),
                ),
            }
        )

        # A guided action whose motion comes from an inherited base method.
        action = ActionSeed(
            "Wp06", "app.Wp06Action.cStab3", 7, 3, "WP06_STAB_3", "guid", "中段突き", ()
        )
        event = MotlistRequestSetEvent(
            213, "wp06_00_213", 0, "clip", 0, WEAPON_TRACK, 0, WEAPON_TRACK, 25.0, 32.0
        )
        target = MotionTarget(
            "Wp06", (20 << 12) | 213, 20, 213, "wp06_00.motlist", "wp06_00", (event,)
        )
        hit = MotionSetHit(
            "app.Wp06Action.cStabBase",
            "doEnter1",
            0x1000,
            0x1010,
            "Mov_r32_imm32",
            1,
            target,
        )
        methods = {
            action.class_name: [Il2CppMethod(action.class_name, ".ctor1", 0x2000)]
        }
        motion_relations = build_action_relations(
            [action],
            {action: [hit]},
            request_sets,
            methods,
            guides=[],
            track_colliders=routes,
        ).relations

        handling_method = Il2CppMethod("app.cHunterWp09Handling", "doUpdate1", 0x3000)
        external_relations = build_external_collision_relations(
            [
                (
                    handling_owner("Wp09", "app.cHunterWp09Handling"),
                    [ExternalCollisionHit(handling_method, 0x3010, 99)],
                )
            ],
            request_sets,
            routes,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            prefab_dir = (
                root / "natives/STM/GameDesign/Equip/_Prefab/Weapon/Wp10/03/0000"
            )
            prefab_dir.mkdir(parents=True)
            (prefab_dir / "it1003_0000_0.pfb.18.json").write_text(
                json.dumps(
                    {
                        "_format": "mhws_pfb_v1",
                        "gameObjects": [
                            {"instanceId": 1, "componentInstanceIds": [2, 4]}
                        ],
                        "instances": [
                            {"id": 1, "class": "via.GameObject", "fields": {}},
                            {"id": 2, "class": "app.Wp10Insect", "fields": {}},
                            {
                                "id": 3,
                                "class": "via.physics.RequestSetCollider.RequestSetGroup",
                                "fields": {
                                    "v0": "GameDesign/Player/ActionData/Wp10/Collision/"
                                    "Collider/Wp10_Insect_Attack.rcol"
                                },
                            },
                            {
                                "id": 4,
                                "class": "via.physics.RequestSetCollider",
                                "fields": {"v3": [[3, 0, 0, 0]]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            enums = root / "Enums_Internal.json"
            enums.write_text(
                json.dumps(
                    {"app.Wp10InsectDef.INSECT_ATK_TYPE": {"NORMAL": 0, "DIVE": 2}}
                ),
                encoding="utf-8",
            )
            resource_relations = build_insect_attack_relations(
                root / "natives", enums, request_sets
            )

        document = {
            "_format": FORMAT_NAME,
            "inputs": {},
            "statistics": {},
            "actionRelations": _merge_action_relations(
                [*motion_relations, *external_relations]
            ),
            "resourceRelations": resource_relations,
            "unresolvedNames": [],
        }
        self.assertEqual(len(document["actionRelations"]), 2)
        self.assertEqual(
            {relation["resourceRole"] for relation in resource_relations}, {"insect"}
        )
        _assert_valid(self, _validator("action-map-v2.schema.json"), document)


if __name__ == "__main__":
    unittest.main()
