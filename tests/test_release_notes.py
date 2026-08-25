import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import (
    LANGUAGES,
    PROCESSED_ZIP_PREFIX,
    SOURCE_ZIP_PREFIX,
    ZIP_PREFIX,
)


SCRIPT_PATH = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "release_notes.py"
SPEC = importlib.util.spec_from_file_location("github_release_notes", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load release notes script: {SCRIPT_PATH}")
release_notes = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_notes
SPEC.loader.exec_module(release_notes)

CommitChangelog = release_notes.CommitChangelog
build_release_notes = release_notes.build_release_notes
collect_commit_changelog = release_notes.collect_commit_changelog


class ReleaseNotesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository_dir = Path(self.temp_dir.name) / "repository"
        self.repository_dir.mkdir()
        self._git("init", "--initial-branch=main")
        self._git("config", "user.name", "Release Notes Test")
        self._git("config", "user.email", "release-notes@example.com")
        self._commit("Base commit")
        self._git("tag", "database-base")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_limits_changelog_to_twenty_commits_since_previous_release(self) -> None:
        for index in range(1, 22):
            subject = "🗃️ 同步游戏数据" if index == 21 else f"Change {index:02d}"
            self._commit(subject)

        current_sha = self._git("rev-parse", "HEAD").strip()
        changelog = collect_commit_changelog(current_sha, self.repository_dir)
        notes = self._build_notes(changelog)

        self.assertEqual(changelog.previous_tag, "database-base")
        self.assertEqual(changelog.total_commits, 21)
        self.assertEqual(len(changelog.commits), 20)
        self.assertEqual(changelog.commits[0].subject, "🗃️ 同步游戏数据")
        self.assertEqual(changelog.commits[-1].subject, "Change 02")
        self.assertIn("- 🗃️ 同步游戏数据", notes)
        self.assertIn(f"/commit/{changelog.commits[0].sha}", notes)
        self.assertNotIn("- Change 01", notes)
        self.assertIn("Showing the latest 20 of 21 commits", notes)
        self.assertIn(
            f"/compare/database-base...{current_sha}",
            notes,
        )

    def test_does_not_show_more_for_exactly_twenty_commits(self) -> None:
        for index in range(1, 21):
            self._commit(f"Change {index:02d}")

        current_sha = self._git("rev-parse", "HEAD").strip()
        changelog = collect_commit_changelog(current_sha, self.repository_dir)
        notes = self._build_notes(changelog)

        self.assertEqual(changelog.total_commits, 20)
        self.assertEqual(len(changelog.commits), 20)
        self.assertNotIn("Show more commits", notes)

    def test_current_release_tag_produces_an_empty_changelog(self) -> None:
        current_sha = self._git("rev-parse", "HEAD").strip()
        changelog = collect_commit_changelog(current_sha, self.repository_dir)
        notes = self._build_notes(changelog)

        self.assertEqual(changelog.previous_tag, "database-base")
        self.assertEqual(changelog.total_commits, 0)
        self.assertEqual(changelog.commits, ())
        self.assertIn("No commits since the previous release.", notes)
        self.assertNotIn("Show more commits", notes)

    def test_ignores_unrelated_tags_when_finding_previous_release(self) -> None:
        self._commit("First change")
        self._git("tag", "v1.0.0")
        self._commit("Second change")

        current_sha = self._git("rev-parse", "HEAD").strip()
        changelog = collect_commit_changelog(current_sha, self.repository_dir)

        self.assertEqual(changelog.previous_tag, "database-base")
        self.assertEqual(changelog.total_commits, 2)
        self.assertEqual(
            [commit.subject for commit in changelog.commits],
            ["Second change", "First change"],
        )

    def test_emits_release_notes_to_stdout_without_a_temporary_file(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            release_notes.emit_release_notes("# Release notes")

        self.assertEqual(stdout.getvalue(), "# Release notes\n")

    def test_reconfigures_cp1252_stdout_before_writing_unicode(self) -> None:
        buffer = io.BytesIO()
        stdout = io.TextIOWrapper(buffer, encoding="cp1252")

        with contextlib.redirect_stdout(stdout):
            release_notes.emit_release_notes("简体中文")
            stdout.flush()

        self.assertEqual(stdout.encoding, "utf-8")
        self.assertEqual(buffer.getvalue().decode("utf-8").splitlines(), ["简体中文"])

    def test_standalone_cli_outputs_notes_without_project_imports(self) -> None:
        version = "standalone-version"
        output_dir = self._create_assets(version)
        current_sha = self._git("rev-parse", "HEAD").strip()

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--output-dir",
                str(output_dir),
                "--repository-dir",
                str(self.repository_dir),
                "--repository",
                "owner/repository",
                "--version",
                version,
                "--commit",
                current_sha,
            ],
            cwd=self.repository_dir,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertIn("## What's Changed", result.stdout)
        self.assertIn("## DATABASE", result.stdout)
        self.assertIn("## MHWS-in-json", result.stdout)
        self.assertIn("## PROCESSED_DATA", result.stdout)
        self.assertFalse((output_dir / "release-notes.md").exists())

    def test_json_payload_centralizes_workflow_release_configuration(self) -> None:
        version = "json-version"
        output_dir = self._create_assets(version)
        current_sha = self._git("rev-parse", "HEAD").strip()

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--format",
                "json",
                "--output-dir",
                str(output_dir),
                "--repository-dir",
                str(self.repository_dir),
                "--repository",
                "owner/repository",
                "--version",
                version,
                "--commit",
                current_sha,
            ],
            cwd=self.repository_dir,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        payload = json.loads(result.stdout)

        self.assertTrue(result.stdout.isascii())
        self.assertEqual(payload["tag"], f"database-{version}")
        self.assertEqual(payload["title"], f"Database {version}")
        self.assertIn("## What's Changed", payload["notes"])
        self.assertIn("日本語", payload["notes"])
        self.assertEqual(len(payload["assets"]), 3)

    def test_script_configuration_matches_project_exporter(self) -> None:
        language_section = release_notes.LANGUAGE_ASSET_SECTION
        if language_section is None:
            self.fail("Project configuration requires a language asset section")
        expected_languages = {
            language.code: language.native_name
            for language in LANGUAGES.values()
        }
        configured_templates = {
            section["filename_template"]
            for section in release_notes.ASSET_SECTIONS
        }

        self.assertEqual(language_section["languages"], expected_languages)
        self.assertEqual(
            language_section["filename_template"],
            f"{ZIP_PREFIX}_{{code}}_{{version}}.zip",
        )
        self.assertIn(
            f"{SOURCE_ZIP_PREFIX}_{{version}}.zip",
            configured_templates,
        )
        self.assertIn(
            f"{PROCESSED_ZIP_PREFIX}_{{version}}.zip",
            configured_templates,
        )

    def test_asset_sections_can_be_disabled_for_a_notes_only_project(self) -> None:
        output_dir = Path(self.temp_dir.name) / "empty-output"
        output_dir.mkdir()
        current_sha = self._git("rev-parse", "HEAD").strip()
        changelog = collect_commit_changelog(current_sha, self.repository_dir)

        with (
            mock.patch.object(release_notes, "UPLOAD_ASSET_PATTERNS", ()),
            mock.patch.object(release_notes, "LANGUAGE_ASSET_SECTION", None),
            mock.patch.object(release_notes, "ASSET_SECTIONS", ()),
        ):
            upload_assets = release_notes.collect_upload_assets(output_dir)
            notes = build_release_notes(
                output_dir,
                "owner/repository",
                "v1",
                "1",
                current_sha,
                changelog=changelog,
                upload_assets=upload_assets,
            )

        self.assertEqual(upload_assets, ())
        self.assertIn("## What's Changed", notes)
        self.assertNotIn("## DATABASE", notes)

    def _build_notes(self, changelog: CommitChangelog) -> str:
        version = "test-version"
        output_dir = self._create_assets(version)

        return build_release_notes(
            output_dir,
            "owner/repository",
            f"database-{version}",
            version,
            changelog.current_sha,
            changelog=changelog,
        )

    def _create_assets(self, version: str) -> Path:
        output_dir = Path(self.temp_dir.name) / f"output-{version}"
        output_dir.mkdir(exist_ok=True)
        language_section = release_notes.LANGUAGE_ASSET_SECTION
        if language_section is None:
            self.fail("Test configuration requires a language asset section")
        languages = language_section["languages"]
        language_code = next(iter(languages))
        language_template = language_section["filename_template"]
        assets = [language_template.format(code=language_code, version=version)]
        assets.extend(
            section["filename_template"].format(version=version)
            for section in release_notes.ASSET_SECTIONS
        )
        for asset in assets:
            (output_dir / asset).touch()
        return output_dir

    def _commit(self, subject: str) -> None:
        self._git("commit", "--allow-empty", "--message", subject)

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository_dir,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout


if __name__ == "__main__":
    unittest.main()
