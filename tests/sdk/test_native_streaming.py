"""Check compressed resume identity without importing Ghidra in normal tests."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.evidence import pack_methods, method_rows
from sdk.enemy_logic_exporter.streaming import extract_cached, _read_cache, _write_cache

ROOT = Path(__file__).resolve().parents[2]


class StreamingTests(unittest.TestCase):
    def test_cached_shared_body_preserves_both_method_contexts(self):
        scratch = ROOT / ".agents/test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        profile = dict(
            exeSha256="a" * 64, metadataSha256="b" * 64, gameVersion="fixture"
        )
        body = dict(
            address="0x1000",
            end="0x1010",
            nativeSha256="c" * 64,
            addressAliases=[["a", "x"], ["b", "y"]],
            fields={},
            parameters=[],
            label="fixture",
        )
        rows = [dict(body, type="a", method="x"), dict(body, type="b", method="y")]
        manifest = pack_methods(rows, profile)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            work = Path(directory)
            reuse = work / "reuse.json"
            reuse.write_text(
                json.dumps(
                    pack_methods(
                        [
                            dict(
                                rows[0],
                                completed=True,
                                code="return false;",
                                controlFlow={
                                    "status": "unreviewed_native_control_flow"
                                },
                            )
                        ],
                        profile,
                    )
                ),
                encoding="utf8",
            )
            with patch(
                "sdk.enemy_logic_exporter.streaming.digest",
                return_value=profile["exeSha256"],
            ), patch("sdk.enemy_logic_exporter.streaming.verify_rows"):
                first = extract_cached(
                    manifest,
                    "fixture.exe",
                    work / "cache",
                    work / "project",
                    "unused",
                    reuse=[reuse],
                )
                second = extract_cached(
                    manifest, "fixture.exe", work / "cache", work / "project", "unused"
                )
            self.assertEqual(first["completedBodies"], 1)
            self.assertEqual(second["pendingBodies"], 0)
            self.assertFalse(second["semanticReviewCompleted"])
            index = json.loads((work / "cache/index.json").read_text(encoding="utf8"))
            self.assertEqual(method_rows(index), rows)
            self.assertEqual(len(index["nativeBodyArtifacts"]), 1)

    def test_cache_from_another_version_is_rejected(self):
        scratch = ROOT / ".agents/test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / "body.json.gz"
            row = dict(address="0x1000", end="0x1010", nativeSha256="c" * 64)
            _write_cache(path, dict(row, profile={"gameVersion": "old"}))
            with self.assertRaisesRegex(ValueError, "版本"):
                _read_cache(path, row, {"gameVersion": "new"})
