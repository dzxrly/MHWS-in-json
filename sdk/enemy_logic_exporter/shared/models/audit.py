"""Check SDK discovery coverage before an action graph is eligible for release."""

import re
import hashlib
import json
from .catalog import EXPECTED_ENEMY_IDS


def discovery_digest(discovery):
    return hashlib.sha256(
        json.dumps(
            discovery, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def validate_native_evidence(evidence):
    if (
        not isinstance(evidence, dict)
        or not evidence.get("type")
        or not evidence.get("method")
    ):
        raise ValueError("缺少原生方法上下文")
    if not re.fullmatch(r"[0-9a-f]{64}", evidence.get("nativeSha256", "")):
        raise ValueError("缺少原生方法字节摘要")
    try:
        start, end = int(evidence["address"], 16), int(evidence["end"], 16)
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("原生方法范围无效") from error
    if not 0 < end - start < 200000:
        raise ValueError("原生方法范围未经核实")


def combat_entry_recovered(graph):
    return any(
        entry.get("kind") == "combat_enter" and entry.get("status") == "verified"
        for entry in graph.get("entryPoints", [])
    )


def validate_release_graph(graph):
    if graph["enemyId"] not in EXPECTED_ENEMY_IDS:
        raise ValueError("正式怪物范围不匹配或包含训练靶")
    if not combat_entry_recovered(graph):
        raise ValueError("战斗总入口尚未恢复，不能通过正式发布验收")
    for entry in graph.get("entryPoints", []):
        validate_native_evidence(entry.get("evidence"))
    for table in graph["tables"]:
        validate_native_evidence(table.get("evidence"))
    audit = graph.get("recoveryAudit", {})
    if audit.get("reviewed") is not True or not re.fullmatch(
        r"[0-9a-f]{64}", audit.get("discoverySha256", "")
    ):
        raise ValueError("缺少经过核实的 SDK 入口追踪与资源侧核查记录")
    discovery = audit.get("discovery", {})
    if (
        discovery.get("profile") != graph.get("profile")
        or discovery_digest(discovery) != audit["discoverySha256"]
    ):
        raise ValueError("SDK 发现记录的内容、摘要或版本不匹配")
    for key in ("discoveredMethods", "actionRequestSites"):
        if discovery.get(key) != audit.get(key):
            raise ValueError("SDK 发现记录与覆盖验收范围不一致")
    methods = {
        table["evidence"]["type"] + ":" + table["evidence"]["method"]
        for table in graph["tables"]
    }
    discovered = audit.get("discoveredMethods", [])
    if not discovered or len(discovered) != len(set(discovered)):
        raise ValueError("SDK 发现的方法范围为空或重复")
    boundaries = {
        item["method"]
        for item in audit.get("methodBoundaries", [])
        if item.get("reason") and item.get("evidence")
    }
    for item in audit.get("methodBoundaries", []):
        validate_native_evidence(item.get("evidence"))
    if set(discovered) != methods | boundaries:
        raise ValueError("SDK 发现的方法没有逐项进入模型或明确研究边界")
    if any(all(n["kind"] == "unknown" for n in t["nodes"]) for t in graph["tables"]):
        raise ValueError("不能用整个未知子表替代已发现的控制流")
    modeled_sites = {
        node["requestSite"]
        for table in graph["tables"]
        for node in table["nodes"]
        if node["kind"] == "action" and "requestSite" in node
    }
    discovered_sites = audit.get("actionRequestSites", [])
    if not discovered_sites or modeled_sites != set(discovered_sites):
        raise ValueError("SDK 发现的动作请求位置与模型不一致")
    if audit.get("resourceInventoryChecked") is not True:
        raise ValueError("尚未核查资源侧动作、表和特殊命令的引用缺口")
    for item in audit.get("unreferencedResources", []):
        if not item.get("source") or not item.get("reason") or not item.get("evidence"):
            raise ValueError("未找到引用的资源必须逐项保留证据和原因")
