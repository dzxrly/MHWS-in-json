"""The exporter must expose resource gaps instead of inventing execution."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from config import BASE_DIR, SUPPORT_FILES
from src.processed_data.enemy_action_logic.document import validate_document
from src.processed_data.enemy_action_logic.evidence import apply_evidence, load_evidence
from src.processed_data.enemy_action_logic.exporter import (
    OUTPUT_NAME,
    export_enemy_action_logic,
)
from src.processed_data.enemy_action_logic.graph import validate_graph
from src.processed_data.enemy_action_logic.layout import place
from src.processed_data.enemy_action_logic.phases import (
    PHASE_COMPATIBILITY,
    resolve_phases,
)
from src.processed_data.enemy_action_logic.player_view import (
    player_graph,
    resource_actions,
)
from src.processed_data.enemy_action_logic.render import html_document, svg
from src.processed_data.enemy_action_logic.source import (
    ResourceReader,
    discover_enemies,
    load_resources,
    reference_path,
)
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextDB

NAME = "00000000-0000-0000-0000-000000000001"
ACTION = "00000000-0000-0000-0000-000000000002"
BRANCH = "00000000-0000-0000-0000-000000000003"
BRANCH_TWO = "00000000-0000-0000-0000-000000000004"
ROOT = "STM/GameDesign/Enemy/Em0001/00/"


def _write(root, relative, kind, body):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{kind: body}], ensure_ascii=False), encoding="utf-8")
    return path


def _ref(relative):
    return {
        "Resource": {
            "path": relative.removeprefix("STM/").removesuffix(".3.json"),
            "ref_instance_id": 1,
        }
    }


def _fixture(root):
    ids = ["EM0001_00_0", "EM0001_00_1", "EM0165_00_0", "EM1000_00_0"]
    _write(
        root,
        SUPPORT_FILES["enemy"],
        "app.user_data.EnemyData",
        {
            "_Values": [
                {
                    "app.user_data.EnemyData.cData": {
                        "_Index": index,
                        "_enemyId": f"[{index}] {enemy}",
                        "_EnemyName": NAME,
                    }
                }
                for index, enemy in enumerate(ids)
            ]
        },
    )
    table = ROOT + "BTable/Em0001_00_Btable_Combat.user.3.json"
    main = ROOT + "Action/Em0001_00_ActionID.user.3.json"
    sub = ROOT + "Action/Em0001_00_SubActionID.user.3.json"
    bank = ROOT + "BTable/Em0001_00_BTableOrderBank.user.3.json"
    _write(
        root,
        ROOT + "Data/Em0001_00_ParamPack.user.3.json",
        "Pack",
        {
            "_BTableList": _ref(ROOT + "BTable/Em0001_00_BTableList.user.3.json"),
            "_Missing": _ref(ROOT + "Data/Absent.user.3.json"),
        },
    )
    _write(
        root,
        ROOT + "BTable/Em0001_00_BTableList.user.3.json",
        "List",
        {"_Table_COMBAT": _ref(table.replace("Btable", "BTABLE"))},
    )
    _write(
        root,
        ROOT + "Data/Em0001_00_CharacterParamPack.user.3.json",
        "Character",
        {"_ActionDataSetHolder": [_ref(main), _ref(sub)]},
    )
    phases = [
        {"Phase": {"_BattlePhase": "[0] PHASE_1", "_VitalRate": 70}},
        {"Phase": {"_BattlePhase": "[1] PHASE_2", "_VitalRate": 0}},
    ]
    _write(
        root,
        ROOT + "Data/Em0001_00_Param_Unique.user.3.json",
        "Unique",
        {
            "_GenusInfo": {
                "Info": {"_PhaseList": phases, "_PhaseList_HL": deepcopy(phases)}
            }
        },
    )
    for path, name in ((main, "cAttackMain"), (sub, "cAttackSub")):
        _write(
            root,
            path,
            "ace.user_data.ActionID",
            {
                "_ActionIDArray": {
                    "Array": {
                        "_DataArray": [
                            {"ID": {"_Class": name, "_InstanceGuid": ACTION}}
                        ]
                    }
                }
            },
        )
    _write(
        root,
        bank,
        "Bank",
        {
            "_CommandArgumentSettingList": [
                {
                    "Setting": {
                        "_AssetDataList": [
                            {"Asset": {"_Asset": _ref(main)}},
                            {"Asset": {"_Asset": _ref(sub)}},
                        ]
                    }
                }
            ]
        },
    )
    arguments = []
    for index in (0, 1):
        arguments.append(
            {
                "app.btable.cSelectActionArg": {
                    "_EditAssetIndex": {"Int": index},
                    "_EditActionGuid": {"Guid": ACTION},
                    "_EditBranchedParamGuid": {"Guid": BRANCH},
                }
            }
        )
    arguments.insert(1, {"app.btable.cCheckDistanceArg": {"_Distance": {"Float": 9}}})
    _write(
        root,
        table,
        "ace.btable.user_data.BTable",
        {
            "_Tables": {"Array": {"_DataArray": []}},
            "_ExportBTableType": "app.Em0001_Combat_Export",
            "_OrderBank": _ref(bank),
            "_CommandArgArray": arguments,
            "_ImportBTableList": [],
        },
    )
    return table


def _native_graph(phase_id):
    graph = {
        "id": phase_id,
        "title": phase_id,
        "entry": "start",
        "nodes": [
            {"id": "start", "label": "相距 x 米", "kind": "end", "evidence": "context"},
            {
                "id": "check",
                "label": "d < 9？",
                "kind": "decision",
                "evidence": "native",
                "detail": {"address": "0x140000001"},
            },
            {
                "id": "action",
                "label": "请求攻击",
                "kind": "action",
                "evidence": "native",
                "detail": {"actionType": "cRocketPunch"},
            },
            {
                "id": "return",
                "label": "等待下一次决策",
                "kind": "end",
                "evidence": "unresolved",
            },
        ],
        "edges": [
            {"from": "start", "to": "check", "evidence": "context"},
            {"from": "check", "to": "action", "label": "是", "evidence": "native"},
            {"from": "check", "to": "return", "label": "否", "evidence": "native"},
            {"from": "action", "to": "return", "evidence": "unresolved"},
            {"from": "return", "to": "start", "evidence": "unresolved", "back": True},
        ],
        "playerActions": [{"type": "cRocketPunch", "evidence": "native"}],
        "decisionCases": [
            {
                "distanceMin": 0,
                "distanceMax": 9,
                "distanceBasis": "command",
                "state": {"hostility": True},
                "actions": [{"type": "cRocketPunch"}],
                "furtherFiltersUnresolved": True,
            }
        ],
    }
    return graph


class EnemyActionLogicTests(unittest.TestCase):
    def setUp(self):
        work = BASE_DIR / ".agents" / "enemy-action-logic-tests"
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.root = Path(self.temp.name)
        self.table = _fixture(self.root)
        self.repository = SourceRepository(self.root)
        self.text = TextDB({NAME: "测试怪物"}, {})
        self.reader = ResourceReader(self.root)
        self.enemies = discover_enemies(self.repository, self.text)
        self.catalog = load_resources(self.reader, self.enemies[0])

    def tearDown(self):
        self.temp.cleanup()

    def evidence(self):
        return {
            "sourceFiles": self.catalog.sources.copy(),
            "nativeSnapshot": {"exeSha256": "a" * 64},
            "graphs": [_native_graph(phase["id"]) for phase in self.catalog.phases],
        }

    def test_full_ids_scope_shared_assets_and_training_are_preserved(self):
        self.assertEqual(
            [enemy.enemy_id for enemy in self.enemies],
            ["EM0001_00_0", "EM0001_00_1", "EM0165_00_0"],
        )
        self.assertEqual(self.enemies[-1].category, "training")
        shared = load_resources(self.reader, self.enemies[1])
        self.assertEqual(shared.sources, self.catalog.sources)
        self.assertEqual(
            [phase["id"] for phase in self.catalog.phases],
            ["[0] PHASE_1", "[1] PHASE_2"],
        )
        self.assertEqual(len(self.catalog.phases[0]["configurations"]), 2)

    def test_asset_index_disambiguates_guids_and_keeps_branch(self):
        selections = self.catalog.tables[0]["actionArguments"]
        self.assertEqual(
            [action["class"] for action in selections], ["cAttackMain", "cAttackSub"]
        )
        self.assertEqual(
            [action["branchGuid"] for action in selections], [BRANCH, BRANCH]
        )
        self.assertTrue(
            any(
                item["code"] == "missing_reference" for item in self.catalog.diagnostics
            )
        )

    def test_source_graph_does_not_turn_array_order_into_action_order(self):
        graphs = [
            player_graph(self.catalog, phase_id=phase["id"])
            for phase in self.catalog.phases
        ]
        self.assertEqual(len(graphs), 2)
        for graph in graphs:
            validate_graph(graph)
            kinds = {node["id"]: node["kind"] for node in graph["nodes"]}
            self.assertFalse(
                any(
                    kinds[edge["from"]] == kinds[edge["to"]] == "action"
                    for edge in graph["edges"]
                )
            )
            self.assertTrue(
                all(edge["evidence"] == "unresolved" for edge in graph["edges"])
            )
            self.assertFalse(graph["coverage"]["complete"])
            labels = "\n".join(node["label"] for node in graph["nodes"])
            self.assertIn("cAttackMain", labels)
            self.assertIn("cAttackSub", labels)
            self.assertNotIn(ACTION, labels)
            self.assertNotIn("BTable", labels)

    def test_missing_phase_does_not_claim_one_actual_phase(self):
        graph = player_graph(load_resources(self.reader, self.enemies[-1]))
        self.assertEqual(graph["id"], "unresolved")
        self.assertIn("未解析", graph["title"])

    def phase_tables(self, prefix, values=None):
        rule = PHASE_COMPATIBILITY[prefix]
        return [
            {
                "source": "STM/PhaseFixture.user.3.json",
                "guardArguments": [
                    {"index": index, "type": rule.command, "raw": {rule.field: value}}
                    for index, value in enumerate(values or dict(rule.phases))
                ],
            }
        ]

    def test_special_phase_adapter_preserves_custom_ids_and_source_references(self):
        for prefix in ("EM0078_00", "EM0162_00"):
            phases = resolve_phases(prefix, [], self.phase_tables(prefix))
            self.assertEqual(
                [p["id"] for p in phases],
                list(dict(PHASE_COMPATIBILITY[prefix].phases)),
            )
            self.assertTrue(all(p["basis"] == "fixed_em_compatibility" for p in phases))
            self.assertTrue(
                all(
                    p["guardReferences"][0]["source"] == "STM/PhaseFixture.user.3.json"
                    for p in phases
                )
            )
        self.assertEqual(
            len(resolve_phases("EM0078_00", [], self.phase_tables("EM0078_00"))), 3
        )
        self.assertEqual(
            len(resolve_phases("EM0162_00", [], self.phase_tables("EM0162_00"))), 4
        )

    def test_phase_adapter_does_not_infer_from_em_or_generic_phase_names_alone(self):
        self.assertEqual(resolve_phases("EM0078_00", [], []), [])
        self.assertEqual(
            resolve_phases("EM0160_00", [], self.phase_tables("EM0078_00")), []
        )
        tables = self.phase_tables("EM0078_00")
        tables[0]["guardArguments"][0]["type"] = "app.Music.cCheckPhaseArg"
        with self.assertRaisesRegex(ValueError, "Incomplete combat phase"):
            resolve_phases("EM0078_00", [], tables)

    def test_phase_adapter_rejects_new_values_and_conflicting_active_lists(self):
        tables = self.phase_tables("EM0166_00")
        tables[0]["guardArguments"].append(
            {
                "index": 4,
                "type": PHASE_COMPATIBILITY["EM0166_00"].command,
                "raw": {"_EditArg": "[4] PHASE_5"},
            }
        )
        with self.assertRaisesRegex(ValueError, "Unexpected combat phase"):
            resolve_phases("EM0166_00", [], tables)
        with self.assertRaisesRegex(ValueError, "conflicts with EM compatibility"):
            resolve_phases(
                "EM0166_00",
                [{"id": "[0] PHASE_1", "configurations": []}],
                self.phase_tables("EM0166_00"),
            )

    def test_active_phase_lists_keep_all_configurations_without_unused_enum_values(
        self,
    ):
        explicit = [
            {
                "id": phase_id,
                "configurations": [{"field": "_PhaseList"}, {"field": "_PhaseList_HL"}],
            }
            for phase_id, _ in PHASE_COMPATIBILITY["EM0166_00"].phases
        ]
        phases = resolve_phases("EM0166_00", explicit, self.phase_tables("EM0166_00"))
        self.assertEqual(len(phases), 4)
        self.assertTrue(all(len(p["configurations"]) == 2 for p in phases))
        self.assertTrue(all(p["basis"] == "resource_phase_list" for p in phases))

    def test_swim_phase_adapter_keeps_regular_combat_and_unchecked_enum_value(self):
        phases = resolve_phases(
            "EM0046_00",
            [],
            self.phase_tables("EM0046_00", ["[1] ELECTRIC_LEVEL_3", "[2] FINISH"]),
        )
        self.assertEqual(len(phases), 4)
        self.assertEqual(phases[0]["id"], "regular_combat")
        self.assertEqual(phases[1]["id"], "[0] ELECTRIC_LEVEL_2")
        self.assertEqual(phases[1]["guardReferences"], [])
        self.assertIn("枚举", phases[1]["note"])
        self.assertTrue(all(p["scope"] == "swim_combat" for p in phases[1:]))
        catalog = deepcopy(self.catalog)
        catalog.phases = phases
        graph = player_graph(catalog, phase_id=phases[1]["id"])
        self.assertIn("电力等级 2", graph["title"])
        self.assertEqual(graph["phaseDefinition"]["scope"], "swim_combat")
        self.assertIn("整场战斗", graph["limitations"][0])

    def test_unrelated_phase_list_without_phase_field_is_not_a_combat_phase(self):
        _write(
            self.root,
            "STM/GameDesign/Enemy/Em0165/00/Data/Em0165_00_Param_Unique.user.3.json",
            "Unique",
            {"_PhaseList": [{"Effect": {"_Timer": 5}}]},
        )
        reader = ResourceReader(self.root)
        catalog = load_resources(reader, self.enemies[-1])
        self.assertEqual([p["id"] for p in catalog.phases], ["unresolved"])

    def test_native_evidence_requires_hashes_and_matching_phases(self):
        evidence = self.evidence()
        graphs, provenance = apply_evidence(self.catalog, self.reader, evidence)
        self.assertEqual(graphs[0]["mode"], "imported_native")
        self.assertEqual(graphs[0]["coverage"]["nativeNodes"], 2)
        self.assertFalse(provenance["inGameVerified"])
        bad = deepcopy(evidence)
        bad["sourceFiles"][self.table] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            apply_evidence(self.catalog, self.reader, bad)
        bad = deepcopy(evidence)
        del bad["sourceFiles"][self.table]
        with self.assertRaisesRegex(ValueError, "source coverage"):
            apply_evidence(self.catalog, self.reader, bad)
        bad = deepcopy(evidence)
        bad["graphs"].pop()
        with self.assertRaisesRegex(ValueError, "combat phases"):
            apply_evidence(self.catalog, self.reader, bad)

    def test_graph_rejects_orphans_dangling_edges_and_dead_paths(self):
        graph = _native_graph("phase")
        bad = deepcopy(graph)
        bad["nodes"].append(
            {
                "id": "orphan",
                "label": "孤立",
                "kind": "unknown",
                "evidence": "unresolved",
            }
        )
        with self.assertRaisesRegex(ValueError, "unreachable"):
            validate_graph(bad)
        bad = deepcopy(graph)
        bad["edges"][0]["to"] = "absent"
        with self.assertRaisesRegex(ValueError, "Dangling"):
            validate_graph(bad)
        bad = deepcopy(graph)
        bad["edges"] = [edge for edge in bad["edges"] if edge["from"] != "action"]
        with self.assertRaisesRegex(ValueError, "no return/exit"):
            validate_graph(bad)

    def test_distance_cases_require_explicit_basis_and_known_action_types(self):
        graph = _native_graph(self.catalog.phases[0]["id"])
        projected = player_graph(self.catalog, graph)
        labels = "\n".join(node["label"] for node in projected["nodes"])
        self.assertIn("d < 9", labels)
        self.assertNotIn("x < 9", labels)
        self.assertEqual(projected["edges"], graph["edges"])
        self.assertEqual(projected["decisionCases"], graph["decisionCases"])
        for field, value in (
            ("distanceBasis", None),
            ("distanceMax", -1),
            ("actions", [{"type": "cAbsent"}]),
        ):
            bad = deepcopy(graph)
            bad["decisionCases"][0][field] = value
            with self.assertRaisesRegex(ValueError, "distance case"):
                player_graph(self.catalog, bad)

    def test_html_is_offline_flowcharts_and_escapes_source_content(self):
        graphs = [
            player_graph(self.catalog, phase_id=phase["id"])
            for phase in self.catalog.phases
        ]
        graphs[0]["nodes"][0]["label"] = "</script><script>alert(1)</script>"
        document = html_document(
            {
                "schemaVersion": 1,
                "format": "mhws_enemy_action_logic",
                "enemies": [
                    {"enemyId": "EM0001_00_0", "name": "<怪物>", "graphs": graphs}
                ],
            }
        )
        self.assertEqual(document.count('<section class="diagram"'), 2)
        self.assertNotIn("<table", document)
        self.assertNotIn("<script src=", document)
        self.assertNotIn("</script><script>alert(1)", document)
        self.assertIn("\\u003c/script", document)
        self.assertIn('class="node"', svg(graphs[0]))
        self.assertEqual(document.count('id="arrow-EM0001_00_0-0"'), 1)
        self.assertEqual(document.count('id="arrow-EM0001_00_0-1"'), 1)
        self.assertEqual(validate_document(document)["enemies"][0]["name"], "<怪物>")

    def test_layout_rejects_outside_geometry(self):
        graph = player_graph(self.catalog)
        graph["layout"] = place(graph)
        place(graph)
        graph["layout"]["nodes"]["start"]["width"] = 1e20
        with self.assertRaisesRegex(ValueError, "layout bounds"):
            place(graph)

    def test_multirow_edges_do_not_imply_action_chains_by_crossing_nodes(self):
        catalog = deepcopy(self.catalog)
        template = catalog.tables[0]["actionArguments"][0]
        catalog.tables[0]["actionArguments"] = [
            {**template, "class": f"cCandidate{index}"} for index in range(20)
        ]
        graph = player_graph(catalog)
        layout = place(graph)
        for edge, shape in zip(graph["edges"], layout["edges"]):
            for first, second in zip(shape["points"], shape["points"][1:]):
                for node_id, bounds in layout["nodes"].items():
                    if node_id in (edge["from"], edge["to"]):
                        continue
                    left, right = bounds["x"] + 1, bounds["x"] + bounds["width"] - 1
                    top, bottom = bounds["y"] + 1, bounds["y"] + bounds["height"] - 1
                    crosses = (
                        first[0] == second[0]
                        and left < first[0] < right
                        and max(first[1], second[1]) > top
                        and min(first[1], second[1]) < bottom
                    ) or (
                        first[1] == second[1]
                        and top < first[1] < bottom
                        and max(first[0], second[0]) > left
                        and min(first[0], second[0]) < right
                    )
                    self.assertFalse(
                        crosses,
                        f"{edge['from']} -> {edge['to']} crosses unrelated {node_id}",
                    )

    def test_single_html_roundtrip_and_pipeline_registration(self):
        path = export_enemy_action_logic(
            self.root / OUTPUT_NAME, self.repository, self.text
        )
        payload = validate_document(path)
        self.assertEqual(len(payload["enemies"]), 3)
        self.assertEqual(sum(len(enemy["graphs"]) for enemy in payload["enemies"]), 5)
        self.assertEqual(path.suffix, ".html")
        self.assertEqual(list(self.root.glob("*.html")), [path])
        self.assertFalse(list(self.root.glob("*.pdf")))
        self.assertFalse(list(self.root.glob("*.zip")))
        from src.processed_data.exporter import OUTPUT_NAMES
        from src.pipeline.validation import validate_outputs

        self.assertIn(OUTPUT_NAME, OUTPUT_NAMES)
        stage = self.root / "stage"
        stage.mkdir()
        (stage / OUTPUT_NAME).write_bytes(path.read_bytes())
        self.assertEqual(
            validate_outputs(stage, {OUTPUT_NAME}, {})[0]["path"], OUTPUT_NAME
        )

    def test_native_html_import_and_unknown_selection_failure(self):
        evidence_path = self.root / "evidence.json"
        evidence_path.write_text(
            json.dumps(
                {"schemaVersion": 1, "enemies": {"EM0001_00_0": self.evidence()}}
            ),
            encoding="utf-8",
        )
        self.assertIn("EM0001_00_0", load_evidence(evidence_path))
        path = export_enemy_action_logic(
            self.root / OUTPUT_NAME,
            self.repository,
            self.text,
            evidence_path=evidence_path,
            enemy_ids={"EM0001_00_0"},
        )
        payload = validate_document(path)
        first = payload["enemies"][0]["graphs"][0]
        self.assertEqual(first["basis"], "native_flow")
        self.assertEqual(first["coverage"]["displayedActionTypes"], 1)
        labels = "\n".join(node["label"] for node in first["nodes"])
        self.assertIn("火箭拳\ncRocketPunch", labels)
        self.assertIn("d", labels)
        self.assertNotIn("0x140000001", labels)
        self.assertIn("EM0001_00_0", load_evidence(path))
        self.assertEqual(
            load_evidence(path)["EM0001_00_0"]["graphs"][0]["edges"],
            self.evidence()["graphs"][0]["edges"],
        )
        regenerated = export_enemy_action_logic(
            self.root / "again.html",
            self.repository,
            self.text,
            evidence_path=path,
            enemy_ids={"EM0001_00_0"},
        )
        again = validate_document(regenerated)["enemies"][0]
        self.assertEqual(again["graphs"][0]["decisionCases"], first["decisionCases"])
        self.assertEqual(
            again["provenance"]["nativeSnapshot"],
            payload["enemies"][0]["provenance"]["nativeSnapshot"],
        )
        with self.assertRaisesRegex(ValueError, "Unknown/out-of-scope"):
            export_enemy_action_logic(
                path,
                self.repository,
                self.text,
                enemy_ids={"EM1000_00_0"},
            )

    def test_html_rejects_tampered_payload_and_diagram_inventory(self):
        path = export_enemy_action_logic(
            self.root / OUTPUT_NAME, self.repository, self.text
        )
        original = path.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_document(original.replace("测试怪物", "changed"))
        with self.assertRaisesRegex(ValueError, "diagrams do not match"):
            validate_document(
                original.replace('data-node="start"', 'data-node="absent"', 1)
            )
        with self.assertRaisesRegex(ValueError, "self-contained"):
            validate_document(
                original + '<script src="https://example.com/viewer.js"></script>'
            )

    def test_references_reject_traversal(self):
        for reference in ("../secret.user", "/root/secret.user", "C:/secret.user"):
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                reference_path(reference)

    def test_action_parameter_versions_and_animation_filters_are_not_merged(self):
        self.catalog.action_params = [
            {
                "guid": ACTION,
                "branchGuid": branch,
                "class": "cAttackMain",
                "source": ROOT + "Action/Param.user.3.json",
                "index": 0,
                "actionSource": self.catalog.tables[0]["actionArguments"][0][
                    "actionSource"
                ],
                "parameters": {
                    "_LoopTime": value,
                    "_MotionSequenceFilters": [
                        {
                            "Filter": {
                                "STRUCT__ID_PageNo": 0,
                                "STRUCT__ID_FilterNo": filter_id,
                            }
                        }
                    ],
                },
            }
            for branch, value, filter_id in ((BRANCH, 2.0, 12), (BRANCH_TWO, 3.5, 13))
        ]
        first = self.catalog.tables[0]["actionArguments"][0]
        self.catalog.tables[0]["actionArguments"].append(
            {**first, "index": 3, "branchGuid": BRANCH_TWO}
        )
        actions = [
            row
            for row in resource_actions(self.catalog)
            if row["type"] == "cAttackMain"
        ]
        self.assertEqual(len(actions), 2)
        self.assertEqual({row["parameters"]["_LoopTime"] for row in actions}, {2, 3.5})
        self.assertEqual(len({row["variantId"] for row in actions}), 2)
        self.assertTrue(all(row["parameterResolved"] for row in actions))
        graph = player_graph(self.catalog)
        moves = [
            node
            for node in graph["nodes"]
            if node.get("detail", {}).get("actionType") == "cAttackMain"
        ]
        self.assertEqual(len(moves), 2)
        self.assertIn("动画过滤版本 0/12", moves[0]["label"])
        self.assertIn("动画过滤版本 0/13", moves[1]["label"])

    def test_actionparam_without_branch_array_keeps_default_parameters(self):
        from src.processed_data.enemy_action_logic.source import (
            _action_parameters,
            ZERO_GUID,
        )

        body = {
            "_ActionClassList": [{"app.Example.cAttackMain": {"_LoopTime": 3.5}}],
            "_ActionInfoList": [{"Info": {"_ActionGuid": ACTION}}],
            "_BranchedParamsList": [],
            "_IsUseBranchedParam": False,
        }
        rows = _action_parameters("test", body)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["branchGuid"], ZERO_GUID)
        self.assertEqual(rows[0]["parameters"]["_LoopTime"], 3.5)
        body["_BranchedParamsList"] = [
            {
                "Branches": {
                    "_Params": [
                        {
                            "Branch": {
                                "_Guid": BRANCH,
                                "_ActionClass": {"ace.cActionBase": {}},
                            }
                        }
                    ]
                }
            }
        ]
        rows = _action_parameters("test", body)
        self.assertEqual(rows[1]["branchGuid"], BRANCH)
        self.assertEqual(rows[1]["parameterClass"], "ace.cActionBase")
        self.assertFalse(rows[1]["parameterCompatible"])
        self.assertEqual(rows[1]["parameters"], {})
        body["_BranchedParamsList"] *= 2
        diagnostics = []
        rows = _action_parameters("test", body, diagnostics)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["branchGuid"], ZERO_GUID)
        self.assertEqual(diagnostics[0]["code"], "actionparam_branches_unresolved")

    def test_same_move_caller_contexts_resume_only_their_own_continuations(self):
        graph = _native_graph(self.catalog.phases[0]["id"])
        graph["nodes"] = graph["nodes"][:2]
        graph["edges"] = graph["edges"][:1]
        for suffix in ("a", "b"):
            graph["nodes"].extend(
                [
                    {
                        "id": suffix,
                        "label": "请求动作",
                        "kind": "action",
                        "evidence": "native",
                        "detail": {
                            "actionType": "cAttackMain",
                            "requestSites": [
                                {
                                    "source": self.table,
                                    "index": 0,
                                    "context": "caller-" + suffix,
                                }
                            ],
                            "continuation": {
                                "label": "继续原调用点",
                                "target": "end-" + suffix,
                                "evidence": "native",
                            },
                            "executionFlow": {
                                "entry": "hit",
                                "nodes": [
                                    {
                                        "id": "hit",
                                        "label": "攻击段",
                                        "kind": "process",
                                        "evidence": "native",
                                    }
                                ],
                                "edges": [],
                                "exits": [{"id": "hit", "label": "动画结束"}],
                            },
                        },
                    },
                    {
                        "id": "end-" + suffix,
                        "label": "本路径结束",
                        "kind": "end",
                        "evidence": "native",
                    },
                ]
            )
            graph["edges"].extend(
                [
                    {
                        "from": "check",
                        "to": suffix,
                        "label": "是" if suffix == "a" else "否",
                        "evidence": "native",
                    },
                    {"from": suffix, "to": "end-" + suffix, "evidence": "context"},
                ]
            )
        graph["decisionCases"] = []
        projected = player_graph(self.catalog, graph)
        self.assertEqual(projected["coverage"]["actionVersions"], 1)
        self.assertEqual(projected["coverage"]["actionRequestContexts"], 2)
        for suffix in ("a", "b"):
            edges = [
                e for e in projected["edges"] if e["from"] == suffix + "-v0-resume"
            ]
            self.assertEqual([e["to"] for e in edges], ["end-" + suffix])
            self.assertTrue(
                any(
                    e["from"] == suffix + "-v0-state-hit"
                    and e["to"] == suffix + "-v0-resume"
                    for e in projected["edges"]
                )
            )
        self.assertEqual(
            [e["label"] for e in projected["edges"] if e["from"] == "check"],
            ["是", "否"],
        )
