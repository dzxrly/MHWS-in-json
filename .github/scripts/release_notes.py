import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


# Project configuration: edit only this block when reusing the script.
RELEASE_TAG_PATTERN = "database-*"
RELEASE_TAG_TEMPLATE = "database-{version}"
RELEASE_TITLE_TEMPLATE = "Database {version}"
MAX_CHANGELOG_COMMITS = 20
DEFAULT_OUTPUT_DIRECTORY = Path("output")
# Use an empty tuple for a notes-only release with no uploaded assets.
UPLOAD_ASSET_PATTERNS = ("*.zip",)

# Set to None when the project has no language-specific release assets.
LANGUAGE_ASSET_SECTION: dict[str, object] | None = {
    "heading": "DATABASE",
    "description": "Localized database workbooks, packaged separately for each language.",
    "filename_template": "DATABASE_{code}_{version}.zip",
    "link_text": "Download ZIP",
    "languages": {
        "ja-JP": "日本語",
        "en-US": "English",
        "fr-FR": "Français",
        "it-IT": "Italiano",
        "de-DE": "Deutsch",
        "es-ES": "Español",
        "ru-RU": "Русский",
        "pl-PL": "Polski",
        "nl-NL": "Nederlands",
        "pt-PT": "Português (Portugal)",
        "pt-BR": "Português (Brasil)",
        "ko-KR": "한국어",
        "zh-Hant": "繁體中文",
        "zh-Hans": "简体中文",
        "fi-FI": "Suomi",
        "sv-SE": "Svenska",
        "da-DK": "Dansk",
        "no-NO": "Norsk",
        "cs-CZ": "Čeština",
        "hu-HU": "Magyar",
        "sk-SK": "Slovenčina",
        "ar-SA": "العربية",
        "tr-TR": "Türkçe",
        "bg-BG": "Български",
        "el-GR": "Ελληνικά",
        "ro-RO": "Română",
        "es-419": "Español (Latinoamérica)",
        "vi-VN": "Tiếng Việt",
        "id-ID": "Bahasa Indonesia",
        "uk-UA": "Українська",
        "hi-IN": "हिन्दी",
        "ms-MY": "Bahasa Melayu",
        "th-TH": "ไทย",
    },
}

# Use an empty tuple when no additional asset sections are needed.
ASSET_SECTIONS: tuple[dict[str, str], ...] = (
    {
        "heading": "MHWS-in-json",
        "description": "Complete source JSON data.",
        "filename_template": "MHWS-in-json_{version}.zip",
        "link_text": "Download MHWS-in-json (ZIP)",
    },
    {
        "heading": "PROCESSED_DATA",
        "description": "Language-independent processed data.",
        "filename_template": "PROCESSED_DATA_{version}.zip",
        "link_text": "Download PROCESSED_DATA (ZIP)",
    },
)
# End project configuration.


@dataclass(frozen=True)
class CommitChange:
    sha: str
    subject: str


@dataclass(frozen=True)
class CommitChangelog:
    previous_tag: str | None
    current_sha: str
    total_commits: int
    commits: tuple[CommitChange, ...]


def collect_commit_changelog(
    commit_sha: str,
    repository_dir: Path = Path("."),
    limit: int = MAX_CHANGELOG_COMMITS,
) -> CommitChangelog:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    current_sha = _git(
        repository_dir,
        "rev-parse",
        "--verify",
        f"{commit_sha}^{{commit}}",
    ).strip()
    previous_tag = _find_previous_release_tag(repository_dir, current_sha)
    revision = f"{previous_tag}..{current_sha}" if previous_tag else current_sha
    total_commits = int(_git(repository_dir, "rev-list", "--count", revision).strip())
    log_output = _git(
        repository_dir,
        "-c",
        "i18n.logOutputEncoding=utf-8",
        "log",
        "-z",
        f"--max-count={limit}",
        "--format=%H%x00%s",
        revision,
    )
    fields = log_output.rstrip("\0").split("\0") if log_output else []
    if len(fields) % 2:
        raise RuntimeError("Unexpected git log output while generating release notes")
    commits = tuple(
        CommitChange(fields[index], fields[index + 1])
        for index in range(0, len(fields), 2)
    )
    return CommitChangelog(previous_tag, current_sha, total_commits, commits)


