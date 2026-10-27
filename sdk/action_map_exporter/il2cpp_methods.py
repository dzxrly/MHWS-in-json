from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
import re
from typing import Any

from .shared.il2cpp import iter_il2cpp_types

from .models import Il2CppMethod

_MOTION_FIELD = re.compile(r"motion(?:set)?(?:id)?(?:_?\d+)?$", re.IGNORECASE)
_METHOD_INDEX_SUFFIX = re.compile(r"\d+$")


@dataclass(frozen=True, slots=True)
class MotionField:
    declaring_type: str
    name: str
    offset: int


class Il2CppMethodCatalog:
    def __init__(
        self,
        target_methods: dict[str, list[Il2CppMethod]],
        function_addresses: list[int],
        parents: dict[str, str] | None = None,
        fields: dict[str, tuple[MotionField, ...]] | None = None,
        records: dict[str, dict[str, Any]] | None = None,
        source_path: Path | None = None,
        strict_addresses: bool = False,
    ) -> None:
        self.target_methods = target_methods
        self.function_addresses = function_addresses
        self.parents = parents or {}
        self.fields = fields or {}
        self.records = records or {}
        self.source_path = source_path
        self.strict_addresses = strict_addresses

    def lineage(self, type_name: str) -> tuple[str, ...]:
        result: list[str] = []
        while type_name and type_name not in result:
            result.append(type_name)
            type_name = self.parents.get(type_name, "")
        return tuple(result)

    def motion_fields(self, type_name: str) -> dict[int, MotionField]:
        candidates: dict[int, set[MotionField]] = {}
        for name in self.lineage(type_name):
            for field in self.fields.get(name, ()):
                candidates.setdefault(field.offset, set()).add(field)
        return {
            offset: min(values, key=lambda f: f.declaring_type)
            for offset, values in candidates.items()
            if len({(f.name, f.offset) for f in values}) == 1
        }

    def constructor_at(self, caller_type: str, address: int) -> Il2CppMethod | None:
        # Shared code addresses are resolved in the caller's actual inheritance
        # chain, never by an arbitrary global address-to-type winner.
        for name in self.lineage(caller_type):
            for method in self.target_methods.get(name, ()):
                if (
                    method.function_address == address
                    and method.method_name.startswith(".ctor")
                ):
                    return method
        return None

    def inherited_methods(
        self, type_name: str, namespace_prefix: str
    ) -> list[Il2CppMethod]:
        """Non-constructor methods a type inherits without overriding them.

        Only ancestors inside ``namespace_prefix`` (the weapon's own action
        namespace) are used: weapon motion banks share IDs, so a constant in a
        generic base class cannot be attributed to one weapon.
        """
        overridden = {
            _method_base_name(method.method_name)
            for method in self.target_methods.get(type_name, ())
        }
        output: list[Il2CppMethod] = []
        for ancestor in self.lineage(type_name)[1:]:
            if not ancestor.startswith(namespace_prefix):
                break
            methods = self.target_methods.get(ancestor, ())
            output.extend(
                method
                for method in methods
                if not method.method_name.startswith((".ctor", ".cctor"))
                and _method_base_name(method.method_name) not in overridden
            )
            overridden |= {_method_base_name(method.method_name) for method in methods}
        return output

    @classmethod
    def load(
        cls,
        path: Path,
        target_types: set[str] | None = None,
        *,
        record_types: set[str] | None = None,
        strict_addresses: bool = False,
    ) -> "Il2CppMethodCatalog":
        """Index methods once; retain full signatures only for reviewed types."""
        path = path.expanduser().resolve()
        addresses: set[int] = set()
        parents: dict[str, str] = {}
        fields: dict[str, tuple[MotionField, ...]] = {}
        all_methods: dict[str, list[Il2CppMethod]] = {}
        records = {}
        for type_name, obj in iter_il2cpp_types(path):
            if record_types is not None and type_name in record_types:
                records[type_name] = {
                    key: obj[key]
                    for key in ("address", "fields", "methods")
                    if key in obj
                }
            parent = obj.get("parent")
            if isinstance(parent, str):
                parents[type_name] = parent
            found_fields = []
            for name, field in (obj.get("fields") or {}).items():
                if (
                    isinstance(field, dict)
                    and field.get("type") in {"System.UInt32", "System.Int32"}
                    and "Static" not in str(field.get("flags", ""))
                    and _MOTION_FIELD.search(name)
                ):
                    offset = _parse_address(field.get("offset_from_base"))
                    if offset:
                        found_fields.append(MotionField(type_name, name, offset))
            if found_fields:
                fields[type_name] = tuple(found_fields)
            methods = obj.get("methods", {})
            if strict_addresses and not isinstance(methods, dict):
                raise ValueError("IL2CPP methods must be an object")
            methods = methods or {}
            for method_name, method in methods.items():
                if not isinstance(method, dict):
                    if strict_addresses:
                        raise ValueError("IL2CPP method must be an object")
                    continue
                value = method.get("function")
                if strict_addresses and value:
                    # Native rule bounds previously used int(..., 16) for
                    # every declared function, including unrelated methods.
                    address = int(value, 16)
                    addresses.add(address)
                else:
                    address = _parse_address(value)
                if address == 0:
                    continue
                addresses.add(address)
                record = Il2CppMethod(type_name, method_name, address)
                all_methods.setdefault(type_name, []).append(record)

        catalog = cls(
            all_methods,
            sorted(addresses),
            parents,
            fields,
            records,
            path,
            strict_addresses,
        )
        return catalog if target_types is None else catalog.select(target_types)

    def select(self, target_types: set[str]) -> "Il2CppMethodCatalog":
        """Select action types and their ancestors without rereading metadata."""
        closure = set(target_types)
        pending = list(target_types)
        while pending:
            parent = self.parents.get(pending.pop(), "")
            if parent and parent not in closure:
                closure.add(parent)
                pending.append(parent)
        # Ancestors keep every method: constructors for the field-write
        # chain and the rest for inherited_methods().
        normalized: dict[str, list[Il2CppMethod]] = {}
        for type_name in closure:
            distinct = {
                (method.method_name, method.function_address): method
                for method in self.target_methods.get(type_name, [])
            }
            normalized[type_name] = sorted(
                distinct.values(),
                key=lambda method: (method.function_address, method.method_name),
            )
        return type(self)(
            normalized,
            self.function_addresses,
            {name: self.parents[name] for name in closure if name in self.parents},
            {name: self.fields[name] for name in closure if name in self.fields},
            source_path=self.source_path,
            strict_addresses=self.strict_addresses,
        )


def _method_base_name(method_name: str) -> str:
    # Dump keys append the method index ("doEnter1050554").
    return _METHOD_INDEX_SUFFIX.sub("", method_name)


def _parse_address(value: Any) -> int:
    text = str(value)
    if text.casefold().startswith("0x"):
        text = text[2:]
    try:
        return int(text, 16)
    except ValueError:
        return 0
