from __future__ import annotations

import mmh3


def murmur3_utf16(value: str) -> int:
    return mmh3.hash(value.encode("utf-16le"), seed=0xFFFFFFFF, signed=False)


def normalize_path(value: str) -> str:
    return value.replace("\\", "/")


def hex_address(value: int) -> str:
    return f"0x{value:x}"
