"""Validate graph topology and the JSON/HTML pair before release publication."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re

from .definitions import INDEX_NAME
from .diagram import combined_diagram
from .random_choice import weighted_pool
from .catalog import CATALOG_TYPE


def validate_catalog(catalog):
    tables = catalog["tables"]
    counts = dict(
        tableCount=len(tables),
        argumentCount=sum(len(table["arguments"]) for table in tables),
        actionBindings=sum(
            "action" in arg for table in tables for arg in table["arguments"]
        ),
        verifiedPredicates=sum(
            arg.get("predicate", {}).get("status") == "verified"
            for table in tables
            for arg in table["arguments"]
        ),
    )
    if any(
        type(catalog.get(key)) is not int or catalog[key] != value
        for key, value in counts.items()
    ):
        raise ValueError("怪物资源清单统计不一致")
    for source, digest in catalog["sourceHashes"].items():
        if (
            not source.startswith("STM/")
            or ".." in source.split("/")
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("怪物资源清单来源无效")
    for table in tables:
        if (
            table["source"] not in catalog["sourceHashes"]
            or table["controlFlowStatus"] != "not_recovered"
        ):
            raise ValueError("资源清单不能声称已恢复控制流")
        if [arg["slot"] for arg in table["arguments"]] != list(
            range(len(table["arguments"]))
        ):
            raise ValueError("怪物资源参数槽位不完整")
        for arg in table["arguments"]:
            if (
                "action" in arg
                and arg["action"]["definitionRef"] not in catalog["actionDefinitions"]
            ):
                raise ValueError("动作参数定义引用缺失")


def validate_graph(graph):
    if graph.get("schemaVersion") != 1 or not re.fullmatch(
        r"EM\d{4}_\d{2}_\d+", graph.get("enemyId", "")
    ):
        raise ValueError("行动图格式或怪物标识无效")
    profile = graph["profile"]
    if profile != graph["rules"]["profile"]:
        raise ValueError("行动图与规则的来源版本不匹配")
    if not profile.get("gameVersion") or any(
        not re.fullmatch(r"[0-9a-f]{64}", profile.get(key, ""))
        for key in ("exeSha256", "metadataSha256")
    ):
        raise ValueError("行动图来源版本证据无效")
    if graph["metadataVerification"] not in ("matched", "not_supplied"):
        raise ValueError("行动图元数据核对状态无效")
    if not graph.get("sourceHashes") or any(
        not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in graph["sourceHashes"].values()
    ):
        raise ValueError("行动图缺少资源来源证据")
    tables = {table["tableGuid"]: table for table in graph["tables"]}
    if (
        not tables
        or len(tables) != len(graph["tables"])
        or graph["entry"] not in tables
    ):
        raise ValueError("行动图子表重复或入口无效")
    node_count = random_count = unknown_count = unknown_conditions = complete_count = 0
    for table in tables.values():
        nodes = {node["id"]: node for node in table["nodes"]}
        if len(nodes) != len(table["nodes"]) or table["entry"] not in nodes:
            raise ValueError("行动图节点重复或子表入口无效")
        node_count += len(nodes)
        complete_count += table.get("flowStatus", "verified") == "verified"
        for node in nodes.values():
            required = {
                "condition": ("true", "false"),
                "action": ("resume",),
                "call": ("targetTable", "resume"),
                "mutation": ("next",),
                "weighted_random": ("candidates", "fallback"),
                "return": ("value",),
                "unknown": ("reason",),
            }
            if any(key not in node for key in required.get(node["kind"], ())):
                raise ValueError("行动图节点缺少必需的连接或字段")
            if node["kind"] not in {
                "condition",
                "action",
                "call",
                "mutation",
                "return",
                "weighted_random",
                "unknown",
            }:
                raise ValueError("行动图节点类型无效")
            for role in ("true", "false", "next", "resume"):
                if role in node and node[role] not in nodes:
                    raise ValueError("行动图连接指向缺失节点")
            if node["kind"] == "call" and (
                node["targetTable"] not in tables or "resume" not in node
            ):
                raise ValueError("行动图调用或恢复位置无效")
            if node["kind"] == "action" and (
                "resume" not in node or not node.get("action", {}).get("actionClass")
            ):
                raise ValueError("行动图动作请求缺少动作绑定或恢复位置")
            if node["kind"] == "weighted_random":
                random_count += 1
                weighted_pool(node["candidates"])
                if node["fallback"] not in nodes:
                    raise ValueError("行动图随机回退位置无效")
                for candidate in node["candidates"]:
                    target = nodes.get(candidate["id"], {})
                    if (
                        candidate["targetTable"] not in tables
                        or target.get("kind") != "call"
                        or target["targetTable"] != candidate["targetTable"]
                    ):
                        raise ValueError("行动图随机候选与调用连接不一致")
            if node["kind"] == "condition":
                unknown_conditions += node["predicate"]["status"] != "verified"
            if node["kind"] == "unknown":
                unknown_count += 1
                if not node.get("reason"):
                    raise ValueError("未知节点必须说明未核实的部分")
    expected = dict(
        localTables=len(tables),
        nodes=node_count,
        weightedSelections=random_count,
        unknownFlowNodes=unknown_count,
        unknownConditions=unknown_conditions,
        completeLocalTables=complete_count,
    )
    if any(
        type(graph["coverage"].get(key)) is not int or graph["coverage"][key] != value
        for key, value in expected.items()
    ):
        raise ValueError("行动图覆盖统计与实际节点不一致")


class EmbeddedGraph(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.capturing = False
        self.payloads = []
        self.external_scripts = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "script":
            if attrs.get("src"):
                self.external_scripts.append(attrs["src"])
            self.capturing = (
                attrs.get("id") == "data" and attrs.get("type") == "application/json"
            )
            if self.capturing:
                self.payloads.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self.capturing = False

    def handle_data(self, value):
        if self.capturing:
            self.payloads[-1] += value


def validate_html(html, graph):
    parser = EmbeddedGraph()
    parser.feed(html)
    if parser.external_scripts or len(parser.payloads) != 1:
        raise ValueError("行动图 HTML 缺少唯一内嵌数据或依赖外部脚本")
    payload = json.loads(parser.payloads[0])
    if payload.get("graph") != graph or payload.get("diagram") != combined_diagram(
        graph
    ):
        raise ValueError("行动图 HTML 与 JSON 的内容或连接不一致")


def validate_bundle(processed_dir):
    root = Path(processed_dir)
    index = json.loads((root / INDEX_NAME).read_text(encoding="utf-8"))
    if index.get("schemaVersion") != 1 or not index.get("monsters"):
        raise ValueError("行动图索引无效")
    seen = set()
    for item in index["monsters"]:
        enemy_id = item["enemyId"]
        if enemy_id in seen or not re.fullmatch(r"EM\d{4}_\d{2}_\d+", enemy_id):
            raise ValueError("行动图索引中的怪物标识重复或无效")
        seen.add(enemy_id)
        if item["json"] != f"{enemy_id}.json" or item["html"] not in (
            None,
            f"{enemy_id}.html",
        ):
            raise ValueError("行动图索引中的文件名无效")
        folder = (root / INDEX_NAME).parent
        graph = json.loads((folder / item["json"]).read_text(encoding="utf-8"))
        validate_catalog(graph["resourceCatalog"])
        if (
            graph["enemyId"] != enemy_id
            or graph["logicStatus"] != item["logicStatus"]
            or graph["enemyName"] != item["enemyName"]
            or any(
                graph["resourceCatalog"][key] != value
                for key, value in item["resourceSummary"].items()
            )
        ):
            raise ValueError("行动图索引与模型内容不一致")
        if graph.get("documentType") == CATALOG_TYPE:
            if (
                item["html"] is not None
                or item["coverage"] is not None
                or item["logicStatus"] != "not_recovered"
                or item["profile"] != graph["rulesProfile"]
            ):
                raise ValueError("未恢复控制流的资源清单状态无效")
        else:
            validate_graph(graph)
            if (
                item["html"] is None
                or item["logicStatus"] != "partial"
                or any(
                    item[key] != graph[key]
                    for key in ("profile", "coverage", "metadataVerification")
                )
            ):
                raise ValueError("行动图索引与模型内容不一致")
            validate_html((folder / item["html"]).read_text(encoding="utf-8"), graph)
