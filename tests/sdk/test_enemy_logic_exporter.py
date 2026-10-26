"""Preserve graph topology across compound layout."""

from copy import deepcopy
import unittest

from src.processed_data.enemy_battle_logic.diagram import combined_diagram, node_id


class DiagramTests(unittest.TestCase):
    def graph(self):
        evidence = {"method": "fixture"}
        return dict(
            enemyId="fixture",
            resource="fixture_BTable_Combat.json",
            entry="a",
            scope="fixture",
            coverage={"localTables": 2, "nodes": 4},
            tables=[
                dict(
                    tableGuid="a",
                    tableIndex=1,
                    entry="0",
                    evidence=evidence,
                    nodes=[
                        dict(id="0", kind="call", targetTable="b", resume="1"),
                        dict(id="1", kind="return", value=False),
                    ],
                ),
                dict(
                    tableGuid="b",
                    tableIndex=2,
                    entry="0",
                    evidence=evidence,
                    nodes=[
                        dict(id="0", kind="unknown", reason="not recovered"),
                        dict(id="1", kind="return", value=False),
                    ],
                ),
            ],
        )

    def test_shared_call_and_continuation_are_separate_edges(self):
        graph = self.graph()
        snapshot = deepcopy(graph)
        diagram = combined_diagram(graph)
        self.assertEqual(graph, snapshot)
        nodes = [
            node["id"]
            for group in diagram["layout"]["children"]
            for node in group["children"]
        ]
        self.assertEqual(len(nodes), len(set(nodes)))
        edges = diagram["layout"]["edges"]
        call = next(edge for edge in edges if edge["role"] == "call")
        resume = next(edge for edge in edges if edge["role"] == "resume")
        self.assertEqual(call["targets"], [node_id("b", "0")])
        self.assertEqual(resume["targets"], [node_id("a", "1")])
        self.assertTrue(resume["continuation"])
        self.assertFalse(any(edge["sources"] == [node_id("b", "1")] for edge in edges))


if __name__ == "__main__":
    unittest.main()