def build_release_notes(
    output_dir: Path,
    repository: str,
    tag: str,
    version: str,
    commit_sha: str | None = None,
    server_url: str = "https://github.com",
    changelog: CommitChangelog | None = None,
    upload_assets: tuple[Path, ...] | None = None,
) -> str:
    if upload_assets is None:
        upload_assets = collect_upload_assets(output_dir)
    assets = {path.name for path in upload_assets}
    lines = []
    if commit_sha:
        commit_url = _repository_url(server_url, repository, "commit", commit_sha)
        lines.extend(
            [
                f"Automated export for commit [`{commit_sha[:7]}`]({commit_url}).",
                "",
            ]
        )
    if changelog:
        lines.extend(_changelog_lines(changelog, repository, server_url))
    if LANGUAGE_ASSET_SECTION:
        lines.extend(
            _language_asset_lines(
                LANGUAGE_ASSET_SECTION,
                assets,
                repository,
                tag,
                version,
                server_url,
            )
        )
    for section in ASSET_SECTIONS:
        lines.extend(
            _asset_section_lines(
                section,
                assets,
                repository,
                tag,
                version,
                server_url,
            )
        )
    return "\n".join(lines)


def collect_upload_assets(output_dir: Path) -> tuple[Path, ...]:
    assets = {}
    for pattern in UPLOAD_ASSET_PATTERNS:
        for path in output_dir.glob(pattern):
            if path.is_file():
                assets[path.name] = path.resolve()
    if not assets and UPLOAD_ASSET_PATTERNS:
        joined = ", ".join(UPLOAD_ASSET_PATTERNS)
        raise FileNotFoundError(f"No release assets matched: {joined}")
    return tuple(assets[name] for name in sorted(assets))


def emit_release_notes(notes: str, output: Path | None = None) -> None:
    if output is None or output == Path("-"):
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
        sys.stdout.write(notes)
        if not notes.endswith("\n"):
            sys.stdout.write("\n")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(notes, encoding="utf-8", newline="\n")


def _changelog_lines(
    changelog: CommitChangelog,
    repository: str,
    server_url: str,
) -> list[str]:
    lines = ["## What's Changed", ""]
    if not changelog.commits:
        return lines + ["No commits since the previous release.", ""]

    for commit in changelog.commits:
        commit_url = _repository_url(server_url, repository, "commit", commit.sha)
        lines.append(f"- {commit.subject} ([`{commit.sha[:7]}`]({commit_url}))")

    if changelog.total_commits > len(changelog.commits):
        if changelog.previous_tag:
            more_url = _repository_url(
                server_url,
                repository,
                "compare",
                f"{changelog.previous_tag}...{changelog.current_sha}",
            )
        else:
            more_url = _repository_url(
                server_url,
                repository,
                "commits",
                changelog.current_sha,
            )
        lines.extend(
            [
                "",
                (
                    f"> Showing the latest {len(changelog.commits)} of "
                    f"{changelog.total_commits} commits. "
                    f"[Show more commits →]({more_url})"
                ),
            ]
        )

    lines.append("")
    return lines


def _language_asset_lines(
    section: dict[str, object],
    assets: set[str],
    repository: str,
    tag: str,
    version: str,
    server_url: str,
) -> list[str]:
    heading = _config_string(section, "heading")
    description = _config_string(section, "description")
    filename_template = _config_string(section, "filename_template")
    link_text = _config_string(section, "link_text")
    languages = section.get("languages")
    if not isinstance(languages, dict) or not all(
        isinstance(code, str) and isinstance(name, str)
        for code, name in languages.items()
    ):
        raise ValueError("LANGUAGE_ASSET_SECTION.languages must map codes to names")

    language_assets = _language_assets(
        assets,
        version,
        filename_template,
        languages,
    )
    lines = [
        f"## {heading}",
        "",
        description,
        "",
        "| Language | Download |",
        "| --- | --- |",
    ]
    for language_code, language_name, asset in language_assets:
        asset_url = _repository_url(
            server_url,
            repository,
            "releases",
            "download",
            tag,
            asset,
        )
        lines.append(f"| {language_name} | [{link_text}]({asset_url}) |")
    lines.append("")
    return lines


def _asset_section_lines(
    section: dict[str, str],
    assets: set[str],
    repository: str,
    tag: str,
    version: str,
    server_url: str,
) -> list[str]:
    heading = _config_string(section, "heading")
    description = _config_string(section, "description")
    filename_template = _config_string(section, "filename_template")
    link_text = _config_string(section, "link_text")
    asset = _format_asset_filename(filename_template, version=version)
    _require_assets(assets, asset)
    asset_url = _repository_url(
        server_url,
        repository,
        "releases",
        "download",
        tag,
        asset,
    )
    return [
        f"## {heading}",
        "",
        description,
        "",
        f"[{link_text}]({asset_url})",
        "",
    ]


