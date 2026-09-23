"""Validate the complete product set and record an auditable export manifest."""

import hashlib
import json
from pathlib import Path
import platform
from zipfile import ZipFile
from xml.etree import ElementTree

import openpyxl
from src.processed_data.damage_calculator.exporter import OUTPUT_NAME as DAMAGE_OUTPUT_NAME, validate_catalog
from src.processed_data.skill_effects.exporter import OUTPUT_NAME as SKILL_EFFECTS_OUTPUT_NAME, validate_catalog as validate_skill_effects


def validate_outputs(stage: Path, expected_files: set[str], archives: dict[str, Path | None]) -> list[dict]:
    actual = {path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()}
    expected = expected_files | set(archives)
    if actual != expected:
        raise ValueError(f"Output manifest mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    records = []
    for relative in sorted(expected_files):
        path = stage / relative
        if not path.stat().st_size:
            raise ValueError(f"Empty export: {relative}")
        if path.suffix == ".xlsx":
            _validate_workbook(path)
        elif path.suffix == ".json":
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if path.name == DAMAGE_OUTPUT_NAME:
                validate_catalog(payload)
            elif path.name == SKILL_EFFECTS_OUTPUT_NAME:
                validate_skill_effects(payload)
        records.append({"path": relative, "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    for name, source in archives.items():
        with ZipFile(stage / name) as archive:
            members = archive.infolist()
            member_names = [member.filename for member in members]
            if not members or len(member_names) != len(set(member_names)):
                raise ValueError(f"Empty or duplicate ZIP entries: {name}")
            if source is not None:
                expected_members = {path.relative_to(source).as_posix(): path.stat().st_size
                                    for path in source.rglob("*") if path.is_file()}
                actual_members = {member.filename: member.file_size for member in members}
                if actual_members != expected_members:
                    raise ValueError(f"Archive contents do not match the export: {name}")
                bad = archive.testzip()
                if bad:
                    raise ValueError(f"Invalid archive member in {name}: {bad}")
        records.append({"path": name, "bytes": (stage / name).stat().st_size, "entries": len(members)})
    return records


def _validate_workbook(path: Path) -> None:
    with ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Invalid workbook member in {path}: {bad}")
        document = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        names = [sheet.attrib["name"] for sheet in document.findall(f"{namespace}sheets/{namespace}sheet")]
        if not names or len(names) != len(set(names)):
            raise ValueError(f"Invalid workbook sheets: {path}")


def write_manifest(stage: Path, *, version: str, languages: list[int], records: list[dict],
                   timings: dict[str, float], source_tables: tuple[str, ...], action_map_path: Path) -> None:
    manifest = {
        "schemaVersion": 1, "version": version, "languageIds": languages,
        "runtime": {"python": platform.python_version(), "openpyxl": openpyxl.__version__},
        "actionMapSha256": hashlib.sha256(action_map_path.read_bytes()).hexdigest(),
        "normalizedSourceTables": list(source_tables), "timingsSeconds": timings, "outputs": records,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
