from __future__ import annotations

from pathlib import Path
import re
import json

from .models import PfbResourceDocument

PFB_FORMAT = "mhws_pfb_v1"
_VERSIONED_PFB = re.compile(r"\.pfb\.(\d+)(?:\.[^/]+)?$", re.IGNORECASE)
_ACTION_DATA_PREFIX = "GameDesign/Player/ActionData/"


class PfbResourceCatalog:
    def __init__(
        self,
        documents: list[PfbResourceDocument],
        missing_prefabs: tuple[str, ...] = (),
    ) -> None:
        self.documents = documents
        self.missing_prefabs = missing_prefabs
        self._by_prefab = {
            canonical_prefab_path(document.prefab_path).casefold(): document
            for document in documents
        }

    @classmethod
    def load_from_directory(
        cls,
        natives_directory: Path,
        prefab_paths: list[str],
    ) -> "PfbResourceCatalog":
        """Read exported resource tables, including referenced PFBs."""
        root = natives_directory.expanduser().resolve()
        requested = {
            canonical_prefab_path(path).casefold(): canonical_prefab_path(path)
            for path in prefab_paths
            if path.strip()
        }
        if not requested:
            return cls([])
        paths: dict[str, Path] = {}
        for path in sorted(root.rglob("*.pfb.*.json"), key=lambda p: str(p).casefold()):
            key = canonical_prefab_path(path.relative_to(root).as_posix()).casefold()
            if key in paths:
                raise ValueError(f"多个 JSON 对应同一 PFB {key}: {paths[key]}, {path}")
            paths[key] = path
        selected = {
            key for key in paths if key.startswith(_ACTION_DATA_PREFIX.casefold())
        } | set(requested)
        pending = list(sorted(selected))
        documents: dict[str, PfbResourceDocument] = {}
        visited: set[str] = set()
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            visited.add(key)
            path = paths.get(key)
            if path is None:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("_format") != PFB_FORMAT:
                raise ValueError(f"不是 {PFB_FORMAT} PFB JSON: {path}")
            resources = data.get("resources")
            if not isinstance(resources, list) or any(
                not isinstance(p, str) for p in resources
            ):
                raise ValueError(f"PFB JSON 缺少 resources 字符串表: {path}")
            relative = path.relative_to(root).as_posix().removesuffix(".json")
            # Keep the original resource table's path identity and ordering
            # semantics: raw PFB export used a case-insensitive sorted set.
            document = PfbResourceDocument(
                prefab_path=canonical_prefab_path(relative),
                archive_path="natives/" + relative,
                resources=tuple(
                    sorted(
                        {p.replace("\\", "/") for p in resources if p.strip()},
                        key=str.casefold,
                    )
                ),
            )
            documents[key] = document
            pending.extend(
                canonical_prefab_path(p).casefold()
                for p in document.resources
                if ".pfb" in p.casefold()
            )
        return cls(
            sorted(documents.values(), key=lambda d: d.prefab_path.casefold()),
            tuple(
                sorted(
                    (requested[k] for k in requested if k not in documents),
                    key=str.casefold,
                )
            ),
        )

    def find(self, prefab_path: str) -> PfbResourceDocument | None:
        return self._by_prefab.get(canonical_prefab_path(prefab_path).casefold())

    def find_rcol_resources(
        self,
        prefab_path: str,
    ) -> list[tuple[tuple[PfbResourceDocument, ...], str]]:
        root = self.find(prefab_path)
        if root is None:
            return []
        output: dict[
            tuple[str, tuple[str, ...]],
            tuple[tuple[PfbResourceDocument, ...], str],
        ] = {}
        pending = [(root, (root,))]
        while pending:
            document, chain = pending.pop()
            chain_keys = {
                canonical_prefab_path(item.prefab_path).casefold() for item in chain
            }
            for resource in document.resources:
                folded = resource.casefold()
                if ".rcol" in folded:
                    key = (
                        folded,
                        tuple(item.archive_path.casefold() for item in chain),
                    )
                    output.setdefault(key, (chain, resource))
                    continue
                if ".pfb" not in folded:
                    continue
                child = self.find(resource)
                child_key = (
                    canonical_prefab_path(child.prefab_path).casefold()
                    if child is not None
                    else ""
                )
                if child is not None and child_key not in chain_keys:
                    pending.append((child, (*chain, child)))
        return sorted(
            output.values(),
            key=lambda item: (
                item[1].casefold(),
                tuple(document.archive_path.casefold() for document in item[0]),
            ),
        )


def canonical_prefab_path(path: str) -> str:
    value = path.replace("\\", "/").lstrip("/")
    if value.casefold().startswith("natives/stm/"):
        value = value[len("natives/STM/") :]
    elif value.casefold().startswith("stm/"):
        value = value[len("STM/") :]
    return _VERSIONED_PFB.sub(".pfb", value)
