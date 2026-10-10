"""x64 field-formula recognizer: helper inlining, partial paths, static constants."""

import struct
import unittest

from sdk.enemy_logic_exporter.shared.logic import native_formula as N
from sdk.enemy_logic_exporter.shared.logic.formula import Unsupported, instantiate

COMMAND, HELPER, CCTOR = 0x141000000, 0x141000100, 0x141000200


def assemble(parts, base):
    """Bytes for ``parts``: raw bytes, a label name, or (opcode, label) short jumps."""
    labels, at = {}, base
    for part in parts:
        if isinstance(part, str):
            labels[part] = at
        else:
            at += 2 if isinstance(part, tuple) else len(part)
    out, at = b"", base
    for part in parts:
        if isinstance(part, str):
            continue
        if isinstance(part, tuple):
            out += bytes([part[0], (labels[part[1]] - at - 2) & 0xFF])
            at += 2
        else:
            out += part
            at += len(part)
    return out


class FakePE:
    def __init__(self, functions):
        self.functions = functions

    def read(self, address, size):
        for start, code in self.functions.items():
            if start <= address < start + len(code):
                return code[address - start : address - start + size]
        return b""

    def end(self, address):
        for start, code in self.functions.items():
            if start <= address < start + len(code):
                return start + len(code)
        return address + 16

    def read_only(self, address, size):
        return False


class Metadata:
    FIELDS = {
        "app.cEnemyContext": {
            "Target": {"offset_from_base": "0x100", "type": "app.cEmModuleTarget"},
            "_IsBusy": {"offset_from_base": "0x60", "type": "System.Boolean"},
            "_Count": {"offset_from_base": "0x64", "type": "System.Int32"},
        },
        "app.cEmModuleTarget": {
            "_Mode": {"offset_from_base": "0x50", "type": "System.Int32"},
            "_Key": {"offset_from_base": "0x58", "type": "app.KEY"},
        },
        "app.KEY": {
            "Category": {"offset_from_base": "0x10", "type": "System.Int32"},
            "Index": {"offset_from_base": "0x14", "type": "System.Int32"},
            "INVALID": {"offset_from_base": "0x10", "type": "app.KEY"},
        },
        "app.ModeArg": {
            "_EditType": {
                "offset_from_base": "0x10",
                "type": "ace.btable.cEditFieldEnum",
            },
            "_EditTypeDefault": {
                "offset_from_base": "0x10",
                "type": "ace.btable.cEditFieldEnum",
            },
        },
    }
    TYPES = {
        "app.KEY": {
            "parent": "System.ValueType",
            "size": "0x18",
            "fields": FIELDS["app.KEY"],
            "methods": {".cctor1": {"function": f"{CCTOR:x}"}},
        }
    }

    def fields(self, name):
        return self.FIELDS.get(name, {})

    def get(self, name):
        return self.TYPES.get(name)

    def enum(self, name):
        return None, {}


ROW = dict(
    type="app.btable.EmCommonCommand.cCheckTest",
    method="onExecute1",
    address=hex(COMMAND),
    end=hex(COMMAND + 0x40),
    parameters=[{"type": "ace.btable.cCommandWork"}, {"type": "app.ModeArg"}],
)
# rax = work.Accessor.ContextHolder.Em (cEnemyContext)
CONTEXT = [
    bytes.fromhex("498b4028"),  # mov rax, [r8+0x28]
    bytes.fromhex("488b4068"),  # mov rax, [rax+0x68]
    bytes.fromhex("488b4040"),  # mov rax, [rax+0x40]
]


