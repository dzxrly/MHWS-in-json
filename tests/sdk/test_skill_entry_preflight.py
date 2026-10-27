"""Selected entry jumps must have readable targets in the supplied dump."""

import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from capstone import CS_ARCH_X86, CS_MODE_64, Cs

from sdk.skill_effect_exporter.shared.native.scan import NativeIndex
from sdk.skill_effect_exporter.shared.workflow import cli
from sdk.skill_effect_exporter.shared.workflow.context import SkillContext

BASE = 0x140001000
SECOND = BASE + 0x100
OUTSIDE = BASE - 0x2000


def jump(source, target):
    return b"\xe9" + struct.pack("<i", target - source - 5)


class FakePE:
    def __init__(self, code, *, zero_filled=()):
        self.code = code
        self.zero_filled = set(zero_filled)

    def contains(self, address):
        return address in self.zero_filled or any(
            start <= address < start + len(code) for start, code in self.code.items()
        )

    def read(self, address, size):
        for start, code in self.code.items():
            if start <= address < start + len(code):
                offset = address - start
                return code[offset : offset + size]
        return b""

    def end(self, address):
        return address + len(self.code[address])


class SkillEntryPreflightTests(unittest.TestCase):
    def context(self, code, *, selected=None, zero_filled=()):
        context = SkillContext.__new__(SkillContext)
        context.only = selected or set()
        context.plan = {
            "SkillA": [("function", BASE, "SkillA", [], None)],
            "SkillB": [("function", SECOND, "SkillB", [], None)],
        }
        index = NativeIndex.__new__(NativeIndex)
        index.pe = FakePE(code, zero_filled=zero_filled)
        index.cs = Cs(CS_ARCH_X86, CS_MODE_64)
        index.cs.detail = True
        index.catalog = {
            BASE: [("Fixture", "entry1")],
            SECOND: [("Fixture", "other2")],
        }
        index.metadata = {
            "Fixture": {
                "methods": {
                    "entry1": {"function": hex(BASE)},
                    "other2": {"function": hex(SECOND)},
                }
            }
        }
        context.index = index
        return context

    def test_selected_external_entry_reports_identity_and_addresses(self):
        context = self.context(
            {BASE: jump(BASE, OUTSIDE), SECOND: b"\xc3"}, selected={"SkillA"}
        )
        with self.assertRaises(ValueError) as raised:
            context.preflight_entries({})
        message = str(raised.exception)
        for detail in ("dump", "Fixture.entry1", hex(BASE), hex(OUTSIDE)):
            self.assertIn(detail, message)

    def test_mapped_but_unreadable_target_is_rejected(self):
        context = self.context(
            {BASE: jump(BASE, SECOND)},
            selected={"SkillA"},
            zero_filled={SECOND},
        )
        with self.assertRaisesRegex(ValueError, hex(SECOND)):
            context.preflight_entries({})

    def test_readable_internal_tail_jump_is_allowed(self):
        context = self.context({BASE: jump(BASE, SECOND), SECOND: b"\xc3"})
        context.preflight_entries({})

    def test_non_jump_entry_does_not_make_later_unknown_paths_fatal(self):
        context = self.context(
            {BASE: b"\x90" + jump(BASE + 1, OUTSIDE), SECOND: b"\xc3"}
        )
        context.preflight_entries({})

    def test_indirect_entry_jump_remains_an_unknown_runtime_path(self):
        context = self.context({BASE: b"\xff\xe0", SECOND: b"\xc3"})
        context.preflight_entries({})

    def test_unselected_plans_and_declarations_do_not_block(self):
        context = self.context(
            {BASE: b"\xc3", SECOND: jump(SECOND, OUTSIDE)}, selected={"SkillA"}
        )
        context.preflight_entries(
            {
                "SkillB": SimpleNamespace(
                    DECLARED_METHODS=[("Fixture", "other", "proof")]
                )
            }
        )

    def test_selected_declared_method_is_checked_even_without_planned_link(self):
        context = self.context(
            {BASE: b"\xc3", SECOND: jump(SECOND, OUTSIDE)}, selected={"SkillA"}
        )
        with self.assertRaisesRegex(ValueError, "Fixture.other2"):
            context.preflight_entries(
                {
                    "SkillA": SimpleNamespace(
                        DECLARED_METHODS=[("Fixture", "other", "proof")]
                    )
                }
            )

    def test_all_missing_selected_entries_are_reported(self):
        context = self.context(
            {BASE: jump(BASE, OUTSIDE), SECOND: jump(SECOND, OUTSIDE + 1)}
        )
        with self.assertRaises(ValueError) as raised:
            context.preflight_entries({})
        self.assertIn("Fixture.entry1", str(raised.exception))
        self.assertIn("Fixture.other2", str(raised.exception))

    def test_cli_fails_before_evaluation_and_output_writer(self):
        context = self.context(
            {BASE: jump(BASE, OUTSIDE), SECOND: b"\xc3"}, selected={"SkillA"}
        )
        module = SimpleNamespace(extract=Mock(), extract_parameters=Mock())
        args = SimpleNamespace(
            command="extract",
            skill=["SkillA"],
            exe=Path("dump.exe"),
            il2cpp=Path("metadata.json"),
            natives=Path("natives"),
            output=Path("existing-output"),
            all_links=False,
        )
        with (
            patch.object(cli, "parser") as parser,
            patch("sdk.skill_effect_exporter.shared.workflow.extract.PE"),
            patch("sdk.skill_effect_exporter.shared.workflow.extract.Il2cppMetadata"),
            patch(
                "sdk.skill_effect_exporter.shared.workflow.context.SkillContext",
                return_value=context,
            ),
            patch("sdk.skill_effect_exporter.skills.entry", return_value=module),
            patch(
                "sdk.skill_effect_exporter.shared.workflow.shards.write_shards"
            ) as write,
        ):
            parser.return_value.parse_args.return_value = args
            with self.assertRaisesRegex(ValueError, "Fixture.entry1"):
                cli.main()
        module.extract.assert_not_called()
        module.extract_parameters.assert_not_called()
        write.assert_not_called()
