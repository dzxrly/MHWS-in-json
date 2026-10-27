from __future__ import annotations

import json
import math
from pathlib import Path
from uuid import uuid4


def finite_number(value: float) -> float | str:
    if math.isfinite(value):
        return value
    if math.isnan(value):
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"


def normalize_json_value(value: object) -> object:
    """Represent non-finite game values explicitly without emitting invalid JSON."""
    if isinstance(value, float):
        return finite_number(value)
    if isinstance(value, dict):
        return {key: normalize_json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json_value(child) for child in value]
    return value


def write_json_atomic(target: Path, document: object) -> None:
    """Write readable UTF-8 JSON without exposing a partially written target."""

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                normalize_json_value(document),
                handle,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
