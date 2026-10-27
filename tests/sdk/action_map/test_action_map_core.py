from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from iced_x86 import Code


from sdk.action_map_exporter.builder import _relation_sort_key
from sdk.action_map_exporter.models import (
    ActionSeed,
    AmmoNameRecord,
    PfbResourceDocument,
    RequestSetIdentity,
    ShellEntryRecord,
)
from sdk.action_map_exporter.pe import PeImage
from sdk.action_map_exporter.pfb import PfbResourceCatalog
from sdk.action_map_exporter.request_sets import RequestSetCatalog
from sdk.action_map_exporter.resource_relations import build_resource_relations
from sdk.action_map_exporter.scanners import _code_name
from sdk.action_map_exporter.scanners import AmmoItemMapCatalog
from sdk.action_map_exporter.shell_relations import build_shell_relations
from sdk.action_map_exporter.shells import AmmoNameCatalog, ShellCatalog
from sdk.action_map_exporter.utils import murmur3_utf16


class InstructionCompatibilityTests(unittest.TestCase):
    def test_iced_python_names_match_action_map_contract(self) -> None:
        self.assertEqual(_code_name(Code.MOV_RM32_IMM32), "Mov_rm32_imm32")
        self.assertEqual(_code_name(Code.MOV_R64_IMM64), "Mov_r64_imm64")
        self.assertEqual(_code_name(Code.CMP_EAX_IMM32), "Cmp_EAX_imm32")

    def test_relation_rcol_order_matches_dotnet_ordinal_ignore_case(self) -> None:
        def relation(rcol: str) -> dict[str, object]:
            return {
                "scope": "Wp02",
                "actionOrder": 2,
                "actionGuideId": 1,
                "actionIdentity": "guide:Wp02:1",
                "rcol": rcol,
                "requestSetId": 1,
                "keyHash": 1,
                "sourceRequestSetOrdinal": 1,
            }

        values = [relation("Wp02_Attack.rcol"), relation("Wp02Sub_Attack.rcol")]
        values.sort(key=_relation_sort_key)
        self.assertEqual(values[0]["rcol"], "Wp02Sub_Attack.rcol")


class PeImageTests(unittest.TestCase):
    def test_maps_virtual_address_to_raw_section_bytes(self) -> None:
        image = bytearray(0x400)
        image[:2] = b"MZ"
        struct.pack_into("<I", image, 0x3C, 0x80)
        struct.pack_into(
            "<4sHHIIIHH",
            image,
            0x80,
            b"PE\0\0",
            0x8664,
            1,
            0,
            0,
            0,
            0xF0,
            0,
        )
        optional = 0x80 + 24
        struct.pack_into("<H", image, optional, 0x20B)
        struct.pack_into("<Q", image, optional + 24, 0x140000000)
        section = optional + 0xF0
        image[section : section + 8] = b".text\0\0\0"
        struct.pack_into("<IIII", image, section + 8, 0x100, 0x1000, 0x100, 0x200)
        image[0x210:0x214] = b"TEST"

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.exe"
            path.write_bytes(image)
            with PeImage(path) as pe:
                self.assertEqual(pe.image_base, 0x140000000)
                self.assertEqual(
                    pe.read_function_bytes(0x140001010, 4),
                    b"TEST",
                )


