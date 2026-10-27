"""Migrate bytes only after whole-function proof; report uncovered locations."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.config import EVIDENCE_DIR, TMP_DIR
from sdk.enemy_logic_exporter.shared.native.symbols import (
    DIGEST_SCHEME,
    normalized_digest,
)
from sdk.enemy_logic_exporter.shared.workflow import version_update as update

OLD_CODE = "8b0500100000e8f00f0000c3"
NEW_CODE = "8b0534120000e8aa220000c3"


class Image:
    def __init__(self, base, code, *, function_length=None):
        self.base = base
        self.code = bytes.fromhex(code)
        self.function_length = (
            len(self.code) if function_length is None else function_length
        )

    def read(self, address, size):
        offset = address - self.base
        return self.code[offset : offset + size]

    def end(self, address):
        return self.base + self.function_length

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Metadata:
    def __init__(self, owner="app.T", method="f2", address=0x5000):
        self.owner, self.method, self.address = owner, method, address

    def get(self, name):
        return (
            dict(methods={self.method: dict(function=hex(self.address)[2:])})
            if name == self.owner
            else None
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class EvidenceMigrationTests(unittest.TestCase):
    def setUp(self):
        work = TMP_DIR / "enemy-logic-exporter/promotion"
        work.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.evidence = self.root / "evidence.json"
        self.old = self.root / "old.json"
        self.new = self.root / "new.json"
        self.monsters = self.root / "monster"
        self.monsters.mkdir()

    def write(self, path, data):
        path.write_text(json.dumps(data), encoding="utf8")

    def read(self, path):
        return json.loads(path.read_text(encoding="utf8"))

    def prepare(self, *, row_length=12, bytes_value=None, extra=None):
        row = dict(
            type="app.T",
            method="f1",
            address="0x1000",
            end=hex(0x1000 + row_length),
            nativeBytes=(
                bytes_value if bytes_value is not None else OLD_CODE[: row_length * 2]
            ),
        )
        self.write(self.evidence, dict(methods=[row], **(extra or {})))
        old = Image(0x1000, OLD_CODE)
        self.write(
            self.old,
            dict(
                digestScheme=DIGEST_SCHEME,
                evidenceDigests={
                    "app.T::f1": dict(
                        address="0x1000",
                        rowLength=row_length,
                        functionLength=12,
                        normalizedSha256=normalized_digest(
                            old, 0x1000, names=lambda address: "M:app.A.f()"
                        ),
                    )
                },
            ),
        )
        self.write(self.new, dict(digestScheme=DIGEST_SCHEME, evidenceDigests={}))

    def migrate(
        self,
        *,
        code=NEW_CODE,
        apply=True,
        callee="M:app.A.f()",
        documents=None,
        metadata=None,
        function_length=None
    ):
        metadata = metadata or Metadata()
        with patch.object(
            update,
            "PE",
            return_value=Image(metadata.address, code, function_length=function_length),
        ), patch.object(update, "Il2cppMetadata", return_value=metadata), patch.object(
            update, "address_catalog", return_value={}
        ), patch.object(
            update, "CallNames", return_value=lambda address: callee
        ), patch.object(
            update, "evidence_documents", return_value=documents or [self.evidence]
        ), patch.object(
            update, "MONSTER_MODULE_DIR", self.monsters
        ):
            return update.migrate_evidence(
                "unused.exe", "unused.json", self.old, self.new, apply=apply
            )

    def test_relocation_refreshes_raw_bytes_after_stable_whole_function_proof(self):
        self.prepare()
        report = self.migrate()
        row = self.read(self.evidence)["methods"][0]
        self.assertEqual(
            (row["method"], row["address"], row["end"]), ("f2", "0x5000", "0x500c")
        )
        self.assertEqual(row["nativeBytes"], NEW_CODE)
        self.assertEqual(report["nativeBytesRefreshed"], 1)
        self.assertEqual(report["migrated"], 1)
        self.assertTrue(report["applied"])
        self.assertEqual(report["review"], [])

    def test_refresh_keeps_row_prefix_length_instead_of_copying_whole_function(self):
        self.prepare(row_length=6)
        report = self.migrate()
        row = self.read(self.evidence)["methods"][0]
        self.assertEqual(row["end"], "0x5006")
        self.assertEqual(row["nativeBytes"], NEW_CODE[:12])
        self.assertEqual(report["nativeBytesRefreshed"], 1)
        self.assertEqual(
            self.read(self.new)["evidenceDigests"]["app.T::f2"]["functionLength"], 12
        )
        self.assertNotIn(
            "rowVariants", self.read(self.new)["evidenceDigests"]["app.T::f2"]
        )

    def test_existing_bytes_field_refreshes_after_proof_and_keeps_prefix_length(self):
        for row_length in (6, 12):
            with self.subTest(row_length=row_length):
                self.prepare(row_length=row_length)
                document = self.read(self.evidence)
                row = document["methods"][0]
                row["bytes"] = row.pop("nativeBytes")
                self.write(self.evidence, document)
                before = self.evidence.read_bytes(), self.new.read_bytes()
                preview = self.migrate(apply=False)
                self.assertEqual(preview["bytesRefreshed"], 1)
                self.assertEqual(preview["nativeBytesRefreshed"], 0)
                self.assertEqual(
                    (self.evidence.read_bytes(), self.new.read_bytes()), before
                )
                report = self.migrate()
                row = self.read(self.evidence)["methods"][0]
                self.assertEqual(row["bytes"], NEW_CODE[: row_length * 2])
                self.assertNotIn("nativeBytes", row)
                self.assertEqual(row["end"], hex(0x5000 + row_length))
                self.assertEqual(report["bytesRefreshed"], 1)
                self.assertEqual(report["nativeBytesRefreshed"], 0)
                self.assertEqual(report["review"], [])

    def test_both_existing_byte_fields_are_counted_and_refreshed_separately(self):
        self.prepare()
        document = self.read(self.evidence)
        document["methods"][0]["bytes"] = OLD_CODE
        self.write(self.evidence, document)
        report = self.migrate()
        row = self.read(self.evidence)["methods"][0]
        self.assertEqual(row["nativeBytes"], NEW_CODE)
        self.assertEqual(row["bytes"], NEW_CODE)
        self.assertEqual(report["nativeBytesRefreshed"], 1)
        self.assertEqual(report["bytesRefreshed"], 1)
        self.assertEqual(report["migrated"], 1)

    def test_invalid_bytes_field_does_not_refresh_either_field_or_authorize_range(self):
        for invalid in ("c3", OLD_CODE + "90", "not hex", None):
            with self.subTest(invalid=invalid):
                self.prepare()
                document = self.read(self.evidence)
                document["methods"][0]["bytes"] = invalid
                self.write(self.evidence, document)
                before = self.evidence.read_bytes()
                report = self.migrate()
                self.assertIn("长度", report["review"][0]["reason"])
                self.assertEqual(report["review"][0]["fields"], ["bytes"])
                self.assertEqual(report["nativeBytesRefreshed"], 0)
                self.assertEqual(report["bytesRefreshed"], 0)
                self.assertEqual(report["migrated"], 0)
                self.assertEqual(self.evidence.read_bytes(), before)

    def test_bytes_field_cannot_hide_changed_function_tail_or_callee(self):
        for code, callee in (
            ("8b0534120000b801000000c3", "M:app.A.f()"),
            (NEW_CODE, "M:app.B.g()"),
        ):
            with self.subTest(code=code, callee=callee):
                self.prepare(row_length=6)
                document = self.read(self.evidence)
                row = document["methods"][0]
                row["bytes"] = row.pop("nativeBytes")
                self.write(self.evidence, document)
                before = self.evidence.read_bytes()
                report = self.migrate(code=code, callee=callee)
                self.assertTrue(report["review"])
                self.assertEqual(report["bytesRefreshed"], 0)
                self.assertEqual(self.evidence.read_bytes(), before)

    def test_same_method_in_two_documents_keeps_both_authorized_prefix_lengths(self):
        self.prepare(row_length=6)
        other = self.root / "long.json"
        short = self.read(self.evidence)["methods"][0]
        self.write(
            other, dict(methods=[dict(short, end="0x100c", nativeBytes=OLD_CODE)])
        )
        documents = [self.evidence, other]
        with patch.object(update, "evidence_documents", return_value=documents):
            digests = update.evidence_digests(
                Image(0x1000, OLD_CODE), Metadata(), lambda _: "M:app.A.f()"
            )
        records = digests["app.T::f1"]["rowVariants"]
        self.assertEqual([row["rowLength"] for row in records], [6, 12])
        self.assertTrue(all(row["functionLength"] == 12 for row in records))
        self.assertEqual(len({row["normalizedSha256"] for row in records}), 1)
        self.write(self.old, dict(digestScheme=DIGEST_SCHEME, evidenceDigests=digests))
        report = self.migrate(documents=documents)
        self.assertEqual(report["review"], [])
        self.assertEqual(report["nativeBytesRefreshed"], 2)
        self.assertEqual(
            self.read(self.evidence)["methods"][0]["nativeBytes"], NEW_CODE[:12]
        )
        self.assertEqual(self.read(other)["methods"][0]["nativeBytes"], NEW_CODE)
        migrated = self.read(self.new)["evidenceDigests"]["app.T::f2"]["rowVariants"]
        self.assertEqual([row["rowLength"] for row in migrated], [6, 12])
        self.assertTrue(all(row["address"] == "0x5000" for row in migrated))
        # Recomputing after migration must preserve the same two ranges too.
        with patch.object(update, "evidence_documents", return_value=documents):
            refreshed = update.evidence_digests(
                Image(0x5000, NEW_CODE), Metadata(), lambda _: "M:app.A.f()"
            )
        self.assertEqual(refreshed["app.T::f2"]["rowVariants"], migrated)

    def test_duplicate_same_range_is_not_a_second_variant(self):
        self.prepare(row_length=6)
        document = self.read(self.evidence)
        document["methods"].append(dict(document["methods"][0]))
        self.write(self.evidence, document)
        with patch.object(update, "evidence_documents", return_value=[self.evidence]):
            digests = update.evidence_digests(
                Image(0x1000, OLD_CODE), Metadata(), lambda _: "M:app.A.f()"
            )
        self.assertNotIn("rowVariants", digests["app.T::f1"])

    def test_current_vec3_addition_receipts_keep_short_and_full_ranges(self):
        rows = []
        for filename in [
            "target_command_effects.v1.json",
            "em0150_wall_target.v1.json",
        ]:
            proof = self.read(EVIDENCE_DIR / filename)
            rows.append(
                next(
                    row
                    for row in proof["methods"]
                    if row["type"] == "via.vec3" and row["method"] == "op_Addition1752"
                )
            )
        rows.sort(key=lambda row: int(row["end"], 16) - int(row["address"], 16))
        short, full = rows
        start = int(short["address"], 16)
        self.assertEqual(short["address"], full["address"])
        lengths = [int(row["end"], 16) - start for row in rows]
        self.assertLess(*lengths)
        documents = [self.evidence, self.root / "wall.json"]
        for path, row in zip(documents, rows):
            self.write(path, dict(methods=[row]))
        metadata = Metadata("via.vec3", "op_Addition1752", start)
        with patch.object(update, "evidence_documents", return_value=documents):
            digests = update.evidence_digests(
                Image(start, full["nativeBytes"], function_length=lengths[0]),
                metadata,
                lambda _: "unused",
            )
        self.write(self.old, dict(digestScheme=DIGEST_SCHEME, evidenceDigests=digests))
        self.write(self.new, dict(digestScheme=DIGEST_SCHEME, evidenceDigests={}))
        moved = Metadata("via.vec3", "op_Addition999999", start + 0x1000)
        report = self.migrate(
            code=full["nativeBytes"],
            metadata=moved,
            documents=documents,
            function_length=lengths[0],
        )
        self.assertEqual(report["review"], [])
        variants = self.read(self.new)["evidenceDigests"][
            "via.vec3::op_Addition999999"
        ]["rowVariants"]
        self.assertEqual([row["rowLength"] for row in variants], lengths)
        self.assertEqual([row["functionLength"] for row in variants], lengths)
        for path, old_row in zip(documents, rows):
            actual = self.read(path)["methods"][0]
            self.assertEqual(actual["nativeBytes"], old_row["nativeBytes"])
            self.assertEqual(
                int(actual["end"], 16) - int(actual["address"], 16),
                int(old_row["end"], 16) - start,
            )

    def test_legacy_profile_does_not_authorize_an_unregistered_longer_row(self):
        for has_bytes in (True, False):
            self.prepare(row_length=6)
            row = self.read(self.evidence)["methods"][0]
            row.update(end="0x100c", nativeBytes=OLD_CODE)
            if not has_bytes:
                row.pop("nativeBytes")
            self.write(self.evidence, dict(methods=[row]))
            before = self.evidence.read_bytes()
            report = self.migrate()
            pending = report["review"][0]
            self.assertIn("未登记该证据行范围", pending["reason"])
            self.assertEqual(pending["rowLength"], 12)
            self.assertEqual(
                pending["availableRanges"],
                [dict(address="0x1000", end="0x1006", rowLength=6)],
            )
            self.assertEqual(report["nativeBytesRefreshed"], 0)
            self.assertEqual(self.evidence.read_bytes(), before)

    def test_unregistered_old_address_cannot_borrow_another_ranges_proof(self):
        self.prepare()
        document = self.read(self.evidence)
        document["methods"][0].update(address="0x2000", end="0x200c")
        self.write(self.evidence, document)
        report = self.migrate()
        self.assertIn("未登记该证据行范围", report["review"][0]["reason"])

    def test_changed_tail_cannot_be_hidden_by_refreshing_the_row_prefix(self):
        self.prepare(row_length=6)
        before = self.evidence.read_bytes()
        report = self.migrate(code="8b0534120000b801000000c3")
        self.assertTrue(report["review"])
        self.assertEqual(report["nativeBytesRefreshed"], 0)
        self.assertEqual(self.evidence.read_bytes(), before)

    def test_grown_function_or_retargeted_callee_is_not_refreshed(self):
        for code, callee in (
            (NEW_CODE + "90", "M:app.A.f()"),
            (NEW_CODE, "M:app.B.g()"),
        ):
            self.prepare()
            before = self.evidence.read_bytes()
            report = self.migrate(code=code, callee=callee)
            self.assertTrue(report["review"])
            self.assertEqual(report["nativeBytesRefreshed"], 0)
            self.assertEqual(self.evidence.read_bytes(), before)

    def test_invalid_old_byte_length_is_reviewed_instead_of_silently_repaired(self):
        self.prepare(bytes_value="c3")
        before = self.evidence.read_bytes()
        report = self.migrate()
        self.assertIn("长度", report["review"][0]["reason"])
        self.assertEqual(self.evidence.read_bytes(), before)

    def test_preview_counts_pending_refresh_without_writing_files(self):
        self.prepare()
        before = self.evidence.read_bytes(), self.new.read_bytes()
        report = self.migrate(apply=False)
        self.assertFalse(report["applied"])
        self.assertEqual(report["nativeBytesRefreshed"], 1)
        self.assertEqual((self.evidence.read_bytes(), self.new.read_bytes()), before)

    def test_uncovered_json_dependencies_remain_explicit_when_review_is_empty(self):
        extras = dict(
            constants=[dict(address="0x2000", end="0x2004", nativeBytes="0000803f")],
            nativeProofs=[dict(address="0x3000", end="0x3001", bytes="c3")],
            classSymbols=[dict(type="app.T", slot="0x4000")],
        )
        self.prepare(extra=extras)
        report = self.migrate()
        self.assertEqual(report["review"], [])
        self.assertEqual(report["coverage"]["status"], "partial")
        self.assertEqual(report["coverage"]["unsupportedDependencyCount"], 3)
        self.assertEqual(
            {row["kind"] for row in report["unsupportedDependencies"]},
            {"constant_address", "native_fragment", "class_symbol_slot"},
        )
        self.assertEqual(
            {row["path"] for row in report["unsupportedDependencies"]},
            {"/constants/0", "/nativeProofs/0", "/classSymbols/0"},
        )
        document = self.read(self.evidence)
        for key, value in extras.items():
            self.assertEqual(document[key], value)

    def test_native_proofs_with_standard_identity_are_not_misclassified(self):
        row = dict(type="app.T", method="f1", address="0x1000", end="0x100c")
        self.assertEqual(
            update._uncovered_json_dependencies(
                dict(nativeProofs=[row]), self.evidence
            ),
            [],
        )

    def test_python_ranges_and_name_pairs_are_reported_without_import_execution(self):
        self.prepare()
        marker = self.root / "imported.txt"
        source = (
            "from pathlib import Path\nPath("
            + repr(str(marker))
            + ").write_text('executed')\nTYPE = 'app.T'\nFULL = dict(type=TYPE, method='f1', address='0x1000', end='0x100c')\nRAW = dict(method='g1', address='0x2000', end='0x2008')\nNAMES = {('app.T', 'f1')}\n"
        )
        path = self.monsters / "sample.py"
        path.write_text(source, encoding="utf8")
        report = self.migrate()
        self.assertFalse(marker.exists())
        rows = report["unsupportedDependencies"]
        self.assertEqual(
            {row["kind"] for row in rows},
            {"python_method_range", "python_native_range", "python_method_name"},
        )
        self.assertEqual({row["line"] for row in rows}, {4, 5, 6})
        self.assertTrue(all(row["file"].endswith("sample.py") for row in rows))
        self.assertEqual(path.read_text(encoding="utf8"), source)


if __name__ == "__main__":
    unittest.main()
