"""Evaluate skill-consuming functions for every equipped skill and level.

Scenario: exactly one skill equipped at one level (for GROUP/SERIES skills, the
level is the number of equipped pieces). The hunter skill object is assembled
from SkillCommonData/SkillData the way the game stores it (EquipSkillData per
skill, EquipSkillInfo with the obfuscated level), so the real helper code runs
unchanged. Global parameters come from PlayerGlobalParam and the files it
references. Everything else is an unknown named after its field path.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from ...config import (
    ARRAY_DATA_OFFSET,
    ARRAY_LENGTH_OFFSET,
    BOX_HEADER,
    LIST_ITEMS_OFFSET,
    LIST_SIZE_OFFSET,
    LIST_VERSION_OFFSET,
    OBJECT_HEADER_WORD,
    CATEGORY_ENUM,
    EQUIP_DATA_HOLDER,
    EQUIP_SKILL_DATA,
    EQUIP_SKILL_INFO,
    HUNTER_SKILL,
    PLAYER_GLOBAL_PARAM,
    SKILL_COMMON,
    SKILL_COMMON_ROW,
    SKILL_DATA,
    SKILL_DATA_ROW,
    SKILL_ENUM,
    SKILL_FIXED_ENUM,
    SKILL_STATE_OWNER,
    DIMENSIONS,
)
from .heap import (
    ENUM_TEXT,
    ArrayObj,
    Heap,
    HObj,
    JsonObj,
    Layouts,
    Ptr,
    SynthObj,
    Unsupported,
    V,
)

FLOAT_TYPES = ("System.Single", "System.Double")


def enum_name(text):
    match = ENUM_TEXT.match(text) if isinstance(text, str) else None
    return match.group(2) if match else text


class StructView(HObj):
    """An inline value-type element given as offset -> V."""

    def __init__(self, type_name, path, values):
        self.type_name, self.path, self.values = type_name, path, values

    def read(self, off, size, heap):
        if off in self.values:
            return self.values[off]
        if 0 <= off < heap.layouts.size(self.type_name):
            return V(0)  # padding: every field of the struct has an entry
        raise Unsupported(f"{self.path}+0x{off:x}")

    def width(self, off, heap):
        return 8 if off in (0x0, 0x8) else 4


class StructArray(ArrayObj):
    def __init__(self, elem_type, views, path):
        super().__init__(elem_type, [], path, values=views)

    def read(self, off, size, heap):
        if off == ARRAY_LENGTH_OFFSET:
            return V(len(self.values))
        if off < ARRAY_DATA_OFFSET:
            raise Unsupported(f"数组头 +0x{off:x}")
        esize = heap.layouts.size(self.elem_type)
        index, inner = divmod(off - ARRAY_DATA_OFFSET, esize)
        if index >= len(self.values):
            raise Unsupported(f"{self.path}[{index}] 越界")
        return self.values[index].read(inner, size, heap)

    def width(self, off, heap):
        if off < ARRAY_DATA_OFFSET:
            return 4
        esize = heap.layouts.size(self.elem_type)
        inner = off - ARRAY_DATA_OFFSET
        return self.values[inner // esize].width(inner % esize, heap)


class SkillWorld:
    """Exports and native identities shared by every scenario."""

    def __init__(self, natives, metadata, pe, index):
        self.natives, self.metadata, self.pe, self.index = natives, metadata, pe, index
        self.layouts = Layouts(metadata)
        self.runtime = self.layouts.enum_values(SKILL_ENUM)  # name -> runtime
        self.fixed = self.layouts.enum_values(SKILL_FIXED_ENUM)  # name -> fixed
        self.runtime_names = {v: k for k, v in self.runtime.items()}
        self.fixed_names = {v & 0xFFFFFFFF: k for k, v in self.fixed.items()}
        self.categories = self.layouts.enum_values(CATEGORY_ENUM)
        self.common = {}
        for row in self.rows(SKILL_COMMON, SKILL_COMMON_ROW):
            name = enum_name(row["_skillId"])
            if name != "NONE":
                self.common[name] = row
        self.levels = defaultdict(list)
        for row in self.rows(SKILL_DATA, SKILL_DATA_ROW):
            name = enum_name(row["_skillId"])
            if name != "NONE":
                self.levels[name].append(row)
        for rows in self.levels.values():
            rows.sort(key=lambda r: r["_SkillLv"])
        setter, pairs = index.remap_pairs()
        self.remap = {self.runtime_names[s]: self.runtime_names[g] for s, g in pairs}
        self.remap_setter = setter
        self.table_slot, self.cookie = index.value_helper_globals()
        self.chain_root, self.chain_offsets = index.param_chain()
        # Per-skill state objects: their runtime type and skill-enum fields as
        # the owner's constructor sets them; other initial values are runtime
        # state and stay unknown.
        self.states = {}
        found = index.state_objects(SKILL_STATE_OWNER, self.layouts)
        for field, (type_name, stores) in found.items():
            layout = self.layouts.fields(type_name)
            values = {
                off: V(imm & 0xFFFFFFFF)
                for off, imm in stores.items()
                if off in layout and layout[off][1] == SKILL_ENUM
            }
            if values:
                self.states[(SKILL_STATE_OWNER, field)] = (type_name, values)

    def rows(self, relative, row_type):
        document = json.loads((self.natives / relative).read_text(encoding="utf-8"))
        ((_, root),) = document[0].items()
        rows = []
        for item in root["_Values"]:
            ((type_name, data),) = item.items()
            if type_name != row_type:
                raise ValueError(f"{relative} 的行类型 {type_name} 不是 {row_type}")
            rows.append(self.with_backing_fields(row_type, data))
        return rows

    def with_backing_fields(self, type_name, data):
        """Fill <x>k__BackingField runtime enums from the serialized _x fields by name."""
        data = dict(data)
        for _, (field, ftype) in self.layouts.fields(type_name).items():
            match = re.match(r"<(\w+)>k__BackingField$", field)
            if not match or field in data:
                continue
            source = next(
                (k for k in data if k.lower() == "_" + match.group(1).lower()), None
            )
            if source is None:
                continue
            item_type = ftype[:-2] if ftype.endswith("[]") else ftype
            values = self.layouts.enum_values(item_type)
            if not values:
                continue

            def convert(text):
                name = enum_name(text)
                if name not in values:
                    raise ValueError(f"{type_name}.{source} 的 {name} 不在 {item_type}")
                return f"[{values[name]}] {name}"

            raw = data[source]
            data[field] = (
                [convert(t) for t in raw] if isinstance(raw, list) else convert(raw)
            )
        return data

    def max_level(self, name):
        return max((r["_SkillLv"] for r in self.levels.get(name, ())), default=0)

    def category(self, name):
        row = self.common.get(name)
        return enum_name(row["_skillCategory"]) if row else None


class Scenario:
    """Heap and globals for one equipped skill at one level."""

    def __init__(self, world: SkillWorld, skill, level):
        self.world, self.skill, self.level = world, skill, level
        self.heap = Heap(world.layouts, world.natives)
        self.heap.dimensions = DIMENSIONS
        self.heap.states = world.states
        layouts = world.layouts
        count = max(world.runtime.values()) + 1
        holder_elements = []
        for runtime in range(count):
            name = world.runtime_names.get(runtime)
            holder_elements.append(self.equip_skill_data(name, runtime))
        holder = SynthObj(
            EQUIP_DATA_HOLDER,
            "EquipDataHolder",
            {
                self.offset(EQUIP_DATA_HOLDER, "_EquipSkillDataArray"): V(
                    Ptr(
                        StructArray(EQUIP_SKILL_DATA, holder_elements, "EquipSkillData")
                    )
                ),
            },
        )
        infos = [V(0)] * count
        target = world.runtime[skill]
        element = holder_elements[target]
        info_values = {OBJECT_HEADER_WORD: V(0)}
        base = self.offset(EQUIP_SKILL_INFO, "_SkillData")
        for off, value in element.values.items():
            info_values[base + off] = value
        # via.rds.Mandrake stores the level as v / m.
        lv = self.offset(EQUIP_SKILL_INFO, "_SkillLv")
        mandrake = {
            name: off - BOX_HEADER
            for off, (name, _) in layouts.fields("via.rds.Mandrake").items()
        }
        info_values[lv + mandrake["v"]] = V(
            level, frozenset({f"装备技能等级 {skill} Lv{level}"})
        )
        info_values[lv + mandrake["m"]] = V(1)
        info_values[self.offset(EQUIP_SKILL_INFO, "_Skill")] = V(target)
        infos[target] = V(
            Ptr(SynthObj(EQUIP_SKILL_INFO, f"EquipSkillInfo[{skill}]", info_values))
        )
        self.this = SynthObj(
            HUNTER_SKILL,
            "cHunterSkill",
            {
                self.offset(HUNTER_SKILL, "_CurrentSkillInfoDic"): V(
                    Ptr(
                        ArrayObj(
                            EQUIP_SKILL_INFO, [], "_CurrentSkillInfoDic", values=infos
                        )
                    )
                ),
                self.offset(HUNTER_SKILL, "_EquipDataHolderRef"): V(Ptr(holder)),
            },
        )
        # The one hunter's skill object, however the calling code reaches it.
        self.heap.singletons[HUNTER_SKILL] = self.this
        remap = [V(0)] * count
        for source, group in world.remap.items():
            remap[world.runtime[source]] = V(
                world.runtime[group], frozenset({"HunterSkillDef.SkillToGroupSkill"})
            )
        chain_target = self.heap.user_file(
            PLAYER_GLOBAL_PARAM.removeprefix("STM/").removesuffix(".3.json")
        )
        node = V(Ptr(chain_target))
        for depth, off in reversed(list(enumerate(world.chain_offsets[:2]))):
            node = V(
                Ptr(
                    SynthObj(
                        "singleton", f"PlayerGlobalParam 单例链 {depth}", {off: node}
                    )
                )
            )
        self.globals = {
            world.table_slot: V(
                Ptr(ArrayObj(SKILL_ENUM, [], "SkillToGroupSkill", values=remap))
            ),
            world.chain_root: node,
        }

    def offset(self, type_name, field):
        for off, (name, _) in self.world.layouts.fields(type_name).items():
            if name == field:
                return off
        raise ValueError(f"{type_name} 缺少字段 {field}")

    def equip_skill_data(self, name, runtime):
        """EquipSkillData of one skill as the game builds it from the two tables."""
        world, heap = self.world, self.heap
        layout = {
            n: off - BOX_HEADER
            for off, (n, _) in world.layouts.fields(EQUIP_SKILL_DATA).items()
        }
        values = {off: V(0) for off in layout.values()}
        common = world.common.get(name)
        rows = world.levels.get(name, [])
        if common is not None:
            values[layout["_SkillCommonData"]] = V(
                Ptr(JsonObj(SKILL_COMMON_ROW, common, f"SkillCommonData[{name}]"))
            )
            category = enum_name(common["_skillCategory"])
            values[layout["_SkillCategory"]] = V(
                world.categories[category],
                frozenset({f"SkillCommonData[{name}]._skillCategory"}),
            )
        if rows:
            items = [
                V(
                    Ptr(
                        JsonObj(
                            SKILL_DATA_ROW, r, f"SkillData[{name} Lv{r['_SkillLv']}]"
                        )
                    )
                )
                for r in rows
            ]
            array = ArrayObj(SKILL_DATA_ROW, [], f"SkillData[{name}]", values=items)
            list_obj = SynthObj(
                f"System.Collections.Generic.List`1<{SKILL_DATA_ROW}>",
                f"SkillData[{name}]",
                {
                    LIST_ITEMS_OFFSET: V(Ptr(array)),
                    LIST_SIZE_OFFSET: V(len(items)),
                    LIST_VERSION_OFFSET: V(0),
                },
            )
            values[layout["_SkillLevelDataList"]] = V(Ptr(list_obj))
            values[layout["_SkillMaxLv"]] = V(
                world.max_level(name), frozenset({f"SkillData[{name}] 最大等级"})
            )
        values[layout["_Skill"]] = V(runtime)
        return StructView(EQUIP_SKILL_DATA, f"EquipSkillData[{name}]", values)
