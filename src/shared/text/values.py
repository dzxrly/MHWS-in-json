"""Explicit text references retained until a language is rendered."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class TextRef:
    guid: str


@dataclass(frozen=True, slots=True)
class TextParts:
    parts: tuple[Any, ...]


def localize(value: Any, resolve: Callable[[str], str | None]) -> Any:
    if isinstance(value, TextRef):
        return resolve(value.guid) or ""
    if isinstance(value, TextParts):
        return "".join(str(localize(part, resolve)) for part in value.parts)
    if isinstance(value, dict):
        return {key: localize(item, resolve) for key, item in value.items()}
    if isinstance(value, list):
        return [localize(item, resolve) for item in value]
    if isinstance(value, tuple):
        return tuple(localize(item, resolve) for item in value)
    return value
