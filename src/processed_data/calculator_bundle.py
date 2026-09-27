"""Build, validate and synchronize the calculator's two data contracts together."""

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from config import ACTION_MAP_PATH, NATIVES_DIR, OUTPUT_DIR
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource
from src.processed_data.damage_calculator.exporter import build_catalog as build_damage
from src.processed_data.skill_effects.exporter import build_catalog as build_skills


def encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


@contextmanager
def preserve_outputs(paths: list[Path], workspace: Path):
    """Restore the complete bundle after a write/generator failure, including Ctrl+C.

    The two projects are not one filesystem transaction. Keep disk backups for
    manual recovery if rollback itself fails. Preserve destination ACLs by writing
    existing files in place instead of moving private temporary files over them.
    """
    runs = workspace.resolve() / ".agents" / "calculator-bundles"
    runs.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=runs))
    previous = {}
    for index, path in enumerate(dict.fromkeys(paths)):
        backup = stage / str(index)
        if path.exists():
            backup.write_bytes(path.read_bytes())
            previous[path] = backup
        else:
            previous[path] = None
    try:
        yield stage
    except BaseException as error:
        failures = []
        for path, backup in previous.items():
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(backup.read_bytes())
            except OSError as rollback_error:
                failures.append(f"{path}: {rollback_error}")
        if failures:
            error.add_note(f"Restore bundle backups manually from {stage}: {'; '.join(failures)}")
            raise
        raise
    finally:
        # Keep backups after any failure for diagnostics; only remove successful runs.
        if sys.exc_info()[0] is None:
            for path in stage.iterdir():
                path.unlink()
            stage.rmdir()


def synchronize(files: dict[str, bytes], roots: tuple[Path, ...], workspace: Path,
                trace_tools: Path | None = None) -> None:
    paths = [root / name for root in roots for name in files]
    if trace_tools:
        paths.append(trace_tools / "mhws_element_trace.lua")
    with preserve_outputs(paths, workspace):
        for path, content in ((root / name, content)
                              for root in roots for name, content in files.items()):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if trace_tools:
            for name in ("build_mhws_trace_actions.py", "build_mhws_trace_runtime.py"):
                subprocess.run([sys.executable, "-B", "-X", "utf8", str(trace_tools / name)], check=True)
            validate_trace(files, trace_tools)


def validate_trace(files: dict[str, bytes], directory: Path) -> None:
    script = (directory / "mhws_element_trace.lua").read_text(encoding="utf-8")
    manifest = json.loads(files["calculator_manifest.json"])
    for identity in (manifest["exports"]["damage_calculator.zh-Hans.json"]["sha256"],
                     manifest["actionMapSha256"], manifest["exports"]["skill_effects.zh-Hans.json"]["sha256"]):
        if identity not in script:
            raise ValueError("Trace script has a stale data identity")


def build_bundle() -> dict[str, bytes]:
    repository = SourceRepository(NATIVES_DIR)
    text = TextSource.from_natives(NATIVES_DIR)
    damage = build_damage(NATIVES_DIR, repository, text)
    skills = build_skills(NATIVES_DIR, repository, text)
    if damage["sourceContract"] != skills["sourceContract"]:
        raise ValueError("Calculator contracts have different sources")
    files = {"damage_calculator.zh-Hans.json": encode(damage), "skill_effects.zh-Hans.json": encode(skills)}
    sources = set(repository.loaded_paths) | set(damage["sourceContract"]["sourceHashes"])
    sources.update(monster["sourceFile"] for monster in damage["monsters"])
    sources.add(damage["gunlance"]["source"])
    for profile in damage["hitProfiles"]:
        sources.add("STM/GameDesign/Player/ActionData/" + profile["rcol"])
        for field in ("physicalCurve", "statusCurve"):
            if profile["multiHit"][field]:
                sources.add("STM/" + profile["multiHit"][field] + ".3.json")
        if profile.get("lanceCharge"):
            sources.add(profile["lanceCharge"]["source"])
        if profile.get("switchaxe"):
            sources.add(profile["switchaxe"]["source"])
    for action in damage["actions"]:
        if action.get("gunlance"):
            sources.add(action["gunlance"]["source"])
        if action.get("shell"):
            sources.add(action["shell"]["source"])
        if action.get("bow"):
            sources.update(action["bow"]["sources"])
    manifest = {
        "schemaVersion": 1,
        "exports": {name: {"sha256": hashlib.sha256(content).hexdigest(),
                            "schemaVersion": json.loads(content)["schemaVersion"]}
                    for name, content in files.items()},
        "sourceContract": damage["sourceContract"]["id"],
        "actionMapSha256": hashlib.sha256(ACTION_MAP_PATH.read_bytes()).hexdigest(),
        "referencedSources": {name: hashlib.sha256((NATIVES_DIR / name).read_bytes()).hexdigest()
                              for name in sorted(sources)},
    }
    files["calculator_manifest.json"] = encode(manifest)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True, help="Calculator project root")
    parser.add_argument("--check", action="store_true", help="Verify reproducibility without writing")
    parser.add_argument("--trace-tools", type=Path, help="Directory containing the trace catalog generators")
    args = parser.parse_args()
    files = build_bundle()  # Both catalogs validate before any existing file changes.
    roots = (OUTPUT_DIR / "processed_data", args.consumer.resolve() / "src/data")
    directory = args.trace_tools.resolve() if args.trace_tools else None
    if args.check:
        for root in roots:
            for name, content in files.items():
                path = root / name
                if not path.exists() or path.read_bytes() != content:
                    raise ValueError(f"Stale calculator output: {path}")
        if directory:
            validate_trace(files, directory)
    else:
        synchronize(files, roots, args.consumer.resolve(), directory)
    print("Calculator bundle verified" if args.check else "Calculator bundle synchronized")


if __name__ == "__main__":
    main()
