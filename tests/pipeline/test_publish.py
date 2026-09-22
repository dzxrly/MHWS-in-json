from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from src.pipeline.publish import ExportTransaction
from src.pipeline.validation import validate_outputs


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.output.mkdir()
        (self.output / "previous.txt").write_text("previous", encoding="utf-8")

    def test_generation_failure_preserves_published_result(self):
        with self.assertRaisesRegex(ValueError, "generation failed"):
            with ExportTransaction(self.output, self.root) as transaction:
                (transaction.stage / "partial.txt").touch()
                raise ValueError("generation failed")
        self.assertEqual((self.output / "previous.txt").read_text(encoding="utf-8"), "previous")
        self.assertFalse((self.output / "partial.txt").exists())

    def test_publish_failure_restores_previous_directory(self):
        original = Path.replace
        with ExportTransaction(self.output, self.root) as transaction:
            (transaction.stage / "new.txt").write_text("new", encoding="utf-8")

            def fail_stage(path, target):
                if path == transaction.stage:
                    raise OSError("destination locked")
                return original(path, target)

            with patch.object(Path, "replace", fail_stage):
                with self.assertRaisesRegex(OSError, "destination locked"):
                    transaction.publish()
            self.assertTrue((self.output / "previous.txt").exists())

    def test_success_publishes_complete_directory_and_cleans_backup(self):
        with ExportTransaction(self.output, self.root) as transaction:
            (transaction.stage / "new.txt").write_text("new", encoding="utf-8")
            transaction.publish()
        self.assertEqual({path.name for path in self.output.iterdir()}, {"new.txt"})
        self.assertFalse(transaction.run_dir.exists())

    def test_interrupted_publication_restores_previous_directory(self):
        original = Path.replace
        with ExportTransaction(self.output, self.root) as transaction:
            def interrupt_stage(path, target):
                if path == transaction.stage:
                    raise KeyboardInterrupt()
                return original(path, target)

            with patch.object(Path, "replace", interrupt_stage):
                with self.assertRaises(KeyboardInterrupt):
                    transaction.publish()
            self.assertTrue((self.output / "previous.txt").exists())

    def test_workspace_and_staging_cannot_be_publication_targets(self):
        for output in (self.root, self.root / ".agents", self.root / ".agents/export-runs/nested"):
            with self.assertRaises(ValueError):
                ExportTransaction(output, self.root)

    def test_manifest_rejects_missing_and_mismatched_archive_members(self):
        stage = self.root / "stage"
        source = stage / "zh-Hans"
        source.mkdir(parents=True)
        (source / "data.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_outputs(stage, {"zh-Hans/missing.json"}, {})
        with ZipFile(stage / "language.zip", "w") as archive:
            archive.writestr("wrong.json", "[]")
        with self.assertRaisesRegex(ValueError, "contents"):
            validate_outputs(stage, {"zh-Hans/data.json"}, {"language.zip": source})
