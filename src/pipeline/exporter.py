from pathlib import Path
from datetime import datetime, timezone
import os
import shutil

from config import (
    FULL_TEXT_MAX_COLUMN_WIDTH,
    FULL_TEXT_WORKBOOK,
    JSON_ROOT,
    LANGUAGE_IDS,
    LANGUAGES,
    MAX_COLUMN_WIDTH,
    NATIVES_DIR,
    OUTPUT_DIR,
    PROCESSED_DIR_NAME,
    PROCESSED_ZIP_PREFIX,
    SOURCE_ZIP_PREFIX,
    VERSION,
    VERSION_ENV_VAR,
    WORKBOOKS,
    ZIP_PREFIX,
)
from src.converters.amulet import export_amulet_pools
from src.converters.bowgun import export_bowgun_workbooks
from src.converters.graphics import export_graphic_preset
from src.data.text_db import TextDB, TextSource, discover_language_ids
from src.data.user3 import load_user3_table
from src.excel.writer import write_workbook
from src.pipeline.package import zip_language_output, zip_processed_output, zip_source_output
from src.pipeline.transforms import transform_workbook
from src.utils.log import file_size, info

REJECTED_TEXT_PREFIX = "[#Rejected#]"


def export_all() -> list[Path]:
    info("Starting MHWS JSON to XLSX export")
    info(f"JSON root: {JSON_ROOT}")
    info(f"Natives directory: {NATIVES_DIR}")
    info(f"Output directory: {OUTPUT_DIR}")
    if not NATIVES_DIR.exists():
        raise FileNotFoundError(f"Natives directory not found: {NATIVES_DIR}")

    if OUTPUT_DIR.exists():
        info(f"Cleaning output directory: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    version = _version()
    info(f"Release version: {version}")
    info("Discovering supported languages")
    language_ids = LANGUAGE_IDS or discover_language_ids(NATIVES_DIR)
    info(f"Languages to export ({len(language_ids)}): {_language_list(language_ids)}")
    info(f"Loading text database: {NATIVES_DIR}")
    text_source = TextSource.from_natives(NATIVES_DIR)
    info(f"Loaded text database: {text_source.file_count} message file(s), {len(text_source.entries)} entries")

    archives: list[Path] = []
    for index, lang_id in enumerate(language_ids, start=1):
        language_code = _language_code(lang_id)
        language_dir = OUTPUT_DIR / language_code
        info(f"[{index}/{len(language_ids)}] Building language database: {language_code} ({lang_id})")
        text_db = text_source.build(lang_id)
        outputs = _export_language(language_dir, text_db)
        info(f"Generated {len(outputs)} workbook(s) for {language_code}")
        archive = zip_language_output(
            language_dir,
            OUTPUT_DIR,
            language_code,
            version,
            ZIP_PREFIX,
        )
        archives.append(archive)

    processed_dir = OUTPUT_DIR / PROCESSED_DIR_NAME
    info("Exporting processed data")
    _export_processed(processed_dir, text_source, language_ids)
    processed_archive = zip_processed_output(
        processed_dir,
        OUTPUT_DIR,
        version,
        PROCESSED_ZIP_PREFIX,
    )
    archives.append(processed_archive)

    source_archive = zip_source_output(
        JSON_ROOT,
        OUTPUT_DIR,
        version,
        SOURCE_ZIP_PREFIX,
    )
    archives.append(source_archive)
    info(f"Export complete: {len(archives)} archive(s)")

    return archives


def _export_language(output_dir: Path, text_db: TextDB) -> list[Path]:
    outputs = [_export_full_text(output_dir, text_db)]
    for workbook_name, specs in WORKBOOKS.items():
        info(f"  Workbook: {workbook_name}")
        sheets = {}
        for sheet_name, relative_path in specs:
            frame = _load_relative(relative_path, text_db, f"{workbook_name}/{sheet_name}")
            if frame is not None:
                sheets[sheet_name] = frame
        if sheets:
            info(f"  Transforming workbook: {workbook_name}")
            sheets = transform_workbook(
                workbook_name,
                sheets,
                lambda p: _load_relative(p, text_db, f"{workbook_name}/support"),
            )
            path = write_workbook(output_dir / workbook_name, sheets, MAX_COLUMN_WIDTH)
            outputs.append(path)
            info(f"  Saved workbook: {path} ({file_size(path)})")
        else:
            info(f"  Skipped workbook without available sheets: {workbook_name}")

    return outputs


def _export_full_text(output_dir: Path, text_db: TextDB) -> Path:
    info(f"  Workbook: {FULL_TEXT_WORKBOOK}")
    rows = _full_text_rows(text_db)
    path = write_workbook(
        output_dir / FULL_TEXT_WORKBOOK,
        {"FullText": rows},
        FULL_TEXT_MAX_COLUMN_WIDTH,
    )
    info(f"  Saved workbook: {path} ({file_size(path)}, {len(rows)} text row(s))")
    return path


def _full_text_rows(text_db: TextDB) -> list[dict[str, str]]:
    available = []
    rejected = []
    empty = []
    for guid, text in text_db.guid_text.items():
        if text_db.is_rejected(guid):
            display_text = f"{REJECTED_TEXT_PREFIX} {text}" if text.strip() else REJECTED_TEXT_PREFIX
            rejected.append({"guid": guid, "text": display_text})
        elif not text.strip():
            empty.append({"guid": guid, "text": text})
        else:
            available.append({"guid": guid, "text": text})
    return available + rejected + empty


def _export_processed(output_dir: Path, text_source: TextSource, language_ids: list[int]) -> None:
    info("  Exporting amulet and skill pools")
    export_amulet_pools(
        output_dir,
        _load_raw_relative,
        _name_resolver(text_source, language_ids),
    )
    info("  Exporting graphic preset workbook")
    export_graphic_preset(output_dir, NATIVES_DIR)
    info("  Exporting bowgun workbooks")
    export_bowgun_workbooks(output_dir, NATIVES_DIR, text_source)


def _load_relative(relative_path: str, text_db: TextDB, label: str | None = None):
    source = NATIVES_DIR / relative_path
    if not source.exists():
        info(f"    Skip missing: {source}")
        return None
    info(f"    Loading {label or relative_path}: {relative_path}")
    frame = load_user3_table(source, text_db)
    info(f"    Loaded {label or relative_path}: {_table_shape(frame)}")
    return frame


def _load_raw_relative(relative_path: str):
    source = NATIVES_DIR / relative_path
    if not source.exists():
        info(f"    Skip missing: {source}")
        return None
    info(f"    Loading raw table: {relative_path}")
    frame = load_user3_table(source)
    info(f"    Loaded raw table: {_table_shape(frame)}")
    return frame


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
                    "languageCode": _language_code(lang_id),
                    "languageIndexInGame": str(lang_id),
                    "name": cache[lang_id].get(guid) or "",
                }
            )
        return names

    return resolve


def _language_code(lang_id: int) -> str:
    language = LANGUAGES.get(lang_id)
    return language.code if language else f"lang-{lang_id:02d}"


def _language_list(language_ids: list[int]) -> str:
    return ", ".join(f"{_language_code(lang_id)}({lang_id})" for lang_id in language_ids)


def _table_shape(rows: list[dict]) -> str:
    columns = {key for row in rows for key in row}
    return f"{len(rows)} row(s), {len(columns)} column(s)"


def _version() -> str:
    if VERSION:
        return VERSION
    env_version = os.environ.get(VERSION_ENV_VAR)
    if env_version:
        return env_version
    date = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sha = os.environ.get("GITHUB_SHA", "local")[:7]
    return f"{date}-{sha}"
