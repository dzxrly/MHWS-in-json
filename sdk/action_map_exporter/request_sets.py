from __future__ import annotations

from collections import defaultdict
import json
import hashlib
from pathlib import Path
import re

from .models import RequestSetIdentity

_ELIGIBLE_TYPES = {
    "app.col_user_data.AttackParamPl",
    "app.col_user_data.AttackParamPlShell",
}
_RCOL_SUFFIX = re.compile(r"\.rcol(?:\.\d+)?$", re.IGNORECASE)


class RequestSetCatalog:
    def __init__(self, records: list[RequestSetIdentity]) -> None:
        self.records = records
        self._by_coordinate: dict[tuple[str, int], list[RequestSetIdentity]] = (
            defaultdict(list)
        )
        self._by_key_hash: dict[tuple[str, int], list[RequestSetIdentity]] = (
            defaultdict(list)
        )
        self._by_resource: dict[tuple[str, str, int], list[RequestSetIdentity]] = (
            defaultdict(list)
        )
        self._by_rcol: dict[tuple[str, str], list[RequestSetIdentity]] = defaultdict(
            list
        )
        for record in records:
            self._by_coordinate[(record.scope, record.request_set_id)].append(record)
            if record.key_hash != 0:
                self._by_key_hash[(record.scope, record.key_hash)].append(record)
            self._by_resource[
                (record.scope, canonical_rcol_path(record.rcol), record.request_set_id)
            ].append(record)
            self._by_rcol[(record.scope, canonical_rcol_path(record.rcol))].append(
                record
            )

    @classmethod
    def load(cls, natives_directory: Path) -> "RequestSetCatalog":
        action_data = natives_directory / "STM" / "GameDesign" / "Player" / "ActionData"
        records: list[RequestSetIdentity] = []
        for scope in [*(f"Wp{index:02d}" for index in range(14)), "Ammo"]:
            source_scope = "WpGunCommon" if scope == "Ammo" else scope
            source_directory = action_data / source_scope
            if not source_directory.is_dir():
                continue
            paths = sorted(
                source_directory.rglob("*.rcol.*.json"),
                key=lambda path: str(path).casefold(),
            )
            for path in paths:
                document = json.loads(path.read_text(encoding="utf-8"))
                sets = (
                    document.get("requestSets") if isinstance(document, dict) else None
                )
                if not isinstance(sets, list):
                    continue
                relative = path.relative_to(action_data).as_posix()
                for ordinal, request_set in enumerate(sets):
                    if not isinstance(request_set, dict):
                        continue
                    user_data_type = _eligible_user_data_type(request_set)
                    if user_data_type is None:
                        continue
                    records.append(
                        RequestSetIdentity(
                            scope=scope,
                            rcol=relative,
                            request_set_id=_integer(request_set.get("requestSetID")),
                            key_hash=_integer(request_set.get("keyHash")),
                            source_request_set_ordinal=ordinal,
                            user_data_type=user_data_type,
                            resource_paths=tuple(_collect_resource_paths(request_set)),
                            attack_payload_hash=_attack_payload_hash(request_set),
                            shape_types=_shape_types(document, request_set),
                        )
                    )
        records.sort(
            key=lambda record: (
                record.scope,
                record.rcol.casefold(),
                record.request_set_id,
                record.key_hash,
                record.source_request_set_ordinal,
            )
        )
        return cls(records)

    def find(self, scope: str, request_set_id: int) -> list[RequestSetIdentity]:
        return self._by_coordinate.get((scope, request_set_id), [])

    def find_by_key_hash(self, scope: str, key_hash: int) -> list[RequestSetIdentity]:
        return self._by_key_hash.get((scope, key_hash), [])

    def find_by_resource(
        self,
        scope: str,
        rcol_resource_path: str,
        request_set_id: int,
    ) -> list[RequestSetIdentity]:
        return self._by_resource.get(
            (scope, canonical_rcol_path(rcol_resource_path), request_set_id), []
        )

    def find_in_resource(
        self,
        scope: str,
        rcol_resource_path: str,
    ) -> list[RequestSetIdentity]:
        return self._by_rcol.get((scope, canonical_rcol_path(rcol_resource_path)), [])


def canonical_rcol_path(path: str) -> str:
    value = path.replace("\\", "/").lstrip("/")
    prefix = "GameDesign/Player/ActionData/"
    index = value.casefold().find(prefix.casefold())
    if index >= 0:
        value = value[index + len(prefix) :]
    if value.casefold().endswith(".json"):
        value = value[: -len(".json")]
    return _RCOL_SUFFIX.sub(".rcol", value).casefold()


def _eligible_user_data_type(request_set: dict[str, object]) -> str | None:
    user_data = request_set.get("userData")
    if not isinstance(user_data, dict):
        return None
    return next((name for name in user_data if name in _ELIGIBLE_TYPES), None)


def _collect_resource_paths(element: object) -> list[str]:
    paths: dict[str, str] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str):
            normalized = value.replace("\\", "/").strip()
            if "/" in normalized and normalized.casefold().endswith(
                (".user", ".pfb", ".rcol")
            ):
                paths.setdefault(normalized.casefold(), normalized)

    visit(element)
    return sorted(paths.values(), key=str.casefold)


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _attack_payload_hash(request_set: dict[str, object]) -> str:
    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {
                k: normalize(v)
                for k, v in value.items()
                if k not in {"RequestSetIndex", "ref_instance_id"}
            }
        if isinstance(value, list):
            return [normalize(v) for v in value]
        return value

    payload = request_set.get("userData")
    if not isinstance(payload, dict) or not any(
        isinstance(v, dict) and v for v in payload.values()
    ):
        return ""
    text = json.dumps(
        normalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _shape_types(
    document: dict[str, object], request_set: dict[str, object]
) -> tuple[str, ...]:
    groups = document.get("groupInfos")
    index = request_set.get("groupIndex")
    if (
        not isinstance(groups, list)
        or not isinstance(index, int)
        or isinstance(index, bool)
        or not 0 <= index < len(groups)
    ):
        return ()
    group = groups[index]
    if not isinstance(group, dict) or not isinstance(group.get("groupShapes"), list):
        return ()
    return tuple(
        sorted(
            {
                str(shape["shapeType"])
                for shape in group["groupShapes"]
                if isinstance(shape, dict) and shape.get("shapeType")
            }
        )
    )
