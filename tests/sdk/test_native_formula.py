"""x64 field-formula recognizer: helper inlining, partial paths, static constants."""

import struct
import unittest

from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.formula import (
    Unsupported,
    _expression,
    instantiate,
)

from sdk.enemy_logic_exporter.shared.logic import native_formula as N

COMMAND, HELPER, CCTOR = 0x141000000, 0x141000100, 0x141000200
OVERRIDE = 0x141000300
POINTS = "System.Collections.Generic.List`1<app.Point>"


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
            "_Points": {"offset_from_base": "0x68", "type": POINTS},
        },
        POINTS: {
            "_items": {"offset_from_base": "0x10", "type": "app.Point[]"},
            "s_emptyArray": {"offset_from_base": "0x10", "type": "app.Point[]"},
            "_size": {"offset_from_base": "0x18", "type": "System.Int32"},
        },
        "app.Point": {
            "_Flags": {"offset_from_base": "0x30", "type": "System.UInt64"},
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
        "app.SwitchArg": {
            "_Kind": {
                "offset_from_base": "0x10",
                "type": "ace.btable.cEditFieldEnum`1<app.KIND>",
            },
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
        },
        # get_Kind (vtable index 4, slot 0x60): 0 in Point, 1 in PointB.
        "app.Point": {
            "parent": "System.Object",
            "methods": {
                "get_Kind7": {
                    "function": f"{HELPER:x}",
                    "vtable_index": 4,
                    "returns": {"type": "System.Int32"},
                }
            },
        },
        "app.PointB": {
            "parent": "app.Point",
            "methods": {
                "get_Kind8": {
                    "function": f"{OVERRIDE:x}",
                    "vtable_index": 4,
                    "returns": {"type": "System.Int32"},
                }
            },
        },
    }

    def fields(self, name):
        return self.FIELDS.get(name, {})

    def subclasses(self, name):
        return ["app.PointB"] if name == "app.Point" else []

    def get(self, name):
        return self.TYPES.get(name)

    def enum(self, name):
        if name == "ace.btable.cEditFieldEnum`1<app.KIND>":
            return "app.KIND", {"X": 1, "Y": 3}
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
        # The index is read from a field, but the base is no array: the read
        # cannot be named, so only that comparison stays unknown.
        self.assertEqual(rule["unknownPaths"], [])
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

    def test_enum_argument_is_forked_and_decided_per_node(self):
        from sdk.enemy_logic_exporter.shared.logic.formula import _expression

        # mov rax, [r9+0x10]; mov eax, [rax+0x10]; cmp eax, 3; sete al; ret
        command = bytes.fromhex("498b4110" "8b4010" "83f803" "0f94c0c3")
        row = dict(ROW, parameters=[ROW["parameters"][0], {"type": "app.SwitchArg"}])
        namer = N.NativeNamer(
            Metadata(), row, ("param", "param_3"), ("param", "param_4")
        )
        formula, _, _ = N.evaluate(
            FakePE({COMMAND: command}), COMMAND, False, namer.argument_domain
        )
        expression = _expression(formula, namer)
        self.assertEqual(
            instantiate(expression, {"_Kind": "[3] Y"}),
            dict(kind="constant", value=True),
        )
        self.assertEqual(
            instantiate(expression, {"_Kind": "[1] X"}),
            dict(kind="constant", value=False),
        )
        # A value the enum does not declare stays unknown.
        self.assertEqual(instantiate(expression, {"_Kind": "[7] Z"})["kind"], "unknown")

    def test_cdqe_sign_extends_eax(self):
        # mov eax, 0xffffffff; cdqe; cmp rax, -1; sete al; ret
        command = bytes.fromhex("b8ffffffff" "4898" "4883f8ff" "0f94c0c3")
        formula, _, _ = N.evaluate(FakePE({COMMAND: command}), COMMAND)
        self.assertEqual(formula, ("const", True))

    def test_tail_jump_target_is_recorded_as_helper(self):
        command = bytes.fromhex("e9") + struct.pack("<i", HELPER - (COMMAND + 5))
        helper = assemble(
            [*CONTEXT, bytes.fromhex("83786401"), bytes.fromhex("0f94c0c3")], HELPER
        )
        _, helpers, _ = N.evaluate(FakePE({COMMAND: command, HELPER: helper}), COMMAND)
        self.assertIn(HELPER, helpers)

    def truth(self, expression, **values):
        context = {f"context:{k}": v for k, v in values.items()}
        return evaluate_expression(expression, None, context).truth

    def test_list_element_at_a_field_index_and_a_flag_mask(self):
        command = assemble(
            [
                *CONTEXT,
                bytes.fromhex("488b5068"),  # mov rdx, [rax+0x68] (_Points)
                bytes.fromhex("48634864"),  # movsxd rcx, dword [rax+0x64] (_Count)
                bytes.fromhex("3b4a18"),  # cmp ecx, [rdx+0x18] (_size)
                (0x7D, "zero"),  # jge zero
                bytes.fromhex("488b5210"),  # mov rdx, [rdx+0x10] (_items)
                bytes.fromhex("488b54ca20"),  # mov rdx, [rdx+rcx*8+0x20]
                bytes.fromhex("488b4230"),  # mov rax, [rdx+0x30] (_Flags)
                bytes.fromhex("48a940000000"),  # test rax, 0x40
                bytes.fromhex("0f95c0c3"),  # setne al; ret
                "zero",
                bytes.fromhex("31c0c3"),
            ],
            COMMAND,
        )
        rule = self.leaf({COMMAND: command})
        self.assertEqual(rule["semanticStatus"], "native_x64_field_formula_recovered")
        formula = rule["formula"]
        self.assertEqual(
            formula["items"][0],
            dict(
                kind="compare",
                operator="lt",
                left=dict(kind="runtime", key="context:_Count", source="_Count"),
                right=dict(
                    kind="runtime", key="context:_Points._size", source="_Points._size"
                ),
            ),
        )
        self.assertEqual(
            formula["items"][1]["key"], "context:_Points._items[_Count]._Flags&0x40"
        )
        context = {"context:_Count": 1, "context:_Points._size": 1}
        self.assertFalse(evaluate_expression(formula, None, context).truth)

    def test_virtual_getter_answered_by_constants(self):
        command = assemble(
            [
                *CONTEXT,
                bytes.fromhex("488b5068"),  # mov rdx, [rax+0x68]
                bytes.fromhex("48634864"),  # movsxd rcx, dword [rax+0x64]
                bytes.fromhex("488b5210"),  # mov rdx, [rdx+0x10]
                bytes.fromhex("488b54ca20"),  # mov rdx, [rdx+rcx*8+0x20]
                bytes.fromhex("488b02"),  # mov rax, [rdx] (method table)
                bytes.fromhex("ff5060"),  # call [rax+0x60] (vtable index 4)
                bytes.fromhex("83f801"),  # cmp eax, 1
                bytes.fromhex("0f94c0c3"),  # sete al; ret
            ],
            COMMAND,
        )
        functions = {
            COMMAND: command,
            HELPER: bytes.fromhex("31c0c3"),  # Point: xor eax, eax; ret
            OVERRIDE: bytes.fromhex("b801000000c3"),  # PointB: mov eax, 1; ret
        }
        rule = self.leaf(functions)
        self.assertEqual(
            rule["formula"]["left"]["key"], "context:_Points._items[_Count].get_Kind()"
        )
        self.assertEqual(rule["formula"]["right"], dict(kind="constant", value=1))
        found = rule["virtualMethods"][0]["implementations"]
        self.assertEqual(
            [(i["type"], i["value"]) for i in found],
            [("app.Point", 0), ("app.PointB", 1)],
        )
        self.assertEqual(
            {h["address"] for h in rule["inlinedHelpers"]}, {hex(HELPER), hex(OVERRIDE)}
        )
        # An override that does more than return a constant is rejected.
        functions[OVERRIDE] = bytes.fromhex("8b4210c3")  # mov eax, [rdx+0x10]; ret
        self.assertIsNone(self.leaf(functions))

    def test_carry_and_masked_equality(self):
        # xor eax, eax; cmp ecx, 1; adc eax, 1 -> 2 exactly when ecx is 0.
        carry = assemble(
            [
                *CONTEXT,
                bytes.fromhex("8b4864"),  # mov ecx, [rax+0x64]
                bytes.fromhex("31c0"),
                bytes.fromhex("83f901"),  # cmp ecx, 1
                bytes.fromhex("83d001"),  # adc eax, 1
                bytes.fromhex("83f802"),  # cmp eax, 2
                bytes.fromhex("0f94c0c3"),
            ],
            COMMAND,
        )
        formula = self.leaf({COMMAND: carry})["formula"]
        self.assertEqual(
            [self.truth(formula, _Count=v) for v in (-1, 0, 1, 5)],
            [False, True, False, False],
        )
        # and ecx, -2; cmp ecx, 8: the field is 8 or 9.
        masked = assemble(
            [
                *CONTEXT,
                bytes.fromhex("8b4864"),
                bytes.fromhex("83e1fe"),  # and ecx, 0xfffffffe
                bytes.fromhex("83f908"),
                bytes.fromhex("0f94c0c3"),
            ],
            COMMAND,
        )
        formula = self.leaf({COMMAND: masked})["formula"]
        self.assertEqual(
            [self.truth(formula, _Count=v) for v in (7, 8, 9, 10, -8)],
            [False, True, True, False, False],
        )

    def test_merged_helper_returns_keep_the_formula(self):
        call = HELPER - (COMMAND + 24)
        command = assemble(
            [
                bytes.fromhex("53"),  # push rbx
                *CONTEXT,
                bytes.fromhex("4889c3"),  # mov rbx, rax
                bytes.fromhex("4889c2"),  # mov rdx, rax
                b"\xe8" + struct.pack("<i", call),  # call helper
                bytes.fromhex("84c0"),  # test al, al
                (0x74, "zero"),
                bytes.fromhex("807b6000"),  # cmp byte [rbx+0x60], 0
                bytes.fromhex("0f95c05bc3"),  # setne al; pop rbx; ret
                "zero",
                bytes.fromhex("31c05bc3"),
            ],
            COMMAND,
        )
        helper = bytes.fromhex("837a6403" "0f9fc0c3")  # cmp [rdx+0x64], 3; setg al
        pe = FakePE({COMMAND: command, HELPER: helper})
        namer = N.NativeNamer(
            Metadata(), ROW, ("param", "param_3"), ("param", "param_4")
        )
        tables = []
        for merge in (False, True):
            formula = N.evaluate(pe, COMMAND, merge=merge)[0]
            expression = _expression(formula, namer)
            tables.append(
                [
                    self.truth(expression, _Count=count, _IsBusy=busy)
                    for count in (2, 3, 4)
                    for busy in (False, True)
                ]
            )
        self.assertEqual(tables[0], [False, False, False, False, False, True])
        self.assertEqual(tables[0], tables[1])

    def test_constant_comparisons_are_decided(self):
        self.assertEqual(
            N._fold(("cmp", "==", ("const", 0), ("const", 0))), ("const", True)
        )
        field = ("load", 4, ("param", "param_3"), 0)
        # Any other mask is the atom "the field has a bit of the mask".
        self.assertEqual(N._mask_zero(field, ("const", 6)), ("not", ("bits", field, 6)))
        with self.assertRaises(Unsupported):
            N._mask_zero(field, ("load", 4, ("param", "param_3"), 8))


if __name__ == "__main__":
    unittest.main()
