"""Managed objects read by emulated code: exported JSON, synthetic state, unknowns.

Every value carries ``prov``: the data items it was computed from, so a result
can name its sources (a SkillData slot, a PlayerSkillParam field, an EXE
constant). Unknown runtime state is a ``Unk`` with a readable path; reading a
field of an unknown object yields another unknown named by the field.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from ...config import (
    ARRAY_DATA_OFFSET,
    ARRAY_LENGTH_OFFSET,
    BOX_HEADER,
    FLOAT_VECTORS,
    INTERFACE_FLAG,
    INTERFACE_TABLE_OFFSET,
    LIST_ITEMS_OFFSET,
    LIST_SIZE_OFFSET,
    LIST_VERSION_OFFSET,
    VEC3_SIZE,
    VTABLE_OFFSET,
)

from ..native.values import (
    Method,
    Ptr,
    Unk,
    Unsupported,
    V,
    VirtualMethod,
    f32_bits,
    f64_bits,
    unk,
)

ENUM_TEXT = re.compile(r"^\[(-?\d+)\]\s*(.*)$")
PRIMITIVES = {
    "System.Boolean": 1,
    "System.Byte": 1,
    "System.SByte": 1,
    "System.Int16": 2,
    "System.UInt16": 2,
    "System.Char": 2,
    "System.Int32": 4,
    "System.UInt32": 4,
    "System.Int64": 8,
    "System.UInt64": 8,
    "System.Single": 4,
    "System.Double": 8,
}


class Layouts:
    """Instance field layouts and value-type sizes from the il2cpp dump."""

    def __init__(self, metadata):
        self.metadata = metadata
        self.cache = {}

    def record(self, type_name):
        return self.metadata.get(type_name) or {}

    def fields(self, type_name):
        """offset -> (name, type), inherited fields included, statics excluded."""
        if type_name not in self.cache:
            result, seen, name = {}, set(), type_name
            chain = []
            while name and name not in seen:
                seen.add(name)
                record = self.record(name)
                if not record:
                    break
                chain.append(record)
                name = record.get("parent")
            for record in reversed(chain):
                for field_name, info in record.get("fields", {}).items():
                    if (
                        "Static" in info.get("flags", "")
                        or "offset_from_base" not in info
                    ):
                        continue
                    result[int(info["offset_from_base"], 16)] = (
                        field_name,
                        info["type"],
                    )
            self.cache[type_name] = dict(sorted(result.items()))
        return self.cache[type_name]

    def is_value_type(self, type_name):
        if (
            type_name in PRIMITIVES
            or type_name in FLOAT_VECTORS
            or self.is_enum(type_name)
        ):
            return True
        return self.record(type_name).get("parent") == "System.ValueType"

    def is_enum(self, type_name):
        return self.record(type_name).get("parent") == "System.Enum"

    def is_interface(self, type_name):
        return INTERFACE_FLAG in self.record(type_name).get("flags", "")

    def interface_method(self, type_name, index):
        """(name, il2cpp record) of an interface's index-th method, or None."""
        methods = sorted(
            self.record(type_name).get("methods", {}).items(),
            key=lambda item: item[1].get("id", 0),
        )
        return methods[index] if 0 <= index < len(methods) else None

    def ancestry(self, type_name):
        """The type and its bases, most derived first."""
        chain, name = [], type_name
        while name and name not in chain:
            chain.append(name)
            name = self.record(name).get("parent")
        return chain

    def virtual_method(self, type_name, index):
        """Function address of an object's virtual method in vtable slot index
        (il2cpp vtable_index), searched from the most derived type, or None."""
        for name in self.ancestry(type_name):
            for info in self.record(name).get("methods", {}).values():
                if info.get("vtable_index") == index and info.get("function"):
                    return int(info["function"], 16)
        return None

    def is_struct(self, type_name):
        """A value type with dumped fields (not a primitive, enum or float vector)."""
        return (
            self.is_value_type(type_name)
            and type_name not in PRIMITIVES
            and type_name not in FLOAT_VECTORS
            and not self.is_enum(type_name)
            and bool(self.fields(type_name))
        )

    def size(self, type_name):
        """Inline size of a field or array element of this type."""
        if type_name in PRIMITIVES:
            return PRIMITIVES[type_name]
        if type_name in FLOAT_VECTORS:
            return (
                VEC3_SIZE if type_name == "via.vec3" else 4 * FLOAT_VECTORS[type_name]
            )
        if self.is_enum(type_name):
            under = (
                self.record(type_name)
                .get("fields", {})
                .get("value__", {})
                .get("type", "System.Int32")
            )
            return PRIMITIVES.get(under, 4)
        if self.is_value_type(type_name):
            return int(self.record(type_name).get("size", "0"), 16) - BOX_HEADER
        return 8

    def enum_values(self, type_name):
        return {
            name: info["default"]
            for name, info in self.record(type_name).get("fields", {}).items()
            if name != "value__" and "default" in info
        }


