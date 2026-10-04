"""Bind reviewed request guards only to the matching implementation identity."""

from copy import deepcopy
import unittest

from sdk.enemy_logic_exporter.shared.logic.action_commands import (
    receipt,
    request_details,
)


class ActionCommandTests(unittest.TestCase):
    def test_sync_has_work_and_mask_guard_without_normal_actor_host_guard(self):
        command = "app.btable.EmCommonCommand.cRequestActionSync"
        proof = receipt()["commands"][command]
        detail = request_details(command, receipt()["profile"], proof)
        self.assertEqual(detail["requestImplementation"], "synchronous")
        self.assertEqual(detail["requestGuard"]["kind"], "all")
        self.assertEqual(
            detail["requestGuard"]["items"][1]["item"]["key"],
            "btable_request_action_mask",
        )
        self.assertNotIn("actorRequestGuard", detail)

    def test_normal_actor_guard_preserves_absent_invalid_and_self_host_cases(self):
        command = "app.btable.EmCommonCommand.cRequestAction"
        detail = request_details(
            command, receipt()["profile"], receipt()["commands"][command]
        )
        guard = detail["actorRequestGuard"]
        self.assertEqual(guard["kind"], "any")
        self.assertEqual(guard["items"][0]["kind"], "not")
        self.assertEqual(guard["items"][1]["right"]["value"], -1)
        self.assertEqual(
            guard["items"][2]["right"]["key"], "request_actor_self_member_index"
        )

    def test_wrong_implementation_or_version_cannot_use_guard_recipe(self):
        command = "app.btable.EmCommonCommand.cRequestActionSync"
        proof = deepcopy(receipt()["commands"][command])
        proof["nativeSha256"] = "0" * 64
        with self.assertRaises(ValueError):
            request_details(command, receipt()["profile"], proof)
        with self.assertRaises(ValueError):
            request_details(command, {}, receipt()["commands"][command])

    def test_selected_and_desire_recovery_cannot_become_fixed_action_recipes(self):
        for command in ("cRequestSelectedAction", "cRequestActionDesireRecover"):
            self.assertIsNone(
                request_details(
                    "app.btable.EmCommonCommand." + command, receipt()["profile"], {}
                )
            )


if __name__ == "__main__":
    unittest.main()
