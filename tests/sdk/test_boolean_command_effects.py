"""A reviewed Boolean command applies its field write only on its true path."""

import hashlib
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.monster import em0160_00_0 as arkveld
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.machine import Machine


class BooleanCommandEffectTests(unittest.TestCase):
    def test_local_history_policy_preserves_numeric_end_of_table_guid(self):
        row = dict(
            type=arkveld.LOCAL_HISTORY_EXPORT,
            method=arkveld.LOCAL_HISTORY_TABLE + "1089978",
        )
        self.assertEqual(arkveld.table_history_policy(row), dict(local=True))
        self.assertIsNone(
            arkveld.table_history_policy(dict(row, method=row["method"] + "_extra"))
        )
        self.assertIsNone(
            arkveld.table_history_policy(dict(row, type="unrelated.Export"))
        )

    def sources(self, *, changed_bytes=False, changed_layout=False):
        proof = arkveld._absorbed_action_proof()
        row = proof["command"]
        records = {
            row["type"]: dict(
                methods={
                    row["method"]: dict(
                        function=row["address"][2:],
                        returns=dict(type="System.Boolean"),
                        params=[dict(type="ace.btable.cCommandWork")],
                    )
                }
            ),
            proof["stateEnum"]["type"]: dict(
                fields={
                    name: dict(default=value)
                    for name, value in proof["stateEnum"].items()
                    if name != "type"
                }
            ),
        }
        memory = {int(row["address"], 16): bytes.fromhex(row["nativeBytes"])}
        for index, symbol in enumerate(proof["classSymbols"], 1):
            records.setdefault(symbol["type"], {})["address"] = hex(index)[2:]
            memory[int(symbol["slot"], 16)] = struct.pack("<Q", index)
        for owner, fields in proof["layouts"].items():
            records.setdefault(owner, {})["fields"] = {
                name: dict(type=field["type"], offset_from_base=field["offset"])
                for name, field in fields.items()
            }
        if changed_bytes:
            memory[int(row["address"], 16)] = (
                b"\x90" + memory[int(row["address"], 16)][1:]
            )
        if changed_layout:
            records["app.cEm0160Extend"]["fields"]["_AbsorbCocoonState"][
                "offset_from_base"
            ] = "0xac"
        metadata = SimpleNamespace(
            get=lambda name: records.get(name),
            fields=lambda name: records.get(name, {}).get("fields", {}),
            enum=lambda name: (
                name,
                {
                    key: value["default"]
                    for key, value in records[name]["fields"].items()
                },
            ),
        )
        return (
            row,
            metadata,
            SimpleNamespace(read=lambda address, size: memory.get(address, b"")[:size]),
        )

    def test_wait_action_is_checked_before_the_state_is_advanced(self):
        row, metadata, pe = self.sources()
        recipe = arkveld.recover_boolean_command_effect(row, metadata, pe)
        condition = recipe["condition"]["expression"]
        context = dict(enemy_command_work_valid=True, self_extend_valid=True)
        context[arkveld.ABSORBED_STATE_KEY] = 4
        self.assertTrue(evaluate_expression(condition, None, context).truth)
        context.update(recipe["onTrue"])
        self.assertEqual(context[arkveld.ABSORBED_STATE_KEY], 5)
        self.assertFalse(evaluate_expression(condition, None, context).truth)
        context["self_extend_valid"] = False
        context[arkveld.ABSORBED_STATE_KEY] = 4
        self.assertFalse(evaluate_expression(condition, None, context).truth)
        context.pop("self_extend_valid")
        self.assertIsNone(evaluate_expression(condition, None, context).truth)

    def test_native_branch_and_true_only_mutation_remain_separate(self):
        row, metadata, pe = self.sources()
        recipe = arkveld.recover_boolean_command_effect(row, metadata, pe)
        base = 0x14606CE00
        target = int(row["address"], 16)
        native = (
            b"\xe8"
            + struct.pack("<i", target - base - 5)
            + bytes.fromhex("84c07406b801000000c331c0c3")
        )
        machine = Machine(
            dict(
                type="fixture",
                method="table",
                address=hex(base),
                end=hex(base + len(native)),
                nativeSha256=hashlib.sha256(native).hexdigest(),
            ),
            native,
            pe,
            {},
            [{"_ArgumentType": ""}],
            {},
            {},
        )
        machine.metadata = metadata
        machine.reviewed_effects = True
        machine.boolean_commands[arkveld.ABSORBED_ACTION_COMMAND] = recipe
        machine.command_evidence[arkveld.ABSORBED_ACTION_COMMAND] = row
        bound = dict(
            commandType=arkveld.ABSORBED_ACTION_COMMAND,
            commandIndex=0,
            argumentIndex=None,
            argumentType="",
            argument={},
        )
        with patch.object(machine, "bind", return_value=bound):
            result = machine.build()
        nodes = {node["id"]: node for node in result["nodes"]}
        check = nodes[result["entry"]]
        effect = nodes[check["true"]]
        self.assertEqual(effect["stateUpdates"], {arkveld.ABSORBED_STATE_KEY: 5})
        self.assertTrue(nodes[effect["next"]]["value"])
        self.assertEqual(nodes[check["false"]]["kind"], "return")
        self.assertFalse(nodes[check["false"]]["value"])

    def test_recipe_rejects_changed_bytes_or_field_layout(self):
        for changes in (dict(changed_bytes=True), dict(changed_layout=True)):
            row, metadata, pe = self.sources(**changes)
            with self.assertRaises(ValueError):
                arkveld.recover_boolean_command_effect(row, metadata, pe)

    def test_unrelated_command_does_not_receive_the_state_transition(self):
        row, metadata, pe = self.sources()
        self.assertIsNone(
            arkveld.recover_boolean_command_effect(
                dict(row, type="unrelated"), metadata, pe
            )
        )
