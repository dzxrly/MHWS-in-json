"""Exercise publication failures without touching real calculator outputs."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from config import BASE_DIR
from src.processed_data.calculator_bundle import synchronize


class CalculatorBundleTests(unittest.TestCase):
    def setUp(self):
        root = BASE_DIR / ".agents" / "bundle-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.roots = (self.workspace / "export", self.workspace / "consumer")
        for root in self.roots:
            root.mkdir()
            (root / "damage.json").write_bytes(b"old damage")
        self.files = {"damage.json": b"new damage", "new.json": b"new file"}

    def assert_restored(self):
        for root in self.roots:
            self.assertEqual((root / "damage.json").read_bytes(), b"old damage")
            self.assertFalse((root / "new.json").exists())

    def test_success_updates_both_destinations_and_cleans_staging(self):
        synchronize(self.files, self.roots, self.workspace)
        for root in self.roots:
            for name, value in self.files.items():
                self.assertEqual((root / name).read_bytes(), value)
        self.assertEqual(list((self.workspace / ".agents/calculator-bundles").iterdir()), [])

    def test_second_destination_failure_restores_first_and_removes_new_files(self):
        write = Path.write_bytes

        def fail_second(path, content):
            if path == self.roots[1] / "damage.json" and content == b"new damage":
                raise PermissionError("simulated locked consumer file")
            return write(path, content)

        with patch.object(Path, "write_bytes", fail_second):
            with self.assertRaisesRegex(PermissionError, "locked consumer"):
                synchronize(self.files, self.roots, self.workspace)
        self.assert_restored()

    def test_generator_failure_restores_script_and_both_json_destinations(self):
        trace = self.workspace / "trace"
        trace.mkdir()
        script = trace / "mhws_element_trace.lua"
        script.write_bytes(b"old script")

        def fail_generator(*args, **kwargs):
            script.write_bytes(b"partially generated script")
            raise subprocess.CalledProcessError(1, "generator")

        with patch("src.processed_data.calculator_bundle.subprocess.run", fail_generator):
            with self.assertRaises(subprocess.CalledProcessError):
                synchronize(self.files, self.roots, self.workspace, trace)
        self.assert_restored()
        self.assertEqual(script.read_bytes(), b"old script")
