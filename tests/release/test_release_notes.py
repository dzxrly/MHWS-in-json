import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from config import (
    LANGUAGES,
    PROCESSED_ZIP_PREFIX,
    SOURCE_ZIP_PREFIX,
    ZIP_PREFIX,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "scripts" / "release_notes.py"
)
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
        scratch_dir = Path(__file__).resolve().parents[2] / ".tmp"
        scratch_dir.mkdir(exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=scratch_dir)
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

    def test_current_release_tag_produces_an_empty_changelog(self) -> None:
        current_sha = self._git("rev-parse", "HEAD").strip()
        changelog = collect_commit_changelog(current_sha, self.repository_dir)
        notes = self._build_notes(changelog)

        self.assertEqual(changelog.previous_tag, "database-base")
        self.assertEqual(changelog.total_commits, 0)
        self.assertEqual(changelog.commits, ())
        self.assertIn("No commits since the previous release.", notes)
        self.assertNotIn("Show more commits", notes)

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
        self.assertIn(
            "<summary>Files in each ZIP (2 files)</summary>\n\n- `FullText.xlsx`",
            result.stdout,
        )
        self.assertIn("- `MissionData.xlsx`", result.stdout)
        self.assertIn(
            "<summary>Files in ZIP (6 files)</summary>\n\n- `EnemyActionNames.xlsx`",
            result.stdout,
        )
        self.assertIn("- `skill_pool.json`", result.stdout)
        self.assertIn("no other language editions are provided.", result.stdout)
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

    def test_download_links_precede_collapsed_folder_summaries(self) -> None:
        version = "layout-version"
        output_dir = self._create_assets(version)
        notes = build_release_notes(
            output_dir, "owner/repository", f"database-{version}", version
        )
        processed = notes[notes.index("## PROCESSED_DATA") :]

        self.assertLess(
            notes.index("| Language | Download |"),
            notes.index("<summary>Files in each ZIP"),
        )
        self.assertLess(
            processed.index("[Download PROCESSED_DATA (ZIP)]"),
            processed.index("<summary>Files in ZIP"),
        )
        self.assertIn("- `nested/`: 3 files (2 `.json`, 1 `.xlsx`)", processed)
        self.assertIn("- `single/only.json`", processed)
        self.assertNotIn("nested/a.json", processed)
        self.assertTrue(processed.rstrip().endswith("</details>"))

    def test_notes_link_the_website_before_the_downloads(self) -> None:
        version = "website-version"
        output_dir = self._create_assets(version)
        notes = build_release_notes(
            output_dir, "owner/repository", f"database-{version}", version
        )
        website = release_notes.WEBSITE_SECTION
        if website is None:
            self.fail("Project configuration requires a website section")

        self.assertIn(f"[{website['link_text']}]({website['url']})", notes)
        self.assertLess(notes.index("## Website"), notes.index("## DATABASE"))
        self.assertNotIn(".html", notes)

    def test_language_archives_must_have_the_same_file_list(self) -> None:
        version = "different-files"
        output_dir = self._create_assets(version)
        language_section = release_notes.LANGUAGE_ASSET_SECTION
        if language_section is None:
            self.fail("Test configuration requires a language asset section")
        codes = iter(language_section["languages"])
        next(codes)
        second_code = next(codes)
        second_name = language_section["filename_template"].format(
            code=second_code, version=version
        )
        with ZipFile(output_dir / second_name, "w") as archive:
            archive.writestr("FullText.xlsx", "")

        with self.assertRaisesRegex(
            ValueError, "language archives contain different files"
        ):
            build_release_notes(
                output_dir, "owner/repository", f"database-{version}", version
            )

    def test_script_configuration_matches_project_exporter(self) -> None:
        language_section = release_notes.LANGUAGE_ASSET_SECTION
        if language_section is None:
            self.fail("Project configuration requires a language asset section")
        expected_languages = {
            language.code: language.native_name for language in LANGUAGES.values()
        }
        configured_templates = {
            section["filename_template"] for section in release_notes.ASSET_SECTIONS
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
            if asset.startswith("DATABASE_"):
                files = ("FullText.xlsx", "MissionData.xlsx")
            elif asset.startswith("PROCESSED_DATA_"):
                files = (
                    "EnemyActionNames.xlsx",
                    "nested/a.json",
                    "nested/b.json",
                    "nested/c.xlsx",
                    "single/only.json",
                    "skill_pool.json",
                )
            else:
                files = ("MHWS-in-json/Enums_Internal.json",)
            with ZipFile(output_dir / asset, "w") as archive:
                for filename in files:
                    archive.writestr(filename, "")
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
