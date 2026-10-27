from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re

from .models import (
    MotbankEntryRecord,
    MotlistIndexDocument,
    MotlistRequestSetEvent,
    MotionTarget,
)

MOTLIST_FORMAT = "re_engine_motlist_action_tracks_v1"
MOTBANK_FORMAT = "re_engine_motbank_v1"
_WEAPON_BANK = re.compile(
    r"(?:^|/)Motion/Player/Weapon/(Wp(?:0[0-9]|1[0-3]))/wp\d{2}\.motbank(?:\.\d+)?$",
    re.IGNORECASE,
)
_MOTLIST_SUFFIX = re.compile(r"\.motlist(?:\.\d+)?$", re.IGNORECASE)


class MotbankCatalog:
    def __init__(self, entries: list[MotbankEntryRecord]) -> None:
        self.entries = entries

    @classmethod
    def load_from_directory(cls, directory: Path) -> "MotbankCatalog":
        root = directory.expanduser().resolve()
        records: list[MotbankEntryRecord] = []
        paths = sorted(
            root.rglob("*.motbank.4.json"),
            key=lambda path: str(path).casefold(),
        )
        for path in paths:
            relative = path.relative_to(root).as_posix()
            match = _WEAPON_BANK.search(relative.removesuffix(".json"))
            if match is None:
                continue
            scope = f"Wp{int(match.group(1)[2:]):02d}"
            document = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(document, dict)
                or document.get("_format") != MOTBANK_FORMAT
            ):
                raise ValueError(f"不是 {MOTBANK_FORMAT} MOTBANK JSON: {path}")
            source = document.get("sourcePath")
            source_match = (
                _WEAPON_BANK.search(source.replace("\\", "/"))
                if isinstance(source, str)
                else None
            )
            if (
                source_match is None
                or source_match.group(1).casefold() != scope.casefold()
            ):
                raise ValueError(f"MOTBANK sourcePath 与武器目录不一致: {path}")
            entries = document.get("motlists")
            if not isinstance(entries, list):
                raise ValueError(f"MOTBANK JSON 缺少 motlists: {path}")
            for entry in entries:
                if (
                    not isinstance(entry, dict)
                    or any(
                        type(entry.get(k)) is not int for k in ("bankId", "bankType")
                    )
                    or not isinstance(entry.get("path"), str)
                    or not entry["path"].strip()
                ):
                    raise ValueError(f"MOTBANK 条目字段无效: {path}")
                records.append(
                    MotbankEntryRecord(
                        scope=scope,
                        bank_id=entry["bankId"],
                        bank_type=entry["bankType"],
                        motlist_path=normalize_motlist_resource_path(entry["path"]),
                        source_path=source.replace("\\", "/"),
                    )
                )

        _validate_banks(records, root)
        records.sort(
            key=lambda item: (
                item.scope,
                item.bank_id,
                item.motlist_path.casefold(),
            )
        )
        return cls(records)


class MotlistJsonCatalog:
    def __init__(self, documents: list[MotlistIndexDocument]) -> None:
        self.documents = documents
        self._by_resource = {
            _motlist_key(document.source_path): document for document in documents
        }

    @classmethod
    def load(cls, root: Path) -> "MotlistJsonCatalog":
        documents: list[MotlistIndexDocument] = []
        paths = sorted(
            (
                path
                for path in root.expanduser().resolve().rglob("*.json")
                if _is_player_motion_path(path)
            ),
            key=lambda path: str(path).casefold(),
        )
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(document, dict)
                or document.get("_format") != MOTLIST_FORMAT
            ):
                continue
            source_path = document.get("sourcePath")
            if not isinstance(source_path, str) or not source_path.strip():
                raise ValueError(f"MOTLIST JSON 缺少 sourcePath: {path}")
            events: list[MotlistRequestSetEvent] = []
            mappings = document.get("requestSetMappings")
            if isinstance(mappings, list):
                for mapping in mappings:
                    if not isinstance(mapping, dict):
                        continue
                    events.append(
                        MotlistRequestSetEvent(
                            motion_id=_int(mapping.get("motionId")),
                            motion_name=_text(mapping.get("motionName")),
                            request_set_id=_int(mapping.get("requestSetId")),
                            clip_source=_text(mapping.get("clipSource")),
                            clip_index=_int(mapping.get("clipIndex")),
                            main_track_name=_text(mapping.get("mainTrackName")),
                            track_index=_int(mapping.get("trackIndex")),
                            track_name=_text(mapping.get("trackName")),
                            start_frame=_float(mapping.get("startFrame")),
                            end_frame=(
                                _float(mapping["endFrame"])
                                if mapping.get("endFrame") is not None
                                else None
                            ),
                        )
                    )
            grouped: dict[int, list[MotlistRequestSetEvent]] = defaultdict(list)
            for event in events:
                grouped[event.motion_id].append(event)
            events_by_motion = {
                motion_id: tuple(
                    sorted(
                        values,
                        key=lambda item: (
                            item.request_set_id,
                            item.start_frame,
                            item.track_index,
                        ),
                    )
                )
                for motion_id, values in grouped.items()
            }
            documents.append(
                MotlistIndexDocument(
                    source_path=source_path.replace("\\", "/"),
                    motlist_name=_text(document.get("motlistName")),
                    events_by_motion=events_by_motion,
                )
            )

        keys: set[str] = set()
        for document in documents:
            key = _motlist_key(document.source_path)
            if key in keys:
                raise ValueError(f"重复的 MOTLIST JSON sourcePath: {key}")
            keys.add(key)
        return cls(documents)

    def find(self, motlist_path: str) -> MotlistIndexDocument | None:
        return self._by_resource.get(_motlist_key(motlist_path))