def _language_assets(
    assets: set[str],
    version: str,
    filename_template: str,
    languages: dict[str, str],
) -> list[tuple[str, str, str]]:
    if filename_template.count("{code}") != 1:
        raise ValueError("Language filename template must contain one {code} placeholder")
    prefix_template, suffix_template = filename_template.split("{code}")
    prefix = _format_asset_filename(prefix_template, version=version)
    suffix = _format_asset_filename(suffix_template, version=version)
    found = {}
    for asset in assets:
        if asset.startswith(prefix) and asset.endswith(suffix):
            end = len(asset) - len(suffix) if suffix else None
            language_code = asset[len(prefix) : end]
            found[language_code] = asset

    if not found:
        raise ValueError("No configured language archives found in the output directory")

    missing_names = sorted(set(found) - set(languages))
    if missing_names:
        joined = ", ".join(missing_names)
        raise ValueError(f"Missing native language name(s): {joined}")

    return [
        (language_code, languages[language_code], found[language_code])
        for language_code in languages
        if language_code in found
    ]


def _format_asset_filename(template: str, *, version: str) -> str:
    try:
        return template.format(version=version)
    except (IndexError, KeyError, ValueError) as error:
        raise ValueError(f"Invalid asset filename template: {template}") from error


def _config_string(config: dict[str, object], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Configuration value {key!r} must be a non-empty string")
    return value


def _require_assets(assets: set[str], *required: str) -> None:
    missing = [asset for asset in required if asset not in assets]
    if missing:
        raise FileNotFoundError(f"Missing release asset(s): {', '.join(missing)}")


def _find_previous_release_tag(repository_dir: Path, commit_sha: str) -> str | None:
    result = _run_git(
        repository_dir,
        "describe",
        "--tags",
        "--match",
        RELEASE_TAG_PATTERN,
        "--abbrev=0",
        commit_sha,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    if result.returncode == 128:
        return None
    message = result.stderr.strip() or "git describe failed"
    raise RuntimeError(message)


def _git(repository_dir: Path, *args: str) -> str:
    result = _run_git(repository_dir, *args)
    return result.stdout


def _run_git(
    repository_dir: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_dir,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or f"git {' '.join(args)} failed"
        raise RuntimeError(message)
    return result


def _repository_url(server_url: str, repository: str, *parts: str) -> str:
    path = "/".join(quote(part, safe="") for part in parts)
    repository_path = "/".join(quote(part, safe="") for part in repository.split("/"))
    return f"{server_url.rstrip('/')}/{repository_path}/{path}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Markdown release notes")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument(
        "--output",
        type=Path,
        help='Write to a file instead of stdout; use "-" for stdout',
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output Markdown or a workflow-ready JSON release payload",
    )
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument(
        "--repository-dir",
        type=Path,
        default=Path(os.environ.get("GITHUB_WORKSPACE", ".")),
    )
    parser.add_argument("--tag")
    parser.add_argument("--version", default=os.environ.get("RELEASE_VERSION"))
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument(
        "--server-url",
        default=os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
    )
    args = parser.parse_args()

    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    if not args.version:
        parser.error("--version or RELEASE_VERSION is required")
    tag = args.tag or RELEASE_TAG_TEMPLATE.format(version=args.version)
    title = RELEASE_TITLE_TEMPLATE.format(version=args.version)
    changelog = (
        collect_commit_changelog(args.commit, args.repository_dir)
        if args.commit
        else None
    )
    commit_sha = changelog.current_sha if changelog else args.commit
    upload_assets = collect_upload_assets(args.output_dir)
    notes = build_release_notes(
        args.output_dir,
        args.repository,
        tag,
        args.version,
        commit_sha,
        args.server_url,
        changelog,
        upload_assets,
    )
    if args.format == "json":
        payload = {
            "tag": tag,
            "title": title,
            "notes": notes,
            "assets": [str(path) for path in upload_assets],
        }
        emit_release_notes(json.dumps(payload, ensure_ascii=True), args.output)
    else:
        emit_release_notes(notes, args.output)


if __name__ == "__main__":
    main()