class ResourceRelationTests(unittest.TestCase):
    def test_follows_nested_prefab_to_exact_weapon_request_set(self) -> None:
        entry = ShellEntryRecord(
            source_scope="Wp11",
            shell_list_path="Wp11/Shell/Wp11ShellList.user.3.json",
            entry_index=0,
            target_scope="Wp11",
            fixed_id=0,
            fixed_name="NORMAL_LV1",
            shell_name_hash=1,
            ammo_type_name="",
            prefab_path="GameDesign/Player/ActionData/Wp11/Shell/Root.pfb",
            main_param_path="Wp11/Shell/MainParam/Normal.user",
            collision_ids=(0,),
        )
        root = PfbResourceDocument(
            prefab_path=entry.prefab_path,
            archive_path=entry.prefab_path + ".17",
            resources=("GameDesign/Player/ActionData/Wp11/Shell/Child.pfb",),
        )
        child = PfbResourceDocument(
            prefab_path="GameDesign/Player/ActionData/Wp11/Shell/Child.pfb",
            archive_path=("GameDesign/Player/ActionData/Wp11/Shell/Child.pfb.17"),
            resources=("GameDesign/Player/ActionData/Wp11/Collision/Shell/Test.rcol",),
        )
        request_set = RequestSetIdentity(
            scope="Wp11",
            rcol="Wp11/Collision/Shell/Test.rcol.38.json",
            request_set_id=0,
            key_hash=10,
            source_request_set_ordinal=0,
            user_data_type="app.col_user_data.AttackParamPlShell",
        )

        result = build_resource_relations(
            ShellCatalog([entry], AmmoNameCatalog([]), {}),
            PfbResourceCatalog([root, child]),
            RequestSetCatalog([request_set]),
            AmmoItemMapCatalog({}, []),
        )

        self.assertEqual(len(result.relations), 1)
        relation = result.relations[0]
        self.assertEqual(relation["scope"], "Wp11")
        self.assertEqual(relation["resourceIdentity"], "shell:Wp11:0")
        self.assertEqual(relation["requestSetId"], 0)
        self.assertEqual(relation["confidence"], "proven")
        self.assertEqual(
            relation["evidence"][0]["prefabTraversal"],
            [root.prefab_path, child.prefab_path],
        )

    def test_derives_repeated_resource_variant_without_weapon_hardcoding(self) -> None:
        prefab_path = "GameDesign/Player/ActionData/Wp11/Shell/Arrow.pfb"
        rcol_path = "GameDesign/Player/ActionData/Wp11/Collision/Shell/Arrow.rcol"
        entries = [
            ShellEntryRecord(
                source_scope="Wp11",
                shell_list_path="Wp11/Shell/Wp11ShellList.user.3.json",
                entry_index=index,
                target_scope="Wp11",
                fixed_id=index,
                fixed_name=f"NORMAL_LV{index + 1}",
                shell_name_hash=index,
                ammo_type_name="",
                prefab_path=prefab_path,
                main_param_path=f"Wp11/Shell/MainParam/Lv{index + 1}.user",
                collision_ids=(index,),
            )
            for index in range(2)
        ]
        entries.append(
            ShellEntryRecord(
                source_scope="Wp11",
                shell_list_path="Wp11/Shell/Wp11ShellList.user.3.json",
                entry_index=2,
                target_scope="Wp11",
                fixed_id=99,
                fixed_name="QUICK_SHOT",
                shell_name_hash=99,
                ammo_type_name="",
                prefab_path=prefab_path,
                main_param_path="Wp11/Shell/MainParam/Quick.user",
                collision_ids=(0,),
            )
        )
        records = [
            RequestSetIdentity(
                scope="Wp11",
                rcol="Wp11/Collision/Shell/Arrow.rcol.38.json",
                request_set_id=request_set_id,
                key_hash=100 + request_set_id,
                source_request_set_ordinal=ordinal,
                user_data_type="app.col_user_data.AttackParamPlShell",
                resource_paths=(
                    (
                        (
                            "GameDesign/Player/ActionData/Wp11/Collision/Collider/"
                            "Wp11PenetrateBottle_MultiHitCurve.user"
                        ),
                    )
                    if request_set_id >= 400
                    else ()
                ),
            )
            for ordinal, request_set_id in enumerate((0, 1, 400, 401))
        ]

        result = build_resource_relations(
            ShellCatalog(entries, AmmoNameCatalog([]), {}),
            PfbResourceCatalog(
                [
                    PfbResourceDocument(
                        prefab_path=prefab_path,
                        archive_path=prefab_path + ".17",
                        resources=(rcol_path,),
                    )
                ]
            ),
            RequestSetCatalog(records),
            AmmoItemMapCatalog({}, []),
        )

        self.assertEqual(result.derived_variant_relations, 3)
        variants = [
            relation
            for relation in result.relations
            if relation["confidence"] == "derived"
        ]
        self.assertEqual(
            sum(relation["requestSetId"] == 400 for relation in variants),
            2,
        )
        self.assertEqual(
            sum(relation["requestSetId"] == 401 for relation in variants),
            1,
        )
        self.assertTrue(
            all(
                relation["resourceNameSuffix"] == " [PENETRATE_BOTTLE]"
                for relation in variants
            )
        )

    def test_keeps_unclassified_shell_request_set_as_rcol_resource(self) -> None:
        entry = ShellEntryRecord(
            source_scope="Wp07",
            shell_list_path="Wp07/Shell/Wp07ShellList.user.3.json",
            entry_index=0,
            target_scope="Wp07",
            fixed_id=9,
            fixed_name="TEST_SHELL",
            shell_name_hash=9,
            ammo_type_name="",
            prefab_path="GameDesign/Player/ActionData/Wp07/Shell/Test.pfb",
            main_param_path="Wp07/Shell/MainParam/Test.user",
            collision_ids=(1,),
        )
        rcol_resource = "GameDesign/Player/ActionData/Wp07/Collision/Shell/Test.rcol"
        records = [
            RequestSetIdentity(
                scope="Wp07",
                rcol="Wp07/Collision/Shell/Test.rcol.38.json",
                request_set_id=value,
                key_hash=100 + value,
                source_request_set_ordinal=index,
                user_data_type="app.col_user_data.AttackParamPlShell",
            )
            for index, value in enumerate((1, 99))
        ]

        result = build_resource_relations(
            ShellCatalog([entry], AmmoNameCatalog([]), {}),
            PfbResourceCatalog(
                [
                    PfbResourceDocument(
                        prefab_path=entry.prefab_path,
                        archive_path=entry.prefab_path + ".17",
                        resources=(rcol_resource,),
                    )
                ]
            ),
            RequestSetCatalog(records),
            AmmoItemMapCatalog({}, []),
        )

        self.assertEqual(result.rcol_fallback_relations, 1)
        fallback = next(
            relation for relation in result.relations if relation["requestSetId"] == 99
        )
        self.assertEqual(fallback["resourceRole"], "rcol_fallback")
        self.assertEqual(fallback["confidence"], "structural")

    def test_shell_action_relation_keeps_weapon_request_set_scope(self) -> None:
        japanese_name = "test action"
        entry = ShellEntryRecord(
            source_scope="Wp11",
            shell_list_path="Wp11/Shell/Wp11ShellList.user.3.json",
            entry_index=0,
            target_scope="Wp11",
            fixed_id=1,
            fixed_name="TEST",
            shell_name_hash=1,
            ammo_type_name="",
            prefab_path="GameDesign/Player/ActionData/Wp11/Shell/Test.pfb",
            main_param_path="Wp11/Shell/MainParam/Test.user",
            collision_ids=(7,),
        )
        prefab = PfbResourceDocument(
            prefab_path=entry.prefab_path,
            archive_path=entry.prefab_path + ".17",
            resources=("GameDesign/Player/ActionData/Wp11/Collision/Shell/Test.rcol",),
        )
        request_set = RequestSetIdentity(
            scope="Wp11",
            rcol="Wp11/Collision/Shell/Test.rcol.38.json",
            request_set_id=7,
            key_hash=murmur3_utf16(japanese_name),
            source_request_set_ordinal=0,
        )
        action = ActionSeed(
            scope="Wp11",
            class_name="app.Wp11Action.cTest",
            guide_id=8,
            guide_order=9,
            internal_name="TEST_ACTION",
            name_guid="guid",
            japanese_name=japanese_name,
            source_files=(),
        )

        result = build_shell_relations(
            ShellCatalog([entry], AmmoNameCatalog([]), {}),
            PfbResourceCatalog([prefab]),
            RequestSetCatalog([request_set]),
            AmmoItemMapCatalog({}, []),
            [action],
            {action: []},
        )

        action_relation = next(
            relation
            for relation in result.relations
            if relation["actionIdentity"].startswith("guide:")
        )
        self.assertEqual(action_relation["scope"], "Wp11")
        self.assertEqual(action_relation["confidence"], "proven")

    def test_bowguns_share_ammo_resource_identity_across_request_sets(self) -> None:
        rcol_resource = (
            "GameDesign/Player/ActionData/WpGunCommon/Collision/Special.rcol"
        )
        entries = [
            ShellEntryRecord(
                source_scope=scope,
                shell_list_path=f"{scope}/Shell/{scope}ShellList.user.3.json",
                entry_index=0,
                target_scope="Ammo",
                fixed_id=5,
                fixed_name="SPECIAL_LV1",
                shell_name_hash=5,
                ammo_type_name="SPECIAL",
                prefab_path=(
                    "GameDesign/Player/ActionData/WpGunCommon/Shell/"
                    f"{scope}Special.pfb"
                ),
                main_param_path="WpGunCommon/Shell/MainParam/Special.user",
                collision_ids=(request_set_id,),
            )
            for scope, request_set_id in (("Wp12", 10), ("Wp13", 11))
        ]
        prefabs = [
            PfbResourceDocument(
                prefab_path=entry.prefab_path,
                archive_path=entry.prefab_path + ".17",
                resources=(rcol_resource,),
            )
            for entry in entries
        ]
        request_sets = [
            RequestSetIdentity(
                scope="Ammo",
                rcol="WpGunCommon/Collision/Special.rcol.38.json",
                request_set_id=request_set_id,
                key_hash=500 + request_set_id,
                source_request_set_ordinal=index,
                user_data_type="app.col_user_data.AttackParamPlShell",
            )
            for index, request_set_id in enumerate((10, 11))
        ]
        ammo_name = AmmoNameRecord(
            item_id="SPECIAL_AMMO",
            item_value=50,
            order=3,
            name_guid="ammo-guid",
            japanese_name="special ammo",
            japanese_name_hash=123,
        )

        result = build_resource_relations(
            ShellCatalog(entries, AmmoNameCatalog([ammo_name]), {7: "SPECIAL"}),
            PfbResourceCatalog(prefabs),
            RequestSetCatalog(request_sets),
            AmmoItemMapCatalog({"SPECIAL": ammo_name}, []),
        )

        self.assertEqual(len(result.relations), 2)
        self.assertEqual(
            {relation["resourceIdentity"] for relation in result.relations},
            {"ammo:item:ammo-guid"},
        )
        self.assertEqual(
            {relation["requestSetId"] for relation in result.relations},
            {10, 11},
        )


if __name__ == "__main__":
    unittest.main()
