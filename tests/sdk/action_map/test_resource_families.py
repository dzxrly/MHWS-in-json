from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from sdk.action_map_exporter.collision_references import additional_collision_references
from sdk.action_map_exporter.models import (
    AmmoNameRecord,
    PfbResourceDocument,
    RequestSetIdentity,
    ShellCollisionReference,
    ShellEntryRecord,
)
from sdk.action_map_exporter.pfb import PfbResourceCatalog
from sdk.action_map_exporter.request_sets import RequestSetCatalog, _attack_payload_hash
from sdk.action_map_exporter.resource_relations import build_resource_relations
from sdk.action_map_exporter.scanners import AmmoItemMapCatalog
from sdk.action_map_exporter.shells import AmmoNameCatalog, ShellCatalog


class ResourceFamilyTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            ShellEntryRecord(
                "Wp12",
                "shells.json",
                i,
                "Ammo",
                i,
                name,
                i,
                name,
                f"GameDesign/{name}.pfb",
                f"GameDesign/{name}.user",
                ids,
                tuple(
                    ShellCollisionReference(
                        rid,
                        "primary" if j == 0 else "additional_collision",
                        "_AttackCollisionID" if j == 0 else "_AditionalColList",
                        "params.json",
                        None if j == 0 else j - 1,
                    )
                    for j, rid in enumerate(ids)
                ),
            )
            for i, (name, ids) in enumerate((("PATTERN", (0, 3)), ("FAMILY", (0,))))
        ]
        self.names = {
            name: AmmoNameRecord(
                name, i, i, f"00000000-0000-0000-0000-{i + 1:012d}", name, i
            )
            for i, name in enumerate(("PATTERN", "FAMILY", "OTHER"))
        }
        self.prefabs = PfbResourceCatalog(
            [
                PfbResourceDocument(
                    entry.prefab_path,
                    entry.prefab_path + ".18",
                    (
                        f"GameDesign/Player/ActionData/WpGunCommon/{entry.fixed_name}.rcol",
                    ),
                )
                for entry in self.entries
            ]
        )
        self.records = [
            RequestSetIdentity(
                "Ammo",
                f"WpGunCommon/{name}.rcol.38.json",
                rid,
                rid + 10,
                ordinal,
                "app.col_user_data.AttackParamPlShell",
                ("shared_MultiHitCurve.user",),
                "1" * 64,
                (shape,),
            )
            for name, values in (
                ("PATTERN", ((0, "ContinuousSphere"), (3, "Capsule"))),
                ("FAMILY", ((0, "ContinuousSphere"), (1, "Capsule"), (2, "Capsule"))),
            )
            for ordinal, (rid, shape) in enumerate(values)
        ]

    def build(self):
        return build_resource_relations(
            ShellCatalog(
                self.entries,
                AmmoNameCatalog([]),
                {i: name for i, name in enumerate(self.names)},
            ),
            self.prefabs,
            RequestSetCatalog(self.records),
            AmmoItemMapCatalog(self.names, []),
        )

    def test_exclusive_named_family_keeps_activation_unverified(self):
        result = self.build()
        self.assertEqual(result.derived_family_relations, 2)
        rows = [
            r for r in result.relations if r["source"] == "static_shell_resource_family"
        ]
        self.assertEqual({r["requestSetId"] for r in rows}, {1, 2})
        for row in rows:
            self.assertEqual(row["confidence"], "derived")
            self.assertEqual(row["resourceNameGuid"], self.names["FAMILY"].name_guid)
            self.assertEqual(
                row["resourceIdentity"],
                f"ammo:item:{self.names['FAMILY'].name_guid}:family",
            )
            self.assertIn("activation unverified", row["resourceNameSuffix"])
            self.assertEqual(row["conditions"][0]["activation"], "unverified")
            self.assertFalse(row["evidence"][0]["activationConfirmed"])

    def test_shared_curve_without_matching_payload_is_rejected(self):
        self.records[-2:] = [
            replace(r, attack_payload_hash="2" * 64) for r in self.records[-2:]
        ]
        self.assertEqual(self.build().derived_family_relations, 0)

    def test_requires_explicit_configured_shape_role(self):
        self.entries[0] = replace(
            self.entries[0],
            collision_references=self.entries[0].collision_references[:1],
        )
        self.assertEqual(self.build().derived_family_relations, 0)

    def test_shared_resource_with_different_named_owner_is_rejected(self):
        self.entries.append(
            replace(
                self.entries[1],
                entry_index=2,
                fixed_id=2,
                fixed_name="OTHER",
                ammo_type_name="OTHER",
            )
        )
        self.assertEqual(self.build().derived_family_relations, 0)

    def test_requires_all_resource_owners_to_be_resolved(self):
        self.entries.append(
            replace(self.entries[1], entry_index=2, collision_ids=(99,))
        )
        self.assertEqual(self.build().derived_family_relations, 0)

    def test_does_not_transfer_ammo_name_to_weapon_scope(self):
        self.entries[1] = replace(self.entries[1], target_scope="Wp11")
        self.records = [
            replace(r, scope="Wp11") if "FAMILY" in r.rcol else r for r in self.records
        ]
        self.assertEqual(self.build().derived_family_relations, 0)

    def test_duplicate_request_id_retains_each_full_identity(self):
        self.records[-1] = replace(self.records[-1], request_set_id=1)
        rows = [
            r
            for r in self.build().relations
            if r["source"] == "static_shell_resource_family"
        ]
        self.assertEqual(
            {
                (r["requestSetId"], r["keyHash"], r["sourceRequestSetOrdinal"])
                for r in rows
            },
            {(1, 11, 1), (1, 12, 2)},
        )

    def test_configuration_preserves_roles_level_and_list_index(self):
        refs = additional_collision_references(
            {
                "Part": {
                    "_AditionalColList": [3, True, 4],
                    "_DefaltEnable": False,
                    "_SubCollisionIDList": [8],
                }
            },
            "main.user",
        )
        self.assertEqual(
            [(r.collision_id, r.role, r.list_index) for r in refs],
            [
                (8, "sub_collision", 0),
                (3, "additional_collision", 0),
                (4, "additional_collision", 2),
            ],
        )
        self.assertIs(refs[1].enabled_by_default, False)
        self.entries[0] = replace(self.entries[0], ammo_level=2)
        row = next(
            r
            for r in self.build().relations
            if r["rcol"].endswith("PATTERN.rcol.38.json") and r["requestSetId"] == 3
        )
        self.assertEqual(
            row["conditions"][0],
            {
                "kind": "collision_configuration",
                "roles": ["additional_collision"],
                "ammoLevel": 2,
            },
        )

    def test_payload_comparison_ignores_only_local_identity(self):
        def payload(index, attack, path="curve.user"):
            return {
                "userData": {
                    "app.col_user_data.AttackParamPlShell": {
                        "RequestSetIndex": index,
                        "_Attack": attack,
                        "_Curve": {"path": path, "ref_instance_id": index},
                    }
                }
            }

        self.assertEqual(
            _attack_payload_hash(payload(1, 20)), _attack_payload_hash(payload(2, 20))
        )
        self.assertNotEqual(
            _attack_payload_hash(payload(1, 20)), _attack_payload_hash(payload(1, 21))
        )
        self.assertNotEqual(
            _attack_payload_hash(payload(1, 20)),
            _attack_payload_hash(payload(1, 20, "other.user")),
        )


if __name__ == "__main__":
    unittest.main()
