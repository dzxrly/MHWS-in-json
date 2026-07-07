from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


def zip_language_output(
    language_dir: Path,
    output_dir: Path,
    language_name: str,
    version: str,
    prefix: str,
    json_root: Path,
) -> Path:
    archive = output_dir / f"{prefix}_{language_name}_{version}.zip"
    with _zip(archive) as zf:
        _write_tree(zf, language_dir)
        _write_tree(zf, json_root, json_root.name)
    return archive


def zip_processed_output(
    processed_dir: Path,
    output_dir: Path,
    version: str,
    prefix: str,
) -> Path:
    archive = output_dir / f"{prefix}_{version}.zip"
    with _zip(archive) as zf:
        _write_tree(zf, processed_dir)
    return archive


def _zip(path: Path) -> ZipFile:
    return ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9)


def _write_tree(zf: ZipFile, root: Path, prefix: str = "") -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            zf.write(path, _zip_name(root, path, prefix))


def _zip_name(root: Path, path: Path, prefix: str) -> str:
    parts = path.relative_to(root).parts
    return str(PurePosixPath(prefix, *parts) if prefix else PurePosixPath(*parts))
