"""Check shared callback order, asynchronous requests and native wait guards."""

from copy import deepcopy
import unittest

from sdk.enemy_logic_exporter.shared.logic.combat_entry import (
    build_combat_entries,
    receipt,
)
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.expressions import validate_expression
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry
from sdk.enemy_logic_exporter.shared.config import SUPPORTED_PROFILE


class CombatEntryTests(unittest.TestCase):
    def setUp(self):
        self.model = dict(
            profile=deepcopy(SUPPORTED_PROFILE),
            enemyId="EM0002_00_0",
            entry="combat-root",
            tables=[dict(tableGuid="combat-root"), dict(tableGuid="sign-root")],
            resourceEntries={
                "combat-resource": dict(
                    tableGuid="combat-root",
                    status="native_dispatch_table_zero_verified",
                    evidence={"method": "combat-dispatch"},
                ),
                "sign-resource": dict(
                    tableGuid="sign-root",
                    status="native_dispatch_table_zero_verified",
                    evidence={"method": "sign-dispatch"},
                ),
            },
        )
        self.monster = dict(
            enemyId="EM0002_00_0",
            slots={"COMBAT": "combat-resource", "STATE_SIGN": "sign-resource"},
        )
        self.result = build_combat_entries(self.model, self.monster)
        self.tables = {
            t["tableGuid"]: {n["id"]: n for n in t["nodes"]}
            for t in self.result["tables"]
        }

    def truth(self, table, node, context):
        return evaluate_expression(
            self.tables[table][node]["expression"], RuleRegistry.load(), context
        ).truth

    def test_source_identity_and_monster_dispatch_are_required(self):
        bad = deepcopy(self.model)
        bad["profile"]["gameVersion"] = "changed"
        with self.assertRaises(ValueError):
            build_combat_entries(bad, self.monster)
        bad = deepcopy(self.model)
        bad["resourceEntries"]["combat-resource"]["status"] = "metadata_candidate"
        with self.assertRaises(ValueError):
            build_combat_entries(bad, self.monster)
        bad = deepcopy(self.model)
        bad["resourceEntries"]["combat-resource"]["tableGuid"] = "another-monster"
        with self.assertRaises(ValueError):
            build_combat_entries(bad, self.monster)

    def test_begin_uses_both_done_flags_and_real_sign_presence(self):
        base = {
            "combat:done_combat_begin": False,
            "combat:done_combat_em_begin": False,
            "combat:state_sign_exists": True,
        }
        self.assertTrue(self.truth("combat-change-begin", "begin", base))
        for key in ("combat:done_combat_begin", "combat:done_combat_em_begin"):
            self.assertFalse(
                self.truth("combat-change-begin", "begin", dict(base, **{key: True}))
            )
        self.assertFalse(
            self.truth(
                "combat-change-begin",
                "begin",
                dict(base, **{"combat:state_sign_exists": False}),
            )
        )
        self.assertIsNone(self.truth("combat-change-begin", "begin", {}))

    def test_return_interrupt_calls_begin_choice_and_preserves_manager_guard(self):
        nodes = self.tables["combat-return-interrupt"]
        self.assertFalse(
            self.truth(
                "combat-return-interrupt",
                "manager",
                {"combat:controller_exists": False},
            )
        )
        self.assertEqual(nodes["choose"]["targetTable"], "combat-change-begin")
        self.assertNotIn("dispatchTarget", nodes["choose"])

    def test_request_is_queued_and_already_current_resume_is_preserved(self):
        node = self.tables["combat-request-combat-direct"]["queue"]
        self.assertEqual(node["kind"], "mutation")
        self.assertEqual(node["effect"], "request_btable")
        self.assertEqual(node["dispatchTarget"], "combat-root")
        self.assertEqual(node["requestedSlotId"], 1)
        self.assertEqual(node["waitUntilActionEnd"]["status"], "partial")
        self.assertTrue(
            self.truth(
                "combat-request-combat-direct",
                "same_main",
                {"combat:scheduler_current_main_slot": 1},
            )
        )
        self.assertEqual(
            self.tables["combat-request-combat-direct"]["same_main"]["true"], "end"
        )

    def test_root_checks_saved_table_pc_and_command(self):
        prefix = "scheduler:main:"
        context = {
            prefix + "operator_exists": True,
            prefix + "manager_export": True,
            prefix + "saved_table": 7,
            prefix + "export_root_index": 7,
            prefix + "saved_pc": 0,
            prefix + "saved_command": 0,
        }
        self.assertTrue(self.truth("combat-scheduler-main", "root", context))
        self.assertFalse(
            self.truth(
                "combat-scheduler-main",
                "root",
                dict(context, **{prefix + "saved_pc": 1}),
            )
        )
        self.assertFalse(
            self.truth(
                "combat-scheduler-main",
                "root",
                dict(context, **{prefix + "saved_command": 1}),
            )
        )
        self.assertFalse(
            self.truth(
                "combat-scheduler-main",
                "root",
                dict(context, **{prefix + "saved_table": 8}),
            )
        )

    def test_callbacks_and_jump_resume_do_not_restart_root_unconditionally(self):
        update = self.tables["combat-scheduler-update"]
        self.assertEqual(update["jump_update"]["targetTable"], "combat-scheduler-jump")
        self.assertEqual(update["jump_active"]["true"], "end")
        self.assertEqual(update["jump_active"]["false"], "main_update")
        self.assertFalse(update["restore"]["freshRoot"])
        for node in self.tables["combat-scheduler-main"].values():
            if node.get("effect") == "emit_btable_callback":
                self.assertNotIn("dispatchTarget", node)

    def test_every_expression_and_connection_is_valid_and_review_stays_partial(self):
        identities = set(self.tables) | {"combat-root", "sign-root"}
        for nodes in self.tables.values():
            for node in nodes.values():
                for role in ("true", "false", "next", "resume"):
                    if role in node:
                        self.assertIn(node[role], nodes)
                if node["kind"] == "condition":
                    validate_expression(node["expression"])
                if node["kind"] == "call":
                    self.assertIn(node["targetTable"], identities)
                if node["kind"] == "return":
                    self.assertIsNone(node["value"])
                    self.assertEqual(node["returnType"], "void")
        self.assertTrue(
            all(e["status"] == "partial" for e in self.result["entryPoints"])
        )
        self.assertFalse(self.result["combatScheduler"]["semanticReviewComplete"])
        self.assertFalse(receipt()["semanticReviewComplete"])


if __name__ == "__main__":
    unittest.main()
