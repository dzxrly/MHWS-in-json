from pathlib import Path
from datetime import datetime, timezone
import os
import shutil

from config import (
    LANGUAGE_IDS,
    LANGUAGE_NAMES,
    MAX_COLUMN_WIDTH,
    NATIVES_DIR,
    OUTPUT_DIR,
    JSON_ROOT,
    PROCESSED_DIR_NAME,
    PROCESSED_ZIP_PREFIX,
    VERSION,
    VERSION_ENV_VAR,
    WORKBOOKS,
    ZIP_PREFIX,
)
from src.converters.amulet import export_amulet_pools
from src.converters.graphics import export_graphic_preset
from src.data.text_db import TextDB, TextSource, discover_language_ids
from src.data.user3 import load_user3_table
from src.excel.writer import write_workbook
from src.pipeline.package import zip_language_output, zip_processed_output
from src.pipeline.transforms import transform_workbook


def export_all() -> list[Path]:
    if not NATIVES_DIR.exists():
        raise FileNotFoundError(f"Natives directory not found: {NATIVES_DIR}")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    version = _version()
    language_ids = LANGUAGE_IDS or discover_language_ids(NATIVES_DIR)
    print(f"Loading text database: {NATIVES_DIR}")
    text_source = TextSource.from_natives(NATIVES_DIR)

    archives: list[Path] = []
    for lang_id in language_ids:
        language = _language_name(lang_id)
        language_dir = OUTPUT_DIR / language
        text_db = text_source.build(lang_id)
        print(f"Exporting {language} ({lang_id})")
        _export_language(language_dir, text_db)
        archive = zip_language_output(
            language_dir,
            OUTPUT_DIR,
            language,
            version,
            ZIP_PREFIX,
            JSON_ROOT,
        )
        archives.append(archive)
        print(f"Saved archive: {archive}")

    processed_dir = OUTPUT_DIR / PROCESSED_DIR_NAME
    print("Exporting processed data")
    _export_processed(processed_dir, text_source, language_ids)
    processed_archive = zip_processed_output(
        processed_dir,
        OUTPUT_DIR,
        version,
        PROCESSED_ZIP_PREFIX,
    )
    archives.append(processed_archive)
    print(f"Saved archive: {processed_archive}")

    return archives


def _export_language(output_dir: Path, text_db: TextDB) -> list[Path]:
    outputs: list[Path] = []
    for workbook_name, specs in WORKBOOKS.items():
        sheets = {}
        for sheet_name, relative_path in specs:
            frame = _load_relative(relative_path, text_db)
            if frame is not None:
                sheets[sheet_name] = frame
        if sheets:
            sheets = transform_workbook(workbook_name, sheets, lambda p: _load_relative(p, text_db))
            outputs.append(write_workbook(output_dir / workbook_name, sheets, MAX_COLUMN_WIDTH))

    return outputs


def _export_processed(output_dir: Path, text_source: TextSource, language_ids: list[int]) -> None:
    export_amulet_pools(
        output_dir,
        _load_raw_relative,
        _name_resolver(text_source, language_ids),
    )
    export_graphic_preset(output_dir, NATIVES_DIR)


def _load_relative(relative_path: str, text_db: TextDB):
    source = NATIVES_DIR / relative_path
    if not source.exists():
        print(f"Skip missing: {source}")
        return None
    return load_user3_table(source, text_db)


def _load_raw_relative(relative_path: str):
    source = NATIVES_DIR / relative_path
    if not source.exists():
        print(f"Skip missing: {source}")
        return None
    return load_user3_table(source)


def _name_resolver(text_source: TextSource, language_ids: list[int]):
    cache: dict[int, TextDB] = {}

    def resolve(guid: str | None) -> list[dict]:
        if not guid:
            return []
        names = []
        for lang_id in language_ids:
            if lang_id not in cache:
                cache[lang_id] = text_source.build(lang_id)
            names.append(
                {
                    "languageCode": _language_name(lang_id),
                    "languageIndexInGame": str(lang_id),
                    "name": cache[lang_id].get(guid) or "",
                }
            )
        return names

    return resolve


def _language_name(lang_id: int) -> str:
    return LANGUAGE_NAMES.get(lang_id, f"lang-{lang_id:02d}")


def _version() -> str:
    if VERSION:
        return VERSION
    env_version = os.environ.get(VERSION_ENV_VAR)
    if env_version:
        return env_version
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    sha = os.environ.get("GITHUB_SHA", "local")[:7]
    return f"{date}-{sha}"