class MotionTargetCatalog:
    def __init__(
        self,
        targets: dict[tuple[str, int], MotionTarget],
        unmatched_banks: list[MotbankEntryRecord],
    ) -> None:
        self.targets = targets
        self.unmatched_banks = unmatched_banks

    @classmethod
    def build(
        cls,
        banks: MotbankCatalog,
        motlists: MotlistJsonCatalog,
    ) -> "MotionTargetCatalog":
        targets: dict[tuple[str, int], MotionTarget] = {}
        unmatched: list[MotbankEntryRecord] = []
        for bank in banks.entries:
            document = motlists.find(bank.motlist_path)
            if document is None:
                unmatched.append(bank)
                continue
            for motion_id, events in document.events_by_motion.items():
                if not 0 <= motion_id <= 0xFFF or not 0 <= bank.bank_id <= 0xFFFFF:
                    continue
                motion_set_id = (bank.bank_id << 12) | motion_id
                key = (bank.scope, motion_set_id)
                target = MotionTarget(
                    scope=bank.scope,
                    motion_set_id=motion_set_id,
                    bank_id=bank.bank_id,
                    motion_id=motion_id,
                    motlist_source_path=document.source_path,
                    motlist_name=document.motlist_name,
                    events=events,
                )
                current = targets.get(key)
                if (
                    current is not None
                    and current.motlist_source_path.casefold()
                    != target.motlist_source_path.casefold()
                ):
                    raise ValueError(
                        f"MotionSet 冲突 {bank.scope}/0x{motion_set_id:x}: "
                        f"{current.motlist_source_path} 与 {target.motlist_source_path}"
                    )
                targets[key] = target
        return cls(targets, unmatched)

    def find(self, scope: str, motion_set_id: int) -> MotionTarget | None:
        return self.targets.get((scope, motion_set_id))


def normalize_motlist_resource_path(path: str) -> str:
    value = path.replace("\\", "/").lstrip("/")
    if value.casefold().startswith("natives/"):
        value = value[len("natives/") :]
    if value.casefold().startswith("stm/"):
        value = value[len("STM/") :]
    return _MOTLIST_SUFFIX.sub(".motlist", value)


def _motlist_key(path: str) -> str:
    return normalize_motlist_resource_path(path).casefold()


def _validate_banks(records: list[MotbankEntryRecord], source: Path) -> None:
    paths_by_key: dict[tuple[str, int], set[str]] = defaultdict(set)
    for record in records:
        paths_by_key[(record.scope, record.bank_id)].add(record.motlist_path.casefold())
    conflict = next(
        (key for key, values in paths_by_key.items() if len(values) > 1), None
    )
    if conflict is not None:
        raise ValueError(f"MOTBANK 条目冲突 {conflict[0]}/Bank {conflict[1]}: {source}")
    missing = [
        f"Wp{index:02d}"
        for index in range(14)
        if not any(record.scope == f"Wp{index:02d}" for record in records)
    ]
    if missing:
        raise ValueError(f"缺少武器 MOTBANK: {', '.join(missing)}")


def _is_player_motion_path(path: Path) -> bool:
    normalized = path.as_posix().casefold()
    return "/motion/player/" in normalized and ".motlist." in normalized


def _int(value: object) -> int:
    return (
        int(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else 0
    )


def _float(value: object) -> float:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else 0.0
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
