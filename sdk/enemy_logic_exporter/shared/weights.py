"""Validate and display frozen integer weights without drawing a random value."""

from fractions import Fraction


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
