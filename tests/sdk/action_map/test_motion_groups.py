from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest

from iced_x86 import Decoder


from sdk.action_map_exporter.models import Il2CppMethod, MotionTarget
from sdk.action_map_exporter.motion_catalogs import MotionTargetCatalog
from sdk.action_map_exporter.motion_groups import MotionGroupCatalog, pack_group_set_id
from sdk.action_map_exporter.scanners import MotionSetScanner, _group_value_is_requested

GROUP_ID = 0x5EF6CFD6F56
GROUP_SET = pack_group_set_id(20, GROUP_ID)
MOTION_SET = (20 << 12) | 630
FUNCTION = 0x140001000


def _meb(group_set_id: int = GROUP_SET, extend_path: str = "") -> list[object]:
    extends = []
    if extend_path:
        extends.append(
            {
                "ace.user_data.MotionExtendBank.SetData": {
                    "_BankID": 20,
                    "_MotionExtend": {
                        "ace.user_data.MotionExtend": {
                            "ref_instance_id": 1,
                            "path": extend_path,
                        }
                    },
                }
            }
        )
    return [
        {
            "ace.user_data.MotionExtendBank": {
                "_MotionExtendList": extends,
                "_GroupTable": [
                    {
                        "ace.user_data.MotionExtendBank.cGroupBankSetSerialize": {
                            "GroupBankId": group_set_id >> 44,
                            "GroupSet": [
                                {
                                    "ace.user_data.MotionExtendBank.cGroupSetSerialize": {
                                        "GroupId": group_set_id & ((1 << 44) - 1),
                                        "Group": {
                                            "ace.user_data.MotionExtendBank.cGroup": {
                                                "LList": [MOTION_SET],
                                                "RList": [MOTION_SET + 1],
                                            }
                                        },
                                    }
                                }
                            ],
                        }
                    }
                ],
            }
        }
    ]


def _mex(motion_group_set_id: int) -> list[object]:
    return [
        {
            "ace.user_data.MotionExtend": {
                "_DataList": [
                    {
                        "ace.user_data.MotionExtend.cMotionExtend": {
                            "_MotionID": 630,
                            "_MotionGroupSetID": motion_group_set_id,
                        }
                    }
                ]
            }
        }
    ]


def _write_weapons(natives: Path, *, mex_group: int | None = None) -> None:
    for index in range(14):
        scope = f"Wp{index:02d}"
        directory = natives / "STM" / "Motion" / "Player" / "Weapon" / scope
        directory.mkdir(parents=True)
        extend = ""
        if index == 0 and mex_group is not None:
            extend = f"Motion/Player/Weapon/{scope}/wp00_00/wp00_00_mex.user"
            extend_file = natives / "STM" / f"{extend}.3.json"
            extend_file.parent.mkdir(parents=True)
            extend_file.write_text(json.dumps(_mex(mex_group)), encoding="utf-8")
        (directory / f"wp{index:02d}_meb.user.3.json").write_text(
            json.dumps(_meb(extend_path=extend)), encoding="utf-8"
        )


