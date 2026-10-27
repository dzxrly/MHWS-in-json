import unittest
import struct
from types import SimpleNamespace
from sdk.enemy_logic_exporter.monster.em0166_00_0 import recover_phase_apply
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry


class Em166PhaseTests(unittest.TestCase):
    def phase_fixture(self, caller_start, helper_start, *, wrong_tail=False):
        caller = (
            b"\x90" * 0x23
            + b"\x0f\x84"
            + struct.pack(
                "<i", helper_start + (1 if wrong_tail else 0) - (caller_start + 0x29)
            )
            + b"\xc3"
        )
        helper = b"\x90" * 0x24 + bytes.fromhex("8b825402000089822c020000") + b"\xc3"
        command_type = "app.btable.Em0166_00BTableCommand.cApplyRequestBattlePhase"
        extend_type = "app.cEm0166_00Extend"
        field_type = "app.Em0166_00_Def.BATTLE_PHASE"
        records = {
            command_type: {"onExecute1": {"function": hex(caller_start)}},
            extend_type: {"applyRequestBattlePhase2": {"function": hex(helper_start)}},
        }
        fields = {
            "_CurrentPhase": {"type": field_type, "offset_from_base": "0x22c"},
            "_RequestPhase": {"type": field_type, "offset_from_base": "0x254"},
        }
        ranges = {caller_start: caller, helper_start: helper}

        def read(address, size):
            for start, raw in ranges.items():
                if start <= address and address + size <= start + len(raw):
                    return raw[address - start : address - start + size]
            return b""

        return (
            dict(
                type=command_type,
                method="onExecute1",
                address=hex(caller_start),
                end=hex(caller_start + len(caller)),
            ),
            SimpleNamespace(
                get=lambda owner: {"methods": records.get(owner, {})},
                fields=lambda _: fields,
            ),
            SimpleNamespace(
                read=read, end=lambda address: address + len(ranges[address])
            ),
        )

    def test_phase_sites_follow_both_current_metadata_entries(self):
        for caller_start, helper_start in ((0x1000, 0x2000), (0x7000, 0x5000)):
            with self.subTest(caller=caller_start, helper=helper_start):
                effect = recover_phase_apply(
                    *self.phase_fixture(caller_start, helper_start)
                )[0]
                self.assertEqual(effect["callerBranchSite"], hex(caller_start + 0x23))
                self.assertEqual(effect["instructionSite"], hex(helper_start + 0x2A))
                self.assertEqual(effect["destination"]["field"], "_CurrentPhase")
                self.assertEqual(effect["value"]["field"], "_RequestPhase")
                self.assertIn("仍未全部恢复", effect["guard"])

    def test_phase_wrong_tail_and_changed_copy_remain_errors(self):
        with self.assertRaisesRegex(ValueError, "真实跳转"):
            recover_phase_apply(*self.phase_fixture(0x1000, 0x2000, wrong_tail=True))
        row, metadata, pe = self.phase_fixture(0x1000, 0x2000)
        read = pe.read
        pe.read = lambda address, size: (
            b"\x00" * size if address == 0x2024 else read(address, size)
        )
        with self.assertRaisesRegex(ValueError, "字段复制"):
            recover_phase_apply(row, metadata, pe)

    def test_phase_check_reads_applied_phase_and_requires_valid_context(self):
        registry = RuleRegistry.load()
        bound = registry.bind(
            "app.btable.Em0166_00BTableCommand.cCheckBattlePhase",
            "app.btable.Em0166_00BTableCommand.cCheckBattlePhaseArg",
            {"_EditArg": "[1] PHASE_2"},
        )
        state = {"valid": True, "_CurrentPhase": 0, "_RequestPhase": 1}
        context = {
            "valid_command_work": True,
            "objects": {"app.cEm0166_00Extend": state},
        }
        self.assertIs(registry.evaluate(bound, context).truth, False)
        state["_CurrentPhase"] = 1
        self.assertIs(registry.evaluate(bound, context).truth, True)
        del state["valid"]
        self.assertIsNone(registry.evaluate(bound, context).truth)

    def test_other_monsters_cannot_use_this_recipe(self):
        self.assertEqual(
            recover_phase_apply(
                {"type": "app.btable.Em0164_50BTableCommand.cApplyRequestBattlePhase"},
                None,
                None,
            ),
            [],
        )
