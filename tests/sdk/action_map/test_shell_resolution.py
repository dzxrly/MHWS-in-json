from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch


from sdk.action_map_exporter.models import (
    ActionSeed,
    PfbResourceDocument,
    RequestSetIdentity,
    ShellEntryRecord,
)
from sdk.action_map_exporter.pfb import PfbResourceCatalog
from sdk.action_map_exporter.request_sets import RequestSetCatalog
from sdk.action_map_exporter.resource_relations import build_resource_relations
from sdk.action_map_exporter.scanners import AmmoItemMapCatalog
from sdk.action_map_exporter.shell_relations import build_shell_relations
from sdk.action_map_exporter.shell_requests import resolve_shell_requests
from sdk.action_map_exporter.shells import AmmoNameCatalog, ShellCatalog
from sdk.action_map_exporter.utils import murmur3_utf16


class ShellResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.action = ActionSeed(
            "Wp02", "app.cHunterWp02Action.TEST", 1, 1, "TEST", "", "Action", ()
        )
        self.entry = ShellEntryRecord(
            "Wp02",
            "Wp02/Shell/Test.user.3.json",
            0,
            "Wp02",
            0,
            "TEST",
            1,
            "",
            "GameDesign/Player/ActionData/Wp02/Shell/Root.pfb",
            "",
            (0,),
        )
        self.target = RequestSetIdentity(
            "Wp02",
            "Wp02/Collision/Shell/Test.rcol.38.json",
            0,
            murmur3_utf16(self.action.japanese_name),
            0,
            "app.col_user_data.AttackParamPlShell",
        )
        self.shells = ShellCatalog([self.entry], AmmoNameCatalog([]), {})
        self.ammo = AmmoItemMapCatalog({}, [])
        self.resource = "GameDesign/Player/ActionData/Wp02/Collision/Shell/Test.rcol"
        self.prefabs = PfbResourceCatalog(
            [
                PfbResourceDocument(
                    self.entry.prefab_path,
                    self.entry.prefab_path + ".17",
                    (self.resource, "natives/STM/" + self.resource + ".38"),
                )
            ]
        )

    def test_aliases_share_one_exact_target_and_retain_all_evidence(self) -> None:
        requests = RequestSetCatalog(
            [self.target, replace(self.target, resource_paths=("metadata.user",))]
        )
        resolution = resolve_shell_requests(self.shells, self.prefabs, requests)
        self.assertEqual(resolution.unresolved, [])
        self.assertEqual(
            {item.request_set.target_key for item in resolution.resolved},
            {self.target.target_key},
        )
        with (
            patch(
                "sdk.action_map_exporter.shell_relations.resolve_shell_requests",
                side_effect=AssertionError("must reuse resolution"),
            ),
            patch(
                "sdk.action_map_exporter.resource_relations.resolve_shell_requests",
                side_effect=AssertionError("must reuse resolution"),
            ),
        ):
            actions = build_shell_relations(
                self.shells,
                self.prefabs,
                requests,
                self.ammo,
                [self.action],
                {},
                resolution=resolution,
            )
            resources = build_resource_relations(
                self.shells, self.prefabs, requests, self.ammo, resolution=resolution
            )
        self.assertEqual(len(actions.relations), 1)
        self.assertEqual(len(resources.relations), 1)
        for evidence in (
            actions.relations[0]["shellEvidence"],
            resources.relations[0]["evidence"],
        ):
            self.assertEqual(len(evidence), 2)
            self.assertEqual(
                {item["rcolResourcePath"] for item in evidence},
                {self.resource, "natives/STM/" + self.resource + ".38"},
            )
            self.assertTrue(
                all(
                    item["prefabTraversal"] == [self.entry.prefab_path]
                    for item in evidence
                )
            )

    def test_distinct_ordinals_are_ambiguous_but_one_named_target_is_resolvable(
        self,
    ) -> None:
        duplicate = replace(self.target, source_request_set_ordinal=1)
        result = resolve_shell_requests(
            self.shells, self.prefabs, RequestSetCatalog([self.target, duplicate])
        )
        self.assertEqual(result.resolved, [])
        self.assertEqual(result.unresolved[0].candidate_count, 2)
        self.assertEqual(result.unresolved[0].reason, "rcol_request_set_ambiguous")
        result = resolve_shell_requests(
            self.shells,
            self.prefabs,
            RequestSetCatalog([self.target, replace(duplicate, key_hash=0)]),
        )
        self.assertEqual(
            {item.request_set.target_key for item in result.resolved},
            {self.target.target_key},
        )

    def test_unmatched_shell_produces_resources_without_pseudo_actions(self) -> None:
        requests = RequestSetCatalog([self.target])
        actions = build_shell_relations(
            self.shells, self.prefabs, requests, self.ammo, [], {}
        )
        resources = build_resource_relations(
            self.shells, self.prefabs, requests, self.ammo
        )
        self.assertEqual(actions.relations, [])
        self.assertEqual(len(resources.relations), 1)


if __name__ == "__main__":
    unittest.main()