class MotionGroupCatalogTests(unittest.TestCase):
    def test_loads_group_members_per_weapon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            natives = Path(directory)
            _write_weapons(natives, mex_group=GROUP_SET)
            catalog = MotionGroupCatalog.load(natives)

        group = catalog.find("Wp00", GROUP_SET)
        self.assertIsNotNone(group)
        assert group is not None
        self.assertEqual(group.bank_id, 20)
        self.assertEqual(group.group_id, GROUP_ID)
        self.assertEqual(
            [(m.motion_set_id, m.side) for m in group.members],
            [(MOTION_SET, "L"), (MOTION_SET + 1, "R")],
        )
        self.assertEqual(catalog.verified_extends, 1)
        # The bank-less group ID and a group from another weapon never match.
        self.assertIsNone(catalog.find("Wp00", GROUP_ID))
        self.assertIsNone(catalog.find("Wp00", GROUP_SET + 1))

    def test_rejects_changed_packing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            natives = Path(directory)
            # The MotionExtend references the group, but not with motion 630.
            _write_weapons(natives, mex_group=GROUP_SET)
            extend = next(natives.rglob("wp00_00_mex.user.3.json"))
            data = _mex(GROUP_SET)
            data[0]["ace.user_data.MotionExtend"]["_DataList"][0][
                "ace.user_data.MotionExtend.cMotionExtend"
            ]["_MotionID"] = 641
            extend.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                MotionGroupCatalog.load(natives)

    def test_requires_every_weapon_bank(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            natives = Path(directory)
            _write_weapons(natives)
            next(natives.rglob("wp13_meb.user.3.json")).unlink()
            with self.assertRaises(FileNotFoundError):
                MotionGroupCatalog.load(natives)


def _mov_rax(value: int) -> bytes:
    return b"\x48\xb8" + struct.pack("<Q", value)


def _mov_rcx(value: int) -> bytes:
    return b"\x48\xb9" + struct.pack("<Q", value)


STORE_RAX = b"\x48\x89\x86\xa8\x00\x00\x00"  # mov [rsi+0A8h], rax
CMP_RAX_RCX = b"\x48\x39\xc8"  # cmp rax, rcx
RET = b"\xc3"


def _decode(code: bytes) -> list[object]:
    return list(Decoder(64, code, ip=FUNCTION))


class GroupUseTests(unittest.TestCase):
    def test_store_is_a_request(self) -> None:
        instructions = _decode(_mov_rax(GROUP_SET) + STORE_RAX + RET)
        self.assertTrue(_group_value_is_requested(instructions, 0))

    def test_comparison_is_not_a_request(self) -> None:
        instructions = _decode(_mov_rcx(GROUP_SET) + CMP_RAX_RCX + RET)
        self.assertFalse(_group_value_is_requested(instructions, 0))

    def test_follows_jump_to_shared_store(self) -> None:
        # mov rax, imm64; jmp +2; int3; int3; mov [rsi+0A8h], rax; ret
        code = _mov_rax(GROUP_SET) + b"\xeb\x02\xcc\xcc" + STORE_RAX + RET
        self.assertTrue(_group_value_is_requested(_decode(code), 0))

    def test_argument_register_reaches_call(self) -> None:
        # mov rdx, imm64; call rel32
        code = (
            b"\x48\xba" + struct.pack("<Q", GROUP_SET) + b"\xe8\x00\x00\x00\x00" + RET
        )
        self.assertTrue(_group_value_is_requested(_decode(code), 0))


class _Image:
    def __init__(self, code: bytes) -> None:
        self.code = code

    def read_function_bytes(self, address: int, length: int) -> bytes:
        return self.code[:length]


class MotionSetScannerGroupTests(unittest.TestCase):
    def setUp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            natives = Path(directory)
            _write_weapons(natives)
            self.groups = MotionGroupCatalog.load(natives)
        target = MotionTarget(
            scope="Wp00",
            motion_set_id=MOTION_SET,
            bank_id=20,
            motion_id=630,
            motlist_source_path="STM/Motion/Player/Weapon/Wp00/wp00_00/wp00_00.motlist.992",
            motlist_name="wp00_00",
            events=(),
        )
        self.targets = MotionTargetCatalog({("Wp00", MOTION_SET): target}, [])
        self.method = Il2CppMethod(
            "app.Wp00SubAction.cPorterRideAttack", ".ctor", FUNCTION
        )

    def _scan(self, code: bytes, groups: MotionGroupCatalog | None) -> list[object]:
        scanner = MotionSetScanner(
            _Image(code), self.targets, [FUNCTION, FUNCTION + 0x100], 0x100, groups
        )
        return scanner.scan("Wp00", self.method)

    def test_stored_group_resolves_to_member_motion(self) -> None:
        hits = self._scan(_mov_rax(GROUP_SET) + STORE_RAX + RET, self.groups)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].target.motion_set_id, MOTION_SET)
        evidence = dict(hits[0].motion_group)
        self.assertEqual(evidence["groupSetId"], GROUP_SET)
        self.assertEqual(evidence["side"], "L")

    def test_compared_group_is_ignored(self) -> None:
        hits = self._scan(_mov_rcx(GROUP_SET) + CMP_RAX_RCX + RET, self.groups)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
