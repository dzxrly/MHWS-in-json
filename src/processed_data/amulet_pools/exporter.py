import json
from pathlib import Path
from typing import Callable
from src.shared.amulets import AmuletCatalog, Loader, load_amulet_catalog
from src.shared.log import file_size, info

NameResolver = Callable[[str | None], list[dict] | str]


def export_amulet_pools(
    output_dir: Path,
    source: AmuletCatalog | Loader,
    name_for_guid: NameResolver | None = None,
) -> None:
    catalog = source if isinstance(source, AmuletCatalog) else load_amulet_catalog(source)
    skill_pool, amulet_pool = build_amulet_pools(catalog, name_for_guid)
    _write_json(output_dir / "skill_pool.json", skill_pool)
    _write_json(output_dir / "amulet_pool.json", amulet_pool)


def build_amulet_pools(
    catalog: AmuletCatalog,
    name_for_guid: NameResolver | None = None,
) -> tuple[list[dict], list[dict]]:
    skill_map = {
        skill_id: _name(guid, name_for_guid)
        for skill_id, guid in catalog.skill_name_guids.items()
    }
    amulet_map = {
        amulet_type: {
            "id": info.id,
            "name": _name(info.name_guid, name_for_guid),
            "rare": _rare(info.rare),
        }
        for amulet_type, info in catalog.amulet_types.items()
    }
    return (
        _skill_pool(catalog.skill_lot, skill_map),
        _amulet_pool(catalog.pt_table, amulet_map, catalog.slots),
    )


def _skill_pool(rows, skill_map: dict) -> list[dict]:
    pools: dict[int, list[dict]] = {}
    for row in rows:
        pt = row.get("SkillPt")
        pools.setdefault(pt, []).append(
            {
                "id": row.get("SkillType"),
                "name": skill_map.get(row.get("SkillType"), row.get("SkillType")),
                "level": row.get("SkillLv"),
            }
        )
    return [{"skillPt": pt, "skillList": pools[pt]} for pt in sorted(pools)]


def _amulet_pool(pt_table, amulet_map: dict, slot_map: dict) -> list[dict]:
    data = []
    for row in pt_table:
        amulet_type = row.get("AmuletType")
        if amulet_type not in amulet_map:
            continue
        entry = {
            "id": str(row.get("Index")),
            "rare": amulet_map[amulet_type],
            "slot": slot_map.get(row.get("SlotPt"), {"slotPt": str(row.get("SlotPt"))}),
        }
        for idx in range(1, 4):
            entry[f"skillPt{idx}"] = str(row.get(f"SkillPt_{idx:02d}", 0))
        data.append(entry)
    return data


def _rare(value) -> str:
    if isinstance(value, str) and value.startswith("RARE"):
        return f"Rare {int(value[4:])}"
    return str(value)


def _name(guid: str | None, resolver: NameResolver | None):
    if resolver is None:
        return guid or ""
    return resolver(guid)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    info(f"    Saved JSON: {path} ({file_size(path)})")