def field_width(layout, off, heap, base=0):
    for start, (_, ftype) in layout.items():
        start -= base
        if start == off:
            if heap.layouts.is_value_type(ftype) and not (
                ftype in PRIMITIVES or heap.layouts.is_enum(ftype)
            ):
                inner = {k: v for k, v in heap.layouts.fields(ftype).items()}
                return field_width(inner, 0, heap, BOX_HEADER) if inner else 4
            return heap.layouts.size(ftype) if heap.layouts.is_value_type(ftype) else 8
        if heap.layouts.is_value_type(
            ftype
        ) and start < off < start + heap.layouts.size(ftype):
            if ftype in FLOAT_VECTORS:
                return 4
            return field_width(
                heap.layouts.fields(ftype), off - start, heap, BOX_HEADER
            )
    return 8


def element_type(type_name):
    if type_name.endswith("[]"):
        return type_name[:-2]
    match = re.match(r"System\.Collections\.Generic\.List`1<(.+)>$", type_name)
    return match.group(1) if match else None


class HObj:
    type_name = "?"
    path = "?"
    exported = False  # built from an exported user file (Heap.convert/user_file)

    def read(self, off, size, heap):
        raise NotImplementedError

    def width(self, off, heap):
        """Size of the field starting at off (vector loads split by it)."""
        layout = heap.layouts.fields(self.type_name) if self.type_name else {}
        return field_width(layout, off, heap)

    def read_wide(self, off, size, heap):
        """A read wider than the field at off (a copy of adjacent fields):
        the bytes are assembled field by field; integers only."""
        value, prov, pos = 0, frozenset(), off
        while pos < off + size:
            width = self.width(pos, heap)
            part = self.read(pos, width, heap)
            if not isinstance(part.val, int) or pos + width > off + size:
                raise Unsupported(
                    f"{self.path}+0x{off:x} 的 {size} 字节读取跨越非整数或不完整字段"
                )
            value |= (part.val & ((1 << 8 * width) - 1)) << 8 * (pos - off)
            prov |= part.prov
            pos += width
        return V(value, prov)

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other


class UnkObj(HObj):
    """Runtime object the exports do not describe; fields stay unknown but named."""

    def __init__(self, type_name, path):
        self.type_name, self.path = type_name, path

    def read(self, off, size, heap):
        if off == 0 and size == 8 and heap.layouts.is_interface(self.type_name):
            return V(Ptr(heap.shared(TypeDescriptor, self.type_name)))
        layout = heap.layouts.fields(self.type_name) if self.type_name else {}
        if off in layout:
            name, ftype = layout[off]
            path = f"{self.path}.{name}"
            dimension = heap.dimension_of(self.type_name, name, ftype)
            if dimension is not None:
                heap.inputs_read.add(dimension)
                if dimension in heap.inputs:
                    return heap.inputs[dimension]
            if not heap.layouts.is_value_type(ftype):
                state = heap.states.get((self.type_name, name))
                if state is not None:
                    return V(Ptr(heap.state_object(*state, path)))
                return V(Ptr(heap.unknown(ftype, path)))
            if heap.layouts.is_struct(ftype):
                return UnkObj(ftype, path).read(BOX_HEADER, size, heap)
            return unk(path)
        for start, (name, ftype) in layout.items():
            inner = heap.layouts.size(ftype) if heap.layouts.is_value_type(ftype) else 8
            if start < off < start + inner:
                if heap.layouts.is_struct(ftype):
                    # An embedded struct: its dumped offsets include the box header.
                    return UnkObj(ftype, f"{self.path}.{name}").read(
                        off - start + BOX_HEADER, size, heap
                    )
                return unk(f"{self.path}.{name}+0x{off - start:x}")
        return unk(f"{self.path}+0x{off:x}")


