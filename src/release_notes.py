import argparse
import os
from pathlib import Path
from urllib.parse import quote

from config import (
    LANGUAGE_NAMES,
    LANGUAGE_NATIVE_NAMES,
    PROCESSED_ZIP_PREFIX,
    SOURCE_ZIP_PREFIX,
    ZIP_PREFIX,
)


def build_release_notes(
    output_dir: Path,
    repository: str,
    tag: str,
    version: str,
    commit_sha: str | None = None,
    server_url: str = "https://github.com",
) -> str:
    assets = {path.name for path in output_dir.glob("*.zip") if path.is_file()}
    language_assets = _language_assets(assets, version)
    source_asset = f"{SOURCE_ZIP_PREFIX}_{version}.zip"
    processed_asset = f"{PROCESSED_ZIP_PREFIX}_{version}.zip"
    _require_assets(assets, source_asset, processed_asset)

    lines = []
    if commit_sha:
        commit_url = _repository_url(server_url, repository, "commit", commit_sha)
        lines.extend(
            [
                f"Automated export for commit [`{commit_sha[:7]}`]({commit_url}).",
                "",
            ]
        )

    lines.extend(
        [
            "## DATABASE",
            "",
            "Localized database workbooks, packaged separately for each language.",
            "",
            "| Language | Download |",
            "| --- | --- |",
        ]
    )
    for language_code, asset in language_assets:
        language_name = LANGUAGE_NATIVE_NAMES[language_code]
        asset_url = _repository_url(server_url, repository, "releases", "download", tag, asset)
        lines.append(f"| {language_name} | [Download ZIP]({asset_url}) |")

    source_url = _repository_url(server_url, repository, "releases", "download", tag, source_asset)
    processed_url = _repository_url(server_url, repository, "releases", "download", tag, processed_asset)
    lines.extend(
        [
            "",
            "## MHWS-in-json",
            "",
            "Complete source JSON data.",
            "",
            f"[Download MHWS-in-json (ZIP)]({source_url})",
            "",
            "## PROCESSED_DATA",
            "",
            "Language-independent processed data.",
            "",
            f"[Download PROCESSED_DATA (ZIP)]({processed_url})",
            "",
        ]
    )
    return "\n".join(lines)


def _language_assets(assets: set[str], version: str) -> list[tuple[str, str]]:
    prefix = f"{ZIP_PREFIX}_"
    suffix = f"_{version}.zip"
    found = {}
    for asset in assets:
        if asset.startswith(prefix) and asset.endswith(suffix):
            language_code = asset[len(prefix) : -len(suffix)]
            found[language_code] = asset

    if not found:
        raise ValueError(f"No {ZIP_PREFIX} language archives found in the output directory")

    missing_names = sorted(set(found) - set(LANGUAGE_NATIVE_NAMES))
    if missing_names:
        joined = ", ".join(missing_names)
        raise ValueError(f"Missing native language name(s): {joined}")

    language_order = {code: index for index, code in LANGUAGE_NAMES.items()}
    return sorted(found.items(), key=lambda item: language_order.get(item[0], len(language_order)))


def _require_assets(assets: set[str], *required: str) -> None:
    missing = [asset for asset in required if asset not in assets]
    if missing:
        raise FileNotFoundError(f"Missing release asset(s): {', '.join(missing)}")


def _repository_url(server_url: str, repository: str, *parts: str) -> str:
    path = "/".join(quote(part, safe="") for part in parts)
    repository_path = "/".join(quote(part, safe="") for part in repository.split("/"))
    return f"{server_url.rstrip('/')}/{repository_path}/{path}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Markdown release notes for exported archives")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--tag")
    parser.add_argument("--version", default=os.environ.get("RELEASE_VERSION"))
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument("--server-url", default=os.environ.get("GITHUB_SERVER_URL", "https://github.com"))
    args = parser.parse_args()

    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    if not args.version:
        parser.error("--version or RELEASE_VERSION is required")
    tag = args.tag or f"database-{args.version}"

    notes = build_release_notes(
        args.output_dir,
        args.repository,
        tag,
        args.version,
        args.commit,
        args.server_url,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
