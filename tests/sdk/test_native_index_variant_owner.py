"""Fresh discovery includes a variant's own slots as well as shared combat."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.native.evidence import method_rows
from sdk.enemy_logic_exporter.shared.workflow import batch


class VariantOwnerIndexTests(unittest.TestCase):
    def test_shared_combat_owner_keeps_own_repel_methods_in_fresh_index(self):
        combat = "app.Em0001_00_BTable_Combat_Export"
        repel = "app.Em0001_50_BTable_Repel_Export"

        class Metadata:
            _objects = {
                combat: {"methods": {"table_combat123": {"function": "1000"}}},
                repel: {
                    "methods": {
                        "table_repel456": {"function": "2000"},
                        "updateTableInpl457": {"function": "3000"},
                    }
                },
                "app.Em0009_00_BTable_Life_Export": {
                    "methods": {"table_other888": {"function": "4000"}}
                },
            }

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def get(self, name):
                return self._objects.get(name)

        class Image:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def end(self, address):
                return address + 1

            def read(self, address, size):
                return b"\xc3" * size

        with tempfile.TemporaryDirectory() as directory, patch.object(
            batch,
            "iter_monsters",
            return_value=(
                SimpleNamespace(NATIVE_OWNER="Em0001_00", ENEMY_ID="EM0001_50_0"),
            ),
        ), patch.object(batch, "Il2cppMetadata", return_value=Metadata()), patch.object(
            batch, "PE", return_value=Image()
        ), patch.object(
            batch, "address_catalog", return_value={}
        ), patch.object(
            batch, "in_tmp", return_value=True
        ):
            index = batch.export_native_index(
                "fixture.exe", "fixture.json", Path(directory) / "index.json"
            )
        identities = {(row["type"], row["method"]) for row in method_rows(index)}
        self.assertEqual(
            identities,
            {
                (combat, "table_combat123"),
                (repel, "table_repel456"),
                (repel, "updateTableInpl457"),
            },
        )


if __name__ == "__main__":
    unittest.main()
