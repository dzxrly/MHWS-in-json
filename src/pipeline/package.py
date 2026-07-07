from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

from src.utils.log import file_size, format_size, info


def zip_language_output(
    language_dir: Path,
    output_dir: Path,
    language_name: str,
    version: str,
    prefix: str,
) -> Path:
    archive = output_dir / f"{prefix}_{language_name}_{version}.zip"
    info(f"Creating language archive: {archive.name}")
    with _zip(archive) as zf:
        _write_tree(zf, language_dir)
    info(f"Created language archive: {archive.name} ({file_size(archive)})")
    return archive


def zip_processed_output(
    processed_dir: Path,
    output_dir: Path,
    version: str,
    prefix: str,
) -> Path:
    archive = output_dir / f"{prefix}_{version}.zip"
    info(f"Creating processed archive: {archive.name}")
    with _zip(archive) as zf:
        _write_tree(zf, processed_dir)
    info(f"Created processed archive: {archive.name} ({file_size(archive)})")
    return archive


def zip_source_output(
    json_root: Path,
    output_dir: Path,
    version: str,
    prefix: str,
) -> Path:
    archive = output_dir / f"{prefix}_{version}.zip"
    info(f"Creating source archive: {archive.name}")
    with _zip(archive) as zf:
        _write_tree(zf, json_root, json_root.name)
    info(f"Created source archive: {archive.name} ({file_size(archive)})")
    return archive


def _zip(path: Path) -> ZipFile:
    return ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9)


def _write_tree(zf: ZipFile, root: Path, prefix: str = "") -> None:
    files = [path for path in sorted(root.rglob("*")) if path.is_file()]
    info(f"  Adding {len(files)} file(s) from {root}")
    for index, path in enumerate(files, start=1):
        size = path.stat().st_size
        if size >= 50 * 1024 * 1024:
            info(f"  Adding large file {index}/{len(files)}: {path.name} ({format_size(size)})")
        zf.write(path, _zip_name(root, path, prefix))
        if index == len(files) or index % 500 == 0:
            info(f"  Added {index}/{len(files)} file(s)")


def _zip_name(root: Path, path: Path, prefix: str) -> str:
    parts = path.relative_to(root).parts
    return str(PurePosixPath(prefix, *parts) if prefix else PurePosixPath(*parts))
