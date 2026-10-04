"""Read scalar and enum values already present in JSON."""

import re
from dataclasses import dataclass
import math


class MissingState(ValueError):
    pass


def scalar(value):
    while isinstance(value, dict) and len(value) == 1:
        value = next(iter(value.values()))
    return value


def enum_number(value):
    value = scalar(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        match = re.match(r"^\[(-?\d+)\]", value)
        if match:
            return int(match[1])
    raise MissingState("枚举缺少数值，不能仅凭名称推测")


@dataclass(frozen=True)
class Outcome:
    truth: bool | None
    reason: str


def number(value):
    value = scalar(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissingState("缺少数值")
    if not math.isfinite(value):
        raise MissingState("数值不是有限数")
    return value


def required(mapping, key):
    if key not in mapping:
        raise MissingState(f"缺少状态：{key}")
    return mapping[key]