class TypeDescriptor(HObj):
    """Type word of an object known only by its interface type; its interface
    dispatch table sits at INTERFACE_TABLE_OFFSET."""

    def __init__(self, type_name):
        self.type_name, self.path = None, f"{type_name} 的类型信息"
        self.interface = type_name

    def read(self, off, size, heap):
        if off == INTERFACE_TABLE_OFFSET and size == 8:
            return V(Ptr(heap.shared(DispatchTable, self.interface)))
        return unk(f"{self.path}+{off:#x}")


class DispatchTable(HObj):
    """Interface dispatch table: slot k is the interface's k-th method."""

    def __init__(self, type_name):
        self.type_name, self.path = None, f"{type_name} 的接口表"
        self.interface = type_name

    def read(self, off, size, heap):
        if off >= 0 and off % 8 == 0 and size == 8:
            return V(Method(self.interface, off // 8))
        return unk(f"{self.path}+{off:#x}")


class ClassDescriptor(HObj):
    """Type word of an object whose runtime type is known; vtable slot k sits
    at VTABLE_OFFSET + 8k."""

    def __init__(self, type_name):
        self.type_name, self.path = None, f"{type_name} 的类型信息"
        self.runtime_type = type_name

    def read(self, off, size, heap):
        slot, rest = divmod(off - VTABLE_OFFSET, 8)
        if off >= VTABLE_OFFSET and not rest and size == 8:
            return V(VirtualMethod(self.runtime_type, slot))
        return unk(f"{self.path}+{off:#x}")


class SynthObj(HObj):
    """Object assembled from exports for a scenario (hunter skill state)."""

    def __init__(self, type_name, path, values=None):
        self.type_name, self.path = type_name, path
        self.values = dict(values or {})  # off -> V

    def read(self, off, size, heap):
        if off in self.values:
            return self.values[off]
        return UnkObj(self.type_name, self.path).read(off, size, heap)


class StateObj(SynthObj):
    """A per-skill state object of config.SKILL_STATE_OWNER, of the runtime
    type its constructor allocates: only the skill-enum fields the constructor
    sets are known; its type word resolves virtual calls."""

    def read(self, off, size, heap):
        if off == 0 and size == 8:
            return V(Ptr(heap.shared(ClassDescriptor, self.type_name)))
        return super().read(off, size, heap)


class JsonObj(HObj):
    """A class instance from an exported user file."""

    def __init__(self, type_name, data, path, overrides=None):
        self.type_name, self.data, self.path = type_name, data, path
        self.overrides = dict(overrides or {})  # field name -> V

    def read(self, off, size, heap):
        layout = heap.layouts.fields(self.type_name)
        if off in layout and size > self.width(off, heap):
            return self.read_wide(off, size, heap)
        if off in layout:
            name, ftype = layout[off]
            if name in self.overrides:
                return self.overrides[name]
            if heap.layouts.is_value_type(ftype) and not (
                ftype in PRIMITIVES or heap.layouts.is_enum(ftype)
            ):
                return heap.value_view(
                    ftype, self.field(name, layout), f"{self.path}.{name}"
                ).read(0, size, heap)
            return heap.convert(
                ftype, self.field(name, layout), f"{self.path}.{name}", size
            )
        for start, (name, ftype) in layout.items():
            if heap.layouts.is_value_type(
                ftype
            ) and start < off < start + heap.layouts.size(ftype):
                inner = heap.value_view(
                    ftype, self.field(name, layout), f"{self.path}.{name}"
                )
                return inner.read(off - start, size, heap)
        raise Unsupported(f"{self.type_name}+0x{off:x} 不是字段起点")

    def field(self, name, layout):
        if isinstance(self.data, dict):
            if name in self.data:
                return self.data[name]
            raise Unsupported(f"导出 JSON 缺少字段 {self.type_name}.{name}")
        # A class with one field is exported as that field's value.
        if len(layout) == 1:
            return self.data
        raise Unsupported(f"{self.type_name} 的导出形式无法对应字段 {name}")


class ValueView(HObj):
    """An inline value type; offsets are relative to its first field."""

    def __init__(self, type_name, data, path):
        self.type_name, self.data, self.path = type_name, data, path

    def width(self, off, heap):
        if self.type_name in FLOAT_VECTORS:
            return 4
        return field_width(heap.layouts.fields(self.type_name), off, heap, BOX_HEADER)

    def read(self, off, size, heap):
        if self.type_name in FLOAT_VECTORS:
            values = self.data if isinstance(self.data, list) else [self.data]
            index = off // 4
            if off % 4 or index >= len(values):
                raise Unsupported(f"{self.type_name}+0x{off:x}")
            return V(
                f32_bits(float(values[index])), frozenset({f"{self.path}[{index}]"})
            )
        if self.type_name == "System.Guid":
            raw = uuid.UUID(self.data).bytes_le if isinstance(self.data, str) else None
            if raw is None or off + size > 16:
                raise Unsupported(f"{self.path} 的 Guid 值")
            return V(
                int.from_bytes(raw[off : off + size], "little"), frozenset({self.path})
            )
        if heap.layouts.is_enum(self.type_name) or self.type_name in PRIMITIVES:
            if off:
                raise Unsupported(f"{self.type_name}+0x{off:x}")
            return heap.convert(self.type_name, self.data, self.path, size)
        layout = {
            k - BOX_HEADER: v for k, v in heap.layouts.fields(self.type_name).items()
        }
        if off in layout and size > self.width(off, heap):
            return self.read_wide(off, size, heap)
        if off in layout:
            name, ftype = layout[off]
            value = self.data.get(name) if isinstance(self.data, dict) else None
            return heap.convert(ftype, value, f"{self.path}.{name}", size)
        raise Unsupported(f"{self.type_name}+0x{off:x}")


class ArrayObj(HObj):
    """Managed array: length at +0x1c, elements from +0x20."""

    def __init__(self, elem_type, items, path, *, values=None):
        self.type_name, self.elem_type, self.items, self.path = (
            elem_type + "[]",
            elem_type,
            items,
            path,
        )
        self.values = values  # optional precomputed element V list

    def width(self, off, heap):
        if off < ARRAY_DATA_OFFSET:
            return 4
        if heap.layouts.is_value_type(self.elem_type) and not (
            self.elem_type in PRIMITIVES or heap.layouts.is_enum(self.elem_type)
        ):
            esize = heap.layouts.size(self.elem_type)
            inner = (off - ARRAY_DATA_OFFSET) % esize
            return field_width(
                heap.layouts.fields(self.elem_type), inner, heap, BOX_HEADER
            )
        return (
            heap.layouts.size(self.elem_type)
            if heap.layouts.is_value_type(self.elem_type)
            else 8
        )

    def read(self, off, size, heap):
        if off == ARRAY_LENGTH_OFFSET or (off == ARRAY_LENGTH_OFFSET - 4 and size == 8):
            count = len(self.values if self.values is not None else self.items)
            return V(count if off == ARRAY_LENGTH_OFFSET else count << 32)
        if off < ARRAY_DATA_OFFSET:
            raise Unsupported(f"数组头 +0x{off:x}")
        esize = heap.layouts.size(self.elem_type)
        index, inner = divmod(off - ARRAY_DATA_OFFSET, esize)
        if self.values is not None:
            if index >= len(self.values) or inner:
                raise Unsupported(f"{self.path}[{index}] 越界")
            return self.values[index]
        if index >= len(self.items):
            raise Unsupported(f"{self.path}[{index}] 越界")
        path = f"{self.path}[{index}]"
        if heap.layouts.is_value_type(self.elem_type) and not (
            self.elem_type in PRIMITIVES or heap.layouts.is_enum(self.elem_type)
        ):
            return heap.value_view(self.elem_type, self.items[index], path).read(
                inner, size, heap
            )
        if inner:
            raise Unsupported(f"{path}+0x{inner:x}")
        return heap.convert(self.elem_type, self.items[index], path, size)


class ListObj(HObj):
    def __init__(self, elem_type, items, path):
        self.type_name = f"System.Collections.Generic.List`1<{elem_type}>"
        self.elem_type, self.items, self.path = elem_type, items, path
        self.array = None

    def width(self, off, heap):
        return 8 if off == LIST_ITEMS_OFFSET else 4

    def read(self, off, size, heap):
        if off == LIST_ITEMS_OFFSET:
            if self.array is None:
                self.array = ArrayObj(self.elem_type, self.items, self.path)
            return V(Ptr(self.array))
        if off == LIST_SIZE_OFFSET:
            return V(len(self.items))
        if off == LIST_VERSION_OFFSET:
            return V(0)
        raise Unsupported(f"List +0x{off:x}")


class Heap:
    """Resolves exported values and user-file references into heap objects."""

    def __init__(self, layouts, natives: Path):
        self.layouts = layouts
        self.natives = Path(natives)
        self.files = {}
        self.unknowns = {}
        self.objects = {}
        self.read_files = set()
        # Scenario dimensions (config.DIMENSIONS): inputs holds the values given
        # for the current evaluation by dimension name, inputs_read the
        # dimensions the evaluation read.
        self.dimensions = ()
        self.inputs = {}
        self.inputs_read = set()
        self.singletons = (
            {}
        )  # type -> object every unknown reference of that type resolves to
        # (owner type, field) -> (runtime type, {offset: V}): per-skill state
        # objects (StateObj) an unknown owner's field holds.
        self.states = {}

    def dimension_of(self, type_name, field_name, field_type):
        """Name of the scenario dimension a runtime field supplies, if any."""
        for dimension in self.dimensions:
            if dimension["field"] is not None:
                if dimension["field"] == (type_name, field_name):
                    return dimension["name"]
            elif field_type == dimension["enum"]:
                return dimension["name"]
        return None

    def unknown(self, type_name, path):
        if type_name in self.singletons:
            return self.singletons[type_name]
        key = (type_name, path)
        if key not in self.unknowns:
            self.unknowns[key] = UnkObj(type_name, path)
        return self.unknowns[key]

    def state_object(self, type_name, values, path):
        key = (StateObj, path)
        if key not in self.unknowns:
            self.unknowns[key] = StateObj(type_name, path, values)
        return self.unknowns[key]

    def shared(self, kind, type_name):
        """One object of a kind per type (interface type words and tables)."""
        key = (kind, type_name)
        if key not in self.unknowns:
            self.unknowns[key] = kind(type_name)
        return self.unknowns[key]

    def user_file(self, relative):
        """Root object of an exported user file (relative to natives/STM)."""
        if relative not in self.files:
            path = self.natives / "STM" / (relative + ".3.json")
            document = json.loads(path.read_text(encoding="utf-8"))
            ((type_name, data),) = document[0].items()
            self.read_files.add(path.relative_to(self.natives).as_posix())
            self.files[relative] = JsonObj(
                type_name, data, type_name.rsplit(".", 1)[-1]
            )
            self.files[relative].exported = True
        return self.files[relative]

    def value_view(self, type_name, data, path):
        return ValueView(type_name, data, path)

    def convert(self, ftype, value, path, size):
        prov = frozenset({path})
        if ftype in PRIMITIVES:
            if value is None:
                raise Unsupported(f"{path} 没有导出值")
            if ftype == "System.Single":
                return V(f32_bits(float(value)), prov)
            if ftype == "System.Double":
                return V(f64_bits(float(value)), prov)
            if ftype == "System.Boolean":
                return V(int(bool(value)), prov)
            return V(int(value) & ((1 << (8 * PRIMITIVES[ftype])) - 1), prov)
        if self.layouts.is_enum(ftype):
            if isinstance(value, str):
                match = ENUM_TEXT.match(value)
                if not match:
                    raise Unsupported(f"{path} 枚举文本 {value!r}")
                value = int(match.group(1))
            return V(int(value) & 0xFFFFFFFF, prov)
        if ftype in FLOAT_VECTORS or self.layouts.is_value_type(ftype):
            raise Unsupported(f"{path} 按整体读取值类型 {ftype}")
        # References carry no provenance: results name the scalar leaves they read.
        if value is None:
            return V(0)
        key = (path, id(value))
        if key in self.objects:
            return V(Ptr(self.objects[key][0]))
        item = element_type(ftype)
        if item is not None and isinstance(value, list):
            obj = (ArrayObj if ftype.endswith("[]") else ListObj)(item, value, path)
        elif isinstance(value, dict) and len(value) == 1:
            ((type_name, data),) = value.items()
            if isinstance(data, dict) and set(data) >= {"ref_instance_id", "path"}:
                obj = self.user_file(data["path"])
            else:
                obj = JsonObj(type_name, data, path)
        else:
            return unk(path, prov)
        obj.exported = True
        self.objects[key] = (obj, value)
        return V(Ptr(obj))
