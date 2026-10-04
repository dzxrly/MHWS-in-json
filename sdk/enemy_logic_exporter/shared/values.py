"""Read scalar and enum values already present in JSON."""

import re


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
