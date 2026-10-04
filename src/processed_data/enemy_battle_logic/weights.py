"""Validate and display frozen integer weights without drawing a random value."""

from fractions import Fraction


def candidate_node_id(candidate):
    """Read a frozen candidate target independently from its pool slot identity."""
    identity = candidate["id"]
    target = candidate.get("nodeId", identity)
    if (
        not isinstance(identity, str)
        or not identity
        or not isinstance(target, str)
        or not target
    ):
        raise ValueError("随机候选标识或调用节点无效")
    if "nodeId" in candidate:
        index = candidate.get("nativeCandidateIndex")
        if type(index) is not int or index < 0 or identity != f"slot:{index}":
            raise ValueError("随机候选槽位身份与原生索引不一致")
    return target


def weighted_pool(candidates, *, excluded=()):
    excluded = set(excluded)
    pool = []
    seen = set()
    for candidate in candidates:
        key, weight = candidate["id"], candidate["weight"]
        if key in seen:
            raise ValueError("随机候选标识重复")
        seen.add(key)
        if type(weight) is not int or weight < 0:
            raise ValueError("随机权重必须是非负整数")
        if key not in excluded and weight:
            pool.append({"id": key, "weight": weight})
    total = sum(c["weight"] for c in pool)
    if total > 0x7FFFFFFF:
        raise ValueError("总权重超过已支持的有符号 32 位范围")
    return [dict(c, share=str(Fraction(c["weight"], total))) for c in pool]