class NativeFormulaTests(unittest.TestCase):
    def leaf(self, functions, partial=False):
        return N.recover_native_formula_leaf(
            ROW, Metadata(), FakePE(functions), partial=partial
        )

    def test_getter_is_expanded_with_the_registers_it_receives(self):
        command = assemble(
            [
                bytes.fromhex("4d85c0"),  # test r8, r8
                (0x74, "zero"),  # je zero
                bytes.fromhex("4c89c1"),  # mov rcx, r8
                b"\xe8" + struct.pack("<i", HELPER - (COMMAND + 13)),  # call getter
                bytes.fromhex("8b4050"),  # mov eax, [rax+0x50]
                bytes.fromhex("498b5110"),  # mov rdx, [r9+0x10]
                bytes.fromhex("3b4210"),  # cmp eax, [rdx+0x10]
                bytes.fromhex("0f94c0c3"),  # sete al; ret
                "zero",
                bytes.fromhex("31c0c3"),  # xor eax, eax; ret
            ],
            COMMAND,
        )
        getter = bytes.fromhex("488b4128488b4068488b4040488b8000010000c3")
        rule = self.leaf({COMMAND: command, HELPER: getter})
        self.assertEqual(rule["semanticStatus"], "native_x64_field_formula_recovered")
        test = rule["formula"]["items"][-1]
        self.assertEqual(test["left"]["key"], "context:Target._Mode")
        # The static default shares the offset; the resource decides.
        self.assertEqual(
            test["right"], dict(kind="argument", field="_EditType|_EditTypeDefault")
        )
        self.assertEqual(rule["inlinedHelpers"][0]["address"], hex(HELPER))
        bound = instantiate(rule["formula"], {"_EditType": "[2] B"})
        self.assertEqual(bound["items"][-1]["right"], dict(kind="constant", value=2))
        self.assertIsNone(
            instantiate(rule["formula"], {"_EditType": 1, "_EditTypeDefault": 0})
        )

    def test_unverifiable_path_stays_unknown_only_in_partial_mode(self):
        command = assemble(
            [
                bytes.fromhex("4d85c0"),
                (0x74, "zero"),
                *CONTEXT,
                bytes.fromhex("80786000"),  # cmp byte [rax+0x60], 0
                (0x75, "lookup"),  # jne lookup
                bytes.fromhex("83786401"),  # cmp dword [rax+0x64], 1
                bytes.fromhex("0f94c0c3"),
                "lookup",
                bytes.fromhex("48634864"),  # movsxd rcx, dword [rax+0x64]
                bytes.fromhex("8a440870c3"),  # mov al, [rax+rcx+0x70]; ret
                "zero",
                bytes.fromhex("31c0c3"),
            ],
            COMMAND,
        )
        self.assertIsNone(self.leaf({COMMAND: command}))
        rule = self.leaf({COMMAND: command}, partial=True)
        self.assertEqual(rule["semanticStatus"], "native_x64_field_formula_partial")
        self.assertEqual(rule["unknownPaths"], ["变量索引"])
        text = str(rule["formula"])
        self.assertIn("context:_Count", text)
        self.assertIn("'kind': 'unknown'", text)

    def test_unsigned_compare_keeps_the_sign_condition(self):
        command = assemble(
            [
                *CONTEXT,
                bytes.fromhex("83786408"),
                bytes.fromhex("0f92c0c3"),
            ],  # cmp; setb
            COMMAND,
        )
        items = self.leaf({COMMAND: command})["formula"]["items"]
        self.assertEqual(
            [(i["operator"], i["right"]["value"]) for i in items],
            [("ge", 0), ("lt", 8)],
        )

    def test_heap_write_rejects_the_whole_command(self):
        command = assemble(
            [*CONTEXT, bytes.fromhex("c6406001"), bytes.fromhex("b001c3")], COMMAND
        )
        with self.assertRaises(N.Fatal):
            N.evaluate(FakePE({COMMAND: command}), COMMAND, partial=True)

    def test_static_constant_needs_a_straight_line_cctor(self):
        target = CCTOR + 0x1000
        store = (
            bytes.fromhex("48c705")
            + struct.pack("<i", target - (CCTOR + 11))
            + struct.pack("<i", -1)
        )
        pe = FakePE({CCTOR: store + b"\xc3"})
        value, source = N.static_constant(Metadata(), pe, "app.KEY", target + 4, 4)
        self.assertEqual((value, source["field"]), (0xFFFFFFFF, "INVALID"))
        branching = FakePE({CCTOR: bytes.fromhex("7400") + store + b"\xc3"})
        self.assertIsNone(
            N.static_constant(Metadata(), branching, "app.KEY", target, 4)
        )

    def test_negative_constants_are_not_signed_twice(self):
        from sdk.enemy_logic_exporter.shared.logic.formula import _signed

        self.assertEqual((_signed(0xFFFFFFFF, 4), _signed(-1, 4)), (-1, -1))

    def test_wide_read_of_two_fields_is_split(self):
        namer = N.NativeNamer(
            Metadata(), ROW, ("param", "param_3"), ("param", "param_4")
        )
        target = (
            "load",
            8,
            ("load", 8, ("load", 8, ("param", "param_3"), 0x28), 0x68),
            0x40,
        )
        key = ("load", 8, ("load", 8, target, 0x100), 0x58)
        split = N.split_wide(("cmp", "!=", key, ("const", 0xFFFFFFFEFFFFFFFF)), namer)
        self.assertEqual(split[0], "or")
        self.assertEqual([p[3][1] for p in split[1]], [0xFFFFFFFF, 0xFFFFFFFE])
        with self.assertRaises(Unsupported):
            N.split_wide(("cmp", "<", key, ("const", 3)), namer)

    def test_constant_comparisons_are_decided(self):
        self.assertEqual(
            N._fold(("cmp", "==", ("const", 0), ("const", 0))), ("const", True)
        )
        with self.assertRaises(Unsupported):
            N._mask_zero(("load", 4, ("param", "param_3"), 0), ("const", 6))


if __name__ == "__main__":
    unittest.main()
