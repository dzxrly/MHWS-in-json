import subprocess
import tempfile
import unittest
from pathlib import Path

from config import LANGUAGES, PROCESSED_ZIP_PREFIX, SOURCE_ZIP_PREFIX, ZIP_PREFIX
from src.release_notes import (
    CommitChangelog,
    build_release_notes,
    collect_commit_changelog,
)


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
        self.assertIn("No commits since the previous database release.", notes)
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

    def _build_notes(self, changelog: CommitChangelog) -> str:
        version = "test-version"
        output_dir = Path(self.temp_dir.name) / "output"
        output_dir.mkdir(exist_ok=True)
        language = next(iter(LANGUAGES.values()))
        assets = [
            f"{ZIP_PREFIX}_{language.code}_{version}.zip",
            f"{SOURCE_ZIP_PREFIX}_{version}.zip",
            f"{PROCESSED_ZIP_PREFIX}_{version}.zip",
        ]
        for asset in assets:
            (output_dir / asset).touch()

        return build_release_notes(
            output_dir,
            "owner/repository",
            f"database-{version}",
            version,
            changelog.current_sha,
            changelog=changelog,
        )

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
