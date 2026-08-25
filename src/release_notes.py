import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from config import (
    LANGUAGES,
    PROCESSED_ZIP_PREFIX,
    SOURCE_ZIP_PREFIX,
    ZIP_PREFIX,
)

_LANGUAGES_BY_CODE = {
    language.code: (lang_id, language)
    for lang_id, language in LANGUAGES.items()
}
_MAX_CHANGELOG_COMMITS = 20
_RELEASE_TAG_PATTERN = "database-*"


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
    limit: int = _MAX_CHANGELOG_COMMITS,
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
    if changelog:
        lines.extend(_changelog_lines(changelog, repository, server_url))

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
        language_name = _LANGUAGES_BY_CODE[language_code][1].native_name
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


def _changelog_lines(
    changelog: CommitChangelog,
    repository: str,
    server_url: str,
) -> list[str]:
    lines = ["## What's Changed", ""]
    if not changelog.commits:
        return lines + ["No commits since the previous database release.", ""]

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

    missing_names = sorted(set(found) - set(_LANGUAGES_BY_CODE))
    if missing_names:
        joined = ", ".join(missing_names)
        raise ValueError(f"Missing native language name(s): {joined}")

    return sorted(found.items(), key=lambda item: _LANGUAGES_BY_CODE[item[0]][0])


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
        _RELEASE_TAG_PATTERN,
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
    changelog = collect_commit_changelog(args.commit) if args.commit else None

    notes = build_release_notes(
        args.output_dir,
        args.repository,
        tag,
        args.version,
        args.commit,
        args.server_url,
        changelog,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
