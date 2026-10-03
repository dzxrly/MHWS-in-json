"""Conditional weighted selection; caller supplies the actually eligible pool."""

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


def choose_with_uint32(candidates, draw, *, excluded=()):
    """The verified modulo and cumulative-weight operations; no RNG is assumed."""
    if type(draw) is not int or not 0 <= draw <= 0xFFFFFFFF:
        raise ValueError("抽样值必须是无符号 32 位整数")
    pool = weighted_pool(candidates, excluded=excluded)
    if not pool:
        return None
    ticket = draw % sum(c["weight"] for c in pool)
    for candidate in pool:
        if ticket < candidate["weight"]:
            return candidate["id"]
        ticket -= candidate["weight"]
    raise AssertionError("无效的权重区间")
