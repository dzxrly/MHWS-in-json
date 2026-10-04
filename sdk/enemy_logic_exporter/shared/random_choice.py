"""Inspect verified integer random selection offline."""

from .weights import weighted_pool


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
