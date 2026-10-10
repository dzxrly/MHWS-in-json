"""Validate native evidence references and Combat entry coverage."""

import re


def validate_native_evidence(evidence):
    if (
        not isinstance(evidence, dict)
        or not evidence.get("type")
        or not evidence.get("method")
    ):
        raise ValueError("缺少原生方法上下文")
    try:
        start, end = int(evidence["address"], 16), int(evidence["end"], 16)
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("原生方法范围无效") from error
    if not 0 < end - start <= 0x200000:
        raise ValueError("原生方法范围未经核实")


def combat_entry_recovered(graph):
    return any(
        entry.get("kind") == "combat_enter" and entry.get("status") == "verified"
        for entry in graph.get("entryPoints", [])
    )
