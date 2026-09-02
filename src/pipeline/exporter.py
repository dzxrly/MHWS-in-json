from pathlib import Path
from datetime import datetime, timezone
import os
import shutil

from config import (
    ACTION_MAP_PATH,
    ACTION_VALUE_WORKBOOK,
    AMULET_WORKBOOK,
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
from src.converters.action_values import (
    ActionValueCatalog,
    build_action_value_workbook,
    load_action_value_catalog,
)
from src.converters.amulet import (
    AmuletCatalog,
    build_amulet_workbook_sheets,
    export_amulet_pools,
    load_amulet_catalog,
)
from src.converters.bowgun import export_bowgun_workbooks
from src.converters.graphics import export_graphic_preset
from src.data.text_db import TextDB, TextSource, discover_language_ids
from src.data.user3 import load_user3_table
from src.excel.amulet import style_amulet_workbook
from src.excel.action_values import write_action_value_workbook
from src.excel.writer import write_workbook
from src.pipeline.package import zip_language_output, zip_processed_output, zip_source_output
from src.pipeline.transforms import transform_workbook
from src.utils.log import file_size, info

REJECTED_TEXT_PREFIX = "[#Rejected#]"


def export_all() -> list[Path]:
    info("Starting MHWS JSON to XLSX export")
    info(f"JSON root: {JSON_ROOT}")
    info(f"Natives directory: {NATIVES_DIR}")
    info(f"Static ActionMap: {ACTION_MAP_PATH}")
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
    amulet_catalog = load_amulet_catalog(_load_raw_relative)
    info("Loading weapon and ammo action-value requestSets")
    action_value_catalog = load_action_value_catalog(
        NATIVES_DIR,
        ACTION_MAP_PATH,
    )
    action_value_count = sum(len(rows) for rows in action_value_catalog.records.values())
    mapped_action_value_count = sum(
        request_set.key in action_value_catalog.bindings
        for rows in action_value_catalog.records.values()
        for request_set in rows
    )
    info(
        "Loaded action-value requestSets: "
        f"{action_value_count} eligible, {mapped_action_value_count} automatically mapped, "
        f"sources={action_value_catalog.mapping_source_counts}"
    )
    action_map_audit = action_value_catalog.action_map_audit
    if action_map_audit is not None:
        info(
            "Static ActionMap: "
            f"{action_map_audit.relations} relation(s), "
            f"{action_map_audit.named_relations} named relation(s), "
            f"{action_map_audit.unnamed_relations} unnamed relation(s), "
            f"{action_map_audit.bound_request_sets} mapped RS, "
            f"{action_map_audit.bindings} exact binding(s)"
        )

    archives: list[Path] = []
    for index, lang_id in enumerate(language_ids, start=1):
        language_code = _language_code(lang_id)
        language_dir = OUTPUT_DIR / language_code
        info(f"[{index}/{len(language_ids)}] Building language database: {language_code} ({lang_id})")
        text_db = text_source.build(lang_id)
        outputs = _export_language(
            language_dir,
            text_db,
            amulet_catalog,
            action_value_catalog,
        )
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
    _export_processed(processed_dir, text_source, language_ids, amulet_catalog)
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


def _export_language(
    output_dir: Path,
    text_db: TextDB,
    amulet_catalog: AmuletCatalog,
    action_value_catalog: ActionValueCatalog,
) -> list[Path]:
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

    outputs.append(_export_amulet_workbook(output_dir, text_db, amulet_catalog))
    outputs.append(
        _export_action_value_workbook(
            output_dir,
            text_db,
            action_value_catalog,
        )
    )
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


def _export_amulet_workbook(
    output_dir: Path,
    text_db: TextDB,
    amulet_catalog: AmuletCatalog,
) -> Path:
    info(f"  Workbook: {AMULET_WORKBOOK}")
    sheets = build_amulet_workbook_sheets(
        amulet_catalog,
        lambda guid: text_db.get(guid) or "",
    )
    path = write_workbook(
        output_dir / AMULET_WORKBOOK,
        sheets,
        MAX_COLUMN_WIDTH,
        style_amulet_workbook,
    )
    row_count = sum(len(rows) for rows in sheets.values())
    info(f"  Saved workbook: {path} ({file_size(path)}, {row_count} data row(s))")
    return path


def _export_action_value_workbook(
    output_dir: Path,
    text_db: TextDB,
    catalog: ActionValueCatalog,
) -> Path:
    info(f"  Workbook: {ACTION_VALUE_WORKBOOK}")
    data = build_action_value_workbook(
        catalog,
        lambda guid: text_db.get(guid) or "",
    )
    path = write_action_value_workbook(
        output_dir / ACTION_VALUE_WORKBOOK,
        data,
    )
    for sheet_name, audit in data.audits.items():
        info(
            f"    {sheet_name}: {audit.eligible_request_sets} eligible RS, "
            f"{audit.mapped_request_sets} mapped, {audit.unmapped_request_sets} unmapped, "
            f"{audit.displayed_rows} displayed row(s), {audit.action_groups} action group(s)"
        )
    row_count = sum(len(rows) for rows in data.sheets.values())
    info(f"  Saved workbook: {path} ({file_size(path)}, {row_count} data row(s))")
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


def _export_processed(
    output_dir: Path,
    text_source: TextSource,
    language_ids: list[int],
    amulet_catalog: AmuletCatalog,
) -> None:
    info("  Exporting amulet and skill pools")
    export_amulet_pools(
        output_dir,
        amulet_catalog,
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
