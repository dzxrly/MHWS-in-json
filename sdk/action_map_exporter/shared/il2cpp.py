from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import ijson


def iter_il2cpp_types(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """Read one top-level type at a time, independently of JSON formatting."""
    with path.open("rb") as handle:
        start = 3 if handle.read(3) == b"\xef\xbb\xbf" else 0
        handle.seek(start)
        # Check the root without materializing the multi-gigabyte document.
        if next(ijson.basic_parse(handle), (None, None))[0] != "start_map":
            raise ValueError("IL2CPP dump must contain a top-level JSON object")
        handle.seek(start)
        for name, value in ijson.kvitems(handle, ""):
            if isinstance(value, dict):
                yield name, value
