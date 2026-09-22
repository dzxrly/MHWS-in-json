"""Coordinate preparation, DATABASE, PROCESSED_DATA, packaging and publication."""

from datetime import datetime, timezone
import os
from pathlib import Path
import re

from config import (
    ACTION_MAP_PATH, BASE_DIR, ENUMS_PATH, JSON_ROOT, LANGUAGE_IDS, NATIVES_DIR, OUTPUT_DIR,
    PROCESSED_DIR_NAME, PROCESSED_ZIP_PREFIX, SOURCE_ZIP_PREFIX, VERSION, VERSION_ENV_VAR, ZIP_PREFIX,
)
from src.database.exporter import WORKBOOK_NAMES, export_language, prepare_database
from src.processed_data.exporter import OUTPUT_NAMES, PoolNames, export_processed
from src.pipeline.package import zip_language_output, zip_processed_output, zip_source_output
from src.pipeline.publish import ExportTransaction
from src.pipeline.validation import validate_outputs, write_manifest
from src.shared.amulets import load_amulet_catalog
from src.shared.languages import language_code
from src.shared.log import info
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource
from src.shared.timing import Timings


def export_all() -> list[Path]:
    if not NATIVES_DIR.is_dir():
        raise FileNotFoundError(f"Natives directory not found: {NATIVES_DIR}")
    version = _version()
    timings = Timings()
    repository = SourceRepository(NATIVES_DIR)
    with timings.measure("prepare/text"):
        text_source = TextSource.from_natives(NATIVES_DIR)
        if not text_source.guid_contents:
            raise ValueError(f"No message GUIDs found under {NATIVES_DIR}")
    language_ids = list(LANGUAGE_IDS or text_source.language_ids)
    if len(language_ids) != len(set(language_ids)) or any(language_id < 0 for language_id in language_ids):
        raise ValueError(f"Invalid language selection: {language_ids}")
    info(f"Release {version}: {len(language_ids)} languages, {text_source.file_count} message files")
    with timings.measure("prepare/database"):
        amulets = load_amulet_catalog(repository.table)
        database = prepare_database(repository, amulets, ENUMS_PATH, ACTION_MAP_PATH)
    names = PoolNames(amulets)

    with ExportTransaction(OUTPUT_DIR, BASE_DIR) as transaction:
        stage = transaction.stage
        archives: dict[str, Path | None] = {}
        for index, language_id in enumerate(language_ids, start=1):
            code = language_code(language_id)
            directory = stage / code
            info(f"[{index}/{len(language_ids)}] Building language database: {code}")
            with timings.measure(f"{code}/text"):
                text_db = text_source.build(language_id)
                names.add_language(language_id, text_db)
            export_language(directory, database, text_source, text_db, language_id, timings)
            with timings.measure(f"{code}/zip"):
                archive = zip_language_output(directory, stage, code, version, ZIP_PREFIX)
            archives[archive.name] = directory

        processed_dir = stage / PROCESSED_DIR_NAME
        export_processed(processed_dir, repository, text_source, amulets, names, timings)
        with timings.measure("package/processed"):
            archive = zip_processed_output(processed_dir, stage, version, PROCESSED_ZIP_PREFIX)
            archives[archive.name] = processed_dir
        with timings.measure("package/source"):
            archive = zip_source_output(JSON_ROOT, stage, version, SOURCE_ZIP_PREFIX)
            archives[archive.name] = None
        expected = {f"{language_code(language_id)}/{name}"
                    for language_id in language_ids for name in WORKBOOK_NAMES}
        expected.update(f"{PROCESSED_DIR_NAME}/{name}" for name in OUTPUT_NAMES)
        with timings.measure("validate"):
            records = validate_outputs(stage, expected, archives)
        write_manifest(stage, version=version, languages=language_ids, records=records,
                       timings=timings.seconds, source_tables=repository.loaded_paths, action_map_path=ACTION_MAP_PATH)
        transaction.publish()
    info(f"Export complete: {len(archives)} archives, {len(repository.loaded_paths)} normalized source tables")
    return [OUTPUT_DIR / name for name in archives]


def _version() -> str:
    version = VERSION or os.environ.get(VERSION_ENV_VAR)
    if not version:
        date = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        version = f"{date}-{os.environ.get('GITHUB_SHA', 'local')[:7]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version):
        raise ValueError(f"Invalid release version: {version!r}")
    return version
