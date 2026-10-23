"""The one place that maps a game version to its EXE and il2cpp dump.

``sdk/game_versions.json`` holds ``{version: {exeSha256, metadataSha256}}``.
Files committed by the SDKs store a source as ``{"gameVersion": "<version>"}``
only; ``expand`` restores the full profile when they are read and ``compact``
reduces it when they are written. Local research caches in ``.agents`` keep
full profiles, because they may come from any build.
"""

import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent / "game_versions.json"
PROFILE_KEYS = frozenset({"gameVersion", "exeSha256", "metadataSha256"})


def registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def profile(version):
    """Full profile of a registered version."""
    entries = registry()
    if version not in entries:
        raise ValueError(f"游戏版本 {version} 未在 {REGISTRY_PATH.name} 中登记")
    return dict(gameVersion=version, **entries[version])


def identify(exe_sha256, metadata_sha256):
    """Registered version whose EXE and il2cpp digests both match."""
    for version, entry in registry().items():
        if (
            entry["exeSha256"] == exe_sha256
            and entry["metadataSha256"] == metadata_sha256
        ):
            return version
    raise ValueError(
        f"EXE 与 il2cpp 不属于 {REGISTRY_PATH.name} 中登记的任何版本；"
        "新版本先运行 sdk.enemy_logic_exporter resolve-symbols 登记"
    )


def register(full_profile):
    """Add or confirm a version entry (resolve-symbols on a new build)."""
    entries = registry()
    version = full_profile["gameVersion"]
    entry = {k: full_profile[k] for k in ("exeSha256", "metadataSha256")}
    if entries.get(version, entry) != entry:
        raise ValueError(f"游戏版本 {version} 已登记为其他 EXE 或 il2cpp，不能覆盖")
    entries[version] = entry
    REGISTRY_PATH.write_text(
        json.dumps(dict(sorted(entries.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def compact(value):
    """Replace every full profile by its registered version reference."""
    if isinstance(value, dict):
        if set(value) == PROFILE_KEYS:
            if profile(value["gameVersion"]) != value:
                raise ValueError(f"来源 {value['gameVersion']} 的摘要与登记不一致")
            return {"gameVersion": value["gameVersion"]}
        return {k: compact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def expand(value):
    """Restore full profiles from ``{"gameVersion": ...}`` references."""
    if isinstance(value, dict):
        if set(value) == {"gameVersion"}:
            return profile(value["gameVersion"])
        return {k: expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand(v) for v in value]
    return value


def read(path):
    return expand(json.loads(Path(path).read_text(encoding="utf-8")))
