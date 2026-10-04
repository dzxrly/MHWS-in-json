"""Keep native successor graphs exact and avoid ambiguous action annotations."""

import unittest
from sdk.enemy_logic_exporter.native_viewer import compact_flow


class NativeViewerTests(unittest.TestCase):
    def fixture(self):
        row = dict(
            type="fixture",
            method="table_fixture",
            address="0x1000",
            end="0x1010",
            nativeSha256="f" * 64,
            addressAliases=[],
        )
        data = dict(
            code="fixture",
            controlFlow=dict(
                blocks=[
                    dict(
                        id="0",
                        start="0x1000",
                        end="0x1007",
                        successors=["1"],
                        operations=[],
                    ),
                    dict(
                        id="1",
                        start="0x1008",
                        end="0x100f",
                        successors=[],
                        operations=[dict(address="0x100f", opcode="RETURN", inputs=[])],
                    ),
                ]
            ),
        )
        return row, data

    def test_actual_successors_are_retained_without_return_edges(self):
        row, data = self.fixture()
        flow = compact_flow(data, row, [], {}, {})
        self.assertEqual([b["successors"] for b in flow["blocks"]], [["1"], []])
        self.assertEqual(flow["entryBlock"], "0")
        self.assertEqual(flow["status"], "unreviewed_native_control_flow")

    def test_ambiguous_instruction_range_does_not_place_action_in_a_guessed_block(self):
        row, data = self.fixture()
        data["controlFlow"]["blocks"][1]["start"] = "0x1004"
        event = dict(address="0x1005", actionRef="a", argumentIndex=1, commandIndex=2)
        flow = compact_flow(data, row, [event], {"a": {"actionGuid": "guid"}}, {})
        self.assertEqual(flow["unplacedActionSites"], ["0x1005"])
        self.assertFalse(any(b["actions"] for b in flow["blocks"]))

    def test_block_outside_method_range_keeps_explicit_boundary(self):
        row, data = self.fixture()
        data["controlFlow"]["blocks"][1]["start"] = "0x2000"
        self.assertEqual(
            compact_flow(data, row, [], {}, {})["rangeBoundaryWarnings"], ["1"]
        )

    def test_successor_to_a_missing_block_is_rejected(self):
        row, data = self.fixture()
        data["controlFlow"]["blocks"][0]["successors"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "后继"):
            compact_flow(data, row, [], {}, {})
