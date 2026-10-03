"""Read a JSON metadata export without loading a native executable."""

import hashlib
import json
import mmap
from pathlib import Path
import re

SMALL_FILE_LIMIT = 8 * 1024 * 1024
METHOD_BODY_FIELDS = frozenset({"body", "code", "il", "instructions"})


class Il2cppMetadata:
    """Index top-level types, then decode only the types a product needs.

    REFramework's large export is a pretty-printed type-name/object mapping.
    Compact small exports are also accepted, which makes the reader independent
    of formatting for fixtures and curated metadata subsets. The mapping key is
    the type name; the export's fqn property can be a hash rather than a name.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.suffix.lower() != ".json":
            raise ValueError("IL2CPP input must be a JSON metadata file")
        self._file = None
        self._mapped = None
        self._objects = {}
        self._offsets = {}
        self.loaded = {}
        self._indent = b""
        try:
            self._file = self.path.open("rb")
            self._mapped = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
            self.bytes = len(self._mapped)
            digest = hashlib.sha256()
            for start in range(0, self.bytes, 1024 * 1024):
                digest.update(self._mapped[start : start + 1024 * 1024])
            self.sha256 = digest.hexdigest()
            if self.bytes <= SMALL_FILE_LIMIT:
                self._objects = json.loads(self._mapped[:].decode("utf-8-sig"))
                if not isinstance(self._objects, dict):
                    raise ValueError(
                        "IL2CPP metadata must be a type-name/object mapping"
                    )
            else:
                first = re.search(rb'\n([ \t]+)"(?:[^"\\]|\\.)*":\s*\{', self._mapped)
                if first is None:
                    raise ValueError(
                        "Large IL2CPP export requires pretty-printed type records"
                    )
                self._indent = first[1]
                pattern = re.compile(
                    rb"^" + re.escape(self._indent) + rb'"((?:[^"\\]|\\.)*)":\s*\{',
                    re.M,
                )
                for match in pattern.finditer(self._mapped):
                    name = json.loads(b'"' + match[1] + b'"')
                    if name in self._offsets:
                        raise ValueError(f"Duplicate IL2CPP type: {name}")
                    self._offsets[name] = match.end() - 1
                if not self._offsets:
                    raise ValueError("No IL2CPP type records found")
        except Exception:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._mapped is not None:
            self._mapped.close()
            self._mapped = None
        if self._file is not None:
            self._file.close()
            self._file = None

    def get(self, name: str | None) -> dict | None:
        if not isinstance(name, str):
            return None
        if name in self.loaded:
            return self.loaded[name]
        if self._objects:
            value = self._objects.get(name)
        elif name in self._offsets:
            start = self._offsets[name]
            end = self._mapped.find(b"\n" + self._indent + b"}", start)
            if end < 0:
                raise ValueError(f"Unterminated IL2CPP type record: {name}")
            value = json.loads(self._mapped[start : end + len(self._indent) + 2])
        else:
            value = None
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"Invalid IL2CPP type record: {name}")
        self.loaded[name] = value
        return value

    def fields(self, name: str) -> dict:
        """Follow declared inheritance; derived fields override base fields."""
        chain, seen = [], set()
        while name and name not in seen:
            seen.add(name)
            record = self.get(name)
            if record is None:
                break
            chain.append(record)
            name = record.get("parent")
        fields = {}
        for record in reversed(chain):
            fields.update(record.get("fields", {}))
            for row in record.get("RSZ", []):
                field = row.get("potential_name")
                if field and field not in fields:
                    fields[field] = {"type": row.get("type")}
        return fields

    def type_hash(self, name: str) -> str | None:
        record = self.get(name)
        if record is None:
            return None
        return hashlib.sha256(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def enum(self, field_type: str | None) -> tuple[str | None, dict]:
        name = field_type
        if isinstance(name, str) and "cEditFieldEnum`1<" in name and name.endswith(">"):
            name = name.split("cEditFieldEnum`1<", 1)[1][:-1]
        record = self.get(name)
        if not record or record.get("parent") != "System.Enum":
            return None, {}
        values = {
            key: value["default"]
            for key, value in record.get("fields", {}).items()
            if key != "value__" and "default" in value
        }
        return name, values

    def method_summary(self, name: str) -> dict:
        record = self.get(name)
        if record is None:
            return {"type": name, "matched": False}
        lifecycle = []
        for method, details in record.get("methods", {}).items():
            if re.match(
                r"(?:doEnter|doUpdate|doExit|onEnter|onUpdate|onExit|onExecute)\d*$",
                method,
            ):
                lifecycle.append(
                    {
                        "name": method,
                        "parameters": [
                            row.get("type") for row in details.get("params", [])
                        ],
                        "returns": details.get("returns", {}).get("type"),
                        "hasBody": any(
                            details.get(field) for field in METHOD_BODY_FIELDS
                        ),
                    }
                )
        return {
            "type": name,
            "matched": True,
            "parent": record.get("parent"),
            "lifecycleMethods": lifecycle,
            "methodCount": len(record.get("methods", {})),
        }

    def description(self) -> dict:
        names = self._objects if self._objects else self._offsets
        return {
            "file": self.path.name,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "indexedTypes": len(names),
            "loadedTypes": sum(record is not None for record in self.loaded.values()),
            "nativeExecutableRead": False,
        }
