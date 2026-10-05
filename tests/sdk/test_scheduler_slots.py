"""Check slot-request recovery and per-monster slot binding without game files."""

from importlib.util import find_spec
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.config import SUPPORTED_PROFILE


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class SlotArgumentTests(unittest.TestCase):
    def decode(self, hexadecimal):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64

        decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        decoder.detail = True
        return list(decoder.disasm(bytes.fromhex(hexadecimal), 0x1000))

    def test_immediate_slot_before_the_request_is_accepted(self):
        from sdk.enemy_logic_exporter.shared.logic.scheduler_slots import (
            _immediate_argument,
        )

        # mov r8d, 0x17; mov rcx, rsi; call 0x2000
        code = self.decode("41b8170000004889f1e8f20f0000")
        self.assertEqual(_immediate_argument(code, 2), (0x17, "immediate"))

    def test_register_or_crossed_call_stays_a_boundary(self):
        from sdk.enemy_logic_exporter.shared.logic.scheduler_slots import (
            _immediate_argument,
        )

        # mov r8d, ebx; call 0x2000
        value, reason = _immediate_argument(self.decode("4189d8e8f80f0000"), 1)
        self.assertIsNone(value)
        self.assertTrue(reason.startswith("dynamic"))
        # mov r8d, 1; call 0x2000; call 0x3000
        code = self.decode("41b801000000e8f50f0000e8f01f0000")
        self.assertEqual(_immediate_argument(code, 2), (None, "crossed_call"))


class SlotBindingTests(unittest.TestCase):
    def test_declared_slots_receive_their_requesting_states(self):
        from sdk.enemy_logic_exporter.shared.logic import scheduler_slots

        evidence = dict(
            profile=SUPPORTED_PROFILE,
            requests=[
                dict(
                    owner="app.cEmAIInterruptDamage",
                    method="onEnter577638",
                    site="0x1",
                    mode="change",
                    slot="DAMAGE",
                )
            ],
            uniqueSlots=dict(
                requester="app.cEmAIInterruptUnique.requestUniqueBTable577693",
                contextField="cEnemyContext+0x35c",
                initializerSite="0x2",
                byIndex=["NONE", "UNIQUE_00", "UNIQUE_01"],
            ),
        )
        model = dict(
            profile=SUPPORTED_PROFILE,
            combatScheduler=dict(
                slotBindings=dict(
                    DAMAGE=dict(resource="damage", dispatchTarget="t1"),
                    UNIQUE_00=dict(resource="unique", dispatchTarget="t2"),
                    LIFE=dict(resource="life"),
                )
            ),
        )
        with patch.object(scheduler_slots, "receipt", return_value=evidence):
            slots = {s["slot"]: s for s in scheduler_slots.scheduler_slots(model)}
        self.assertEqual(slots["DAMAGE"]["requestedBy"][0]["owner"], "app.cEmAIInterruptDamage")
        self.assertEqual(slots["DAMAGE"]["group"], "与玩家战斗")
        self.assertEqual(slots["UNIQUE_00"]["requestedBy"][0]["uniqueIndex"], 1)
        self.assertEqual(slots["LIFE"]["requestedBy"], [])
        self.assertIsNone(slots["LIFE"]["dispatchTarget"])
        with self.assertRaisesRegex(ValueError, "来源版本"):
            with patch.object(scheduler_slots, "receipt", return_value=dict(evidence, profile={})):
                scheduler_slots.scheduler_slots(model)
