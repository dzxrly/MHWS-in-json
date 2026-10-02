"""Read typed user3 resources without treating argument arrays as instructions."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterator

from config import SUPPORT_FILES
from src.processed_data.enemy_action_logic.phases import resolve_phases
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextDB

ENEMY_ID = re.compile(r"(?:\[\d+\]\s*)?(EM(\d{4})_(\d{2})_\d+)$", re.I)
ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def typed(value: Any) -> tuple[str, dict]:
    if isinstance(value, dict) and len(value) == 1:
        name, body = next(iter(value.items()))
        if isinstance(body, dict):
            return name, body
    return "", value if isinstance(value, dict) else {}


def scalar(value: Any) -> Any:
    while isinstance(value, dict) and len(value) == 1:
        value = next(iter(value.values()))
    return value


def walk(value: Any, pointer: str = "") -> Iterator[tuple[str, Any]]:
    yield pointer, value
    if isinstance(value, dict):
        for name, item in value.items():
            escaped = name.replace("~", "~0").replace("/", "~1")
            yield from walk(item, f"{pointer}/{escaped}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, f"{pointer}/{index}")


def reference_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"Unsafe resource reference: {value}")
    name = path.as_posix()
    if not name.startswith("STM/"):
        name = "STM/" + name
    if name.endswith(".user"):
        name += ".3.json"
    elif not name.endswith(".json"):
        raise ValueError(f"Unsupported resource reference: {value}")
    return name


@dataclass
class Enemy:
    enemy_id: str
    name: str
    category: str
    prefix: str


@dataclass
class ResourceCatalog:
    enemy: Enemy
    sources: dict[str, str] = field(default_factory=dict)
    entries: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    action_params: list[dict] = field(default_factory=list)
    phases: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "enemyId": self.enemy.enemy_id,
            "name": self.enemy.name,
            "category": self.enemy.category,
            "sourceFiles": self.sources,
            "entries": self.entries,
            "tables": self.tables,
            "actions": self.actions,
            "actionParams": self.action_params,
            "phases": self.phases,
            "diagnostics": self.diagnostics,
        }


class ResourceReader:
    """Case-insensitive path lookup and a shared typed-resource cache."""

    def __init__(self, natives: Path):
        self.root = Path(natives).resolve()
        self.paths: dict[str, Path] = {}
        for path in sorted((self.root / "STM").rglob("*.json")):
            key = path.relative_to(self.root).as_posix().casefold()
            if key in self.paths:
                raise ValueError(f"Case-colliding resources: {path}")
            self.paths[key] = path
        self.cache: dict[str, tuple[Any, str]] = {}

    def resolve(self, relative: str) -> Path | None:
        reference_path(relative)
        return self.paths.get(relative.casefold())

    def read(self, path: Path) -> tuple[Any, str]:
        key = path.relative_to(self.root).as_posix()
        if key not in self.cache:
            raw = path.read_bytes()
            self.cache[key] = (
                json.loads(raw.decode("utf-8-sig")),
                hashlib.sha256(raw).hexdigest(),
            )
        return self.cache[key]


def discover_enemies(repository: SourceRepository, text_db: TextDB) -> list[Enemy]:
    enemies = {}
    for row in repository.table(SUPPORT_FILES["enemy"]):
        match = ENEMY_ID.fullmatch(str(row.get("enemyId", "")))
        if not match or int(match[2]) >= 1000:
            continue
        enemy_id = match[1].upper()
        name = text_db.get(row.get("EnemyName")) or enemy_id
        category = "training" if int(match[2]) == 165 else "large_monster"
        enemy = Enemy(enemy_id, name, category, enemy_id.rsplit("_", 1)[0])
        if enemy_id in enemies:
            raise ValueError(f"Duplicate full enemy ID: {enemy_id}")
        enemies[enemy_id] = enemy
    if not enemies:
        raise ValueError("EnemyData contains no full enemy IDs below EM1000")
    return [enemies[key] for key in sorted(enemies)]


def load_resources(reader: ResourceReader, enemy: Enemy) -> ResourceCatalog:
    catalog = ResourceCatalog(enemy)
    prefix = enemy.prefix.casefold()
    seeds = [
        path
        for path in reader.paths.values()
        if path.name.casefold().startswith(prefix + "_")
        and (
            path.name.casefold().endswith("_parampack.user.3.json")
            or path.name.casefold().endswith("_characterparampack.user.3.json")
            or path.name.casefold().endswith("_param_unique.user.3.json")
            or "btablelist" in path.name.casefold()
        )
    ]
    package = reader.resolve(
        f"STM/GameDesign/Enemy/Package/{enemy.enemy_id}_pkg.user.3.json"
    )
    if package:
        seeds.append(package)
    catalog.entries.extend(
        {
            "role": "discovered_entry_or_sidecar",
            "source": path.relative_to(reader.root).as_posix(),
        }
        for path in seeds
    )
    if not seeds:
        seeds = [
            path
            for path in reader.paths.values()
            if path.name.casefold().startswith(prefix + "_")
            and (
                "_btable_" in path.name.casefold()
                or "_actionid." in path.name.casefold()
            )
        ]
        catalog.diagnostics.append(
            {
                "code": "entry_pack_missing",
                "detail": "未找到入口参数包，按同 ID 文件发现资源；入口归属未确认。",
            }
        )
    pending = list(seeds)
    visited = set()
    raw_tables: list[tuple[str, dict]] = []
    action_map: dict[tuple[str, str], dict] = {}
    phase_map: dict[str, dict] = {}
    while pending:
        path = pending.pop()
        relative = path.relative_to(reader.root).as_posix()
        if relative in visited:
            continue
        visited.add(relative)
        data, digest = reader.read(path)
        catalog.sources[relative] = digest
        if not isinstance(data, list) or len(data) != 1:
            catalog.diagnostics.append({"code": "unsupported_root", "source": relative})
            continue
        root_type, body = typed(data[0])
        if root_type == "ace.btable.user_data.BTable":
            raw_tables.append((relative, body))
        if root_type == "ace.user_data.ActionParam":
            catalog.action_params.extend(
                _action_parameters(relative, body, catalog.diagnostics)
            )
        for pointer, value in walk(body):
            if not isinstance(value, dict):
                continue
            if "path" in value and isinstance(value["path"], str) and value["path"]:
                if not value["path"].endswith((".user", ".json")):
                    continue  # Animation/RCOL/prefab refs are not user3 tables.
                ref = reference_path(value["path"])
                target = reader.resolve(ref)
                if target is None:
                    catalog.diagnostics.append(
                        {
                            "code": "missing_reference",
                            "source": relative,
                            "pointer": pointer,
                            "reference": ref,
                        }
                    )
                else:
                    pending.append(target)
                if "_Table_" in pointer:
                    catalog.entries.append(
                        {
                            "role": pointer.rsplit("/", 2)[-2],
                            "source": relative,
                            "target": ref,
                            "resolved": target is not None,
                        }
                    )
            if (
                root_type == "ace.user_data.ActionID"
                and "_Class" in value
                and "_InstanceGuid" in value
            ):
                guid = scalar(value["_InstanceGuid"])
                if isinstance(guid, str):
                    action_map[(relative, guid)] = {
                        "guid": guid,
                        "class": value["_Class"],
                        "source": relative,
                        "pointer": pointer,
                    }
            for name, rows in value.items():
                if name.startswith("_PhaseList") and isinstance(rows, list):
                    for index, row in enumerate(rows):
                        _, phase = typed(row)
                        if not ("_BattlePhase" in phase or "_Phase" in phase):
                            continue
                        phase_id = str(
                            scalar(
                                phase.get("_BattlePhase", phase.get("_Phase", index))
                            )
                        )
                        item = phase_map.setdefault(
                            phase_id, {"id": phase_id, "configurations": []}
                        )
                        item["configurations"].append(
                            {
                                "source": relative,
                                "field": name,
                                "index": index,
                                "pointer": pointer,
                                "raw": phase,
                            }
                        )
    catalog.actions = sorted(
        action_map.values(), key=lambda row: (row["source"], row["guid"])
    )
    by_guid: dict[str, list[dict]] = {}
    for action in catalog.actions:
        by_guid.setdefault(action["guid"], []).append(action)
    for relative, body in sorted(raw_tables):
        arguments = body.get("_CommandArgArray", [])
        selections, guards = [], []
        for index, argument in enumerate(arguments):
            kind, fields = typed(argument)
            record = {"index": index, "type": kind, "raw": fields}
            if "_EditActionGuid" in fields:
                guid = scalar(fields["_EditActionGuid"])
                asset = scalar(fields.get("_EditAssetIndex"))
                bank_path = _single_ref(body.get("_OrderBank"))
                action_source = _bank_action_source(reader, bank_path, asset)
                matches = [
                    row
                    for row in by_guid.get(guid, [])
                    if action_source is None
                    or row["source"].casefold() == action_source.casefold()
                ]
                record.update(
                    {
                        "guid": guid,
                        "branchGuid": scalar(
                            fields.get("_EditBranchedParamGuid", ZERO_GUID)
                        ),
                        "assetIndex": asset,
                        "actionSource": action_source,
                        "class": matches[0]["class"] if len(matches) == 1 else None,
                    }
                )
                selections.append(record)
            elif any(
                token in kind.rsplit(".", 1)[-1]
                for token in ("Check", "Is", "Random", "Randam")
            ):
                guards.append(record)
        _, table_container = typed(body.get("_Tables"))
        catalog.tables.append(
            {
                "source": relative,
                "exportType": body.get("_ExportBTableType"),
                "serializedNodeCount": len(table_container.get("_DataArray", [])),
                "argumentCount": len(arguments),
                "actionArguments": selections,
                "guardArguments": guards,
                "imports": [
                    _single_ref(item) for item in body.get("_ImportBTableList", [])
                ],
            }
        )
    catalog.phases = resolve_phases(
        enemy.prefix, [phase_map[key] for key in sorted(phase_map)], catalog.tables
    )
    if not catalog.phases:
        catalog.phases = [{"id": "unresolved", "configurations": []}]
        catalog.diagnostics.append(
            {
                "code": "phase_unresolved",
                "detail": "未发现显式阶段列表；汇总为阶段未解析图，不宣称只有一个战斗阶段。",
            }
        )
    return catalog


def _single_ref(value: Any) -> str | None:
    for _, item in walk(value):
        if (
            isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and item["path"]
        ):
            return reference_path(item["path"])
    return None


def _action_parameters(
    source: str, body: dict, diagnostics: list[dict] | None = None
) -> list[dict]:
    """The parallel ActionParam arrays describe versions, never action order."""
    classes = body.get("_ActionClassList", [])
    infos = body.get("_ActionInfoList", [])
    branches = body.get("_BranchedParamsList", [])
    if len(classes) != len(infos):
        if diagnostics is not None:
            diagnostics.append(
                {
                    "code": "actionparam_identity_unresolved",
                    "source": source,
                    "detail": "动作参数与身份数组长度不同，未按索引猜测对应关系。",
                }
            )
        return []
    if branches and len(classes) != len(branches):
        if diagnostics is not None:
            diagnostics.append(
                {
                    "code": "actionparam_branches_unresolved",
                    "source": source,
                    "detail": "分支参数数组长度与动作列表不同；默认参数保留，分支参数对应未恢复。",
                }
            )
        branches = []
    holder = _single_ref(body.get("_ActionIDHolder"))
    result = []
    for index, (action, info) in enumerate(zip(classes, infos)):
        kind, default = typed(action)
        _, fields = typed(info)
        guid = scalar(fields.get("_ActionGuid"))
        _, branch_list = typed(branches[index] if branches else {})
        versions = [(ZERO_GUID, kind, default)]
        for item in branch_list.get("_Params", []):
            _, item = typed(item)
            branch_kind, params = typed(item.get("_ActionClass"))
            versions.append((scalar(item.get("_Guid")), branch_kind, params))
        for branch_guid, parameter_class, params in versions:
            result.append(
                {
                    "guid": guid,
                    "branchGuid": branch_guid,
                    "class": kind.rsplit(".", 1)[-1],
                    "actionSource": holder,
                    "source": source,
                    "index": index,
                    "parameters": params,
                    "parameterClass": parameter_class,
                    "parameterCompatible": parameter_class == kind,
                }
            )
    return result


def _bank_action_source(
    reader: ResourceReader, bank: str | None, index: Any
) -> str | None:
    if bank is None or not isinstance(index, int) or index < 0:
        return None
    path = reader.resolve(bank)
    if path is None:
        return None
    data, _ = reader.read(path)
    for _, value in walk(data):
        if isinstance(value, dict) and isinstance(value.get("_AssetDataList"), list):
            rows = value["_AssetDataList"]
            if index < len(rows):
                _, item = typed(rows[index])
                return _single_ref(item.get("_Asset"))
    return None
