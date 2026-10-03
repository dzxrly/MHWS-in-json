"""Exercise the build-data transport without contacting GitHub."""

import argparse
import gzip
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sdk.il2cpp import upload_il2cpp


class UploadIl2cppTests(unittest.TestCase):
    def test_gzip_is_reproducible_and_download_preserves_input(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            original = root / "source.json"
            original.write_bytes(b'{"types": {"app.Test": {"size": 32}}}\n')
            first, second = root / "first.gz", root / "second.gz"
            upload_il2cpp.compress_file(original, first, 9)
            upload_il2cpp.compress_file(original, second, 9)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            checksum = root / "first.gz.sha256"
            upload_il2cpp.write_checksum(
                checksum, upload_il2cpp.sha256_file(first), first.name
            )
            upload_il2cpp.verify_checksum(first, checksum)
            restored = root / "restored.json"
            with patch.object(upload_il2cpp, "DEFAULT_WORK_DIR", root / "cache"):
                upload_il2cpp.decompress_file(first, restored)
            self.assertEqual(restored.read_bytes(), original.read_bytes())

    def test_bad_checksum_never_replaces_existing_dump(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            output = root / "il2cpp_dump.json"
            output.write_bytes(b"previous input")
            asset = root / "il2cpp_dump.json.gz"
            asset.write_bytes(gzip.compress(b"new input"))
            checksum = root / "il2cpp_dump.json.gz.sha256"
            checksum.write_text("0" * 64 + "  il2cpp_dump.json.gz\n")
            args = argparse.Namespace(
                repo="owner/repo",
                tag="build-data",
                asset=None,
                output=output,
                work_dir=root,
            )
            with patch.object(
                upload_il2cpp, "download_asset", side_effect=[asset, checksum]
            ):
                with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                    upload_il2cpp.download_command(args)
            self.assertEqual(output.read_bytes(), b"previous input")

    def test_broken_gzip_never_replaces_existing_dump(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            asset, output = root / "bad.gz", root / "il2cpp_dump.json"
            asset.write_bytes(gzip.compress(b"new input")[:-5])
            output.write_bytes(b"previous input")
            with patch.object(upload_il2cpp, "DEFAULT_WORK_DIR", root / "cache"):
                with self.assertRaises((EOFError, gzip.BadGzipFile)):
                    upload_il2cpp.decompress_file(asset, output)
            self.assertEqual(output.read_bytes(), b"previous input")

    def test_build_release_does_not_become_latest(self):
        missing = subprocess.CompletedProcess(
            [], 1, stdout="", stderr="release not found"
        )
        with patch.object(
            upload_il2cpp, "run_command", return_value=missing
        ), patch.object(upload_il2cpp, "run_release_notes_command") as publish:
            upload_il2cpp.ensure_release(
                "owner/repo", "build-data", "Build data", "notes"
            )
        self.assertIn("--latest=false", publish.call_args.args[0])

    def test_repo_detection_supports_reference_remote_formats(self):
        for remote in (
            "https://github.com/owner/repo.git",
            "git@github.com:owner/repo.git",
            "ssh://git@github.com/owner/repo.git",
        ):
            self.assertEqual(upload_il2cpp.parse_github_remote(remote), "owner/repo")


if __name__ == "__main__":
    unittest.main()
