"""Fail closed when the reviewed native basis of collider rules changes.

This is a small receipt checker for the rules shipped by this exporter. It
does not migrate evidence, execute game code, or validate all game behavior.
"""

from bisect import bisect_right
import json
from pathlib import Path
import re
import struct

from iced_x86 import Code, Decoder, OpKind

from ..il2cpp_methods import Il2CppMethodCatalog
from ..pe import PeImage
from .il2cpp import iter_il2cpp_types

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "native_rules.v1.json"
_NEAR_BRANCHES = {OpKind.NEAR_BRANCH16, OpKind.NEAR_BRANCH32, OpKind.NEAR_BRANCH64}


def _stem(name):
    return re.sub(r"\d+$", "", name)


def _identity_matches(name, method, identity):
    return (
        _stem(name) == identity["method"]
        and [p.get("type") for p in method.get("params", [])] == identity["parameters"]
        and [p.get("modifier") for p in method.get("params", [])]
        == identity["parameterModifiers"]
        and method.get("returns", {}).get("type") == identity["returns"]
        and method.get("impl_flags", "") == identity["implFlags"]
    )


def _method(records, identity):
    found = [
        detail
        for name, detail in records.get(identity["type"], {}).get("methods", {}).items()
        if _identity_matches(name, detail, identity)
    ]
    if len(found) != 1 or not found[0].get("function"):
        raise ValueError(
            "ActionMap 原生规则方法无法唯一定位："
            + identity["type"]
            + "."
            + identity["method"]
        )
    return int(found[0]["function"], 16)


def _function_ranges(image):
    # PE32+ exception directory: x64 RUNTIME_FUNCTION entries are 12 bytes.
    with image.path.open("rb") as stream:
        stream.seek(0x3C)
        pe = struct.unpack("<I", stream.read(4))[0]
        stream.seek(pe + 24)
        optional = stream.read(112 + 4 * 8)
    if len(optional) != 144 or struct.unpack_from("<H", optional)[0] != 0x20B:
        raise ValueError("ActionMap 原生规则要求完整的 PE64 异常目录")
    rva, size = struct.unpack_from("<II", optional, 112 + 3 * 8)
    data = image.read_function_bytes(rva, size)
    if len(data) != size or size % 12:
        raise ValueError("ActionMap 原生规则的 PE 函数范围表不完整")
    return sorted(
        (image.image_base + start, image.image_base + end)
        for start, end, _ in struct.iter_unpack("<III", data)
        if start and end > start
    )


def _body_end(image, address, proof, ranges, method_addresses):
    if proof.get("boundary") == "reviewed_leaf_control_flow":
        # These four leaf routines have manually closed branches/lookup tables.
        # The proof includes every reachable return, without adjacent functions.
        return address + proof["length"]
    starts = [start for start, _ in ranges]
    index = bisect_right(starts, address) - 1
    if index >= 0 and ranges[index][0] <= address < ranges[index][1]:
        end = ranges[index][1]
    elif proof.get("boundary") == "bounded_support_helper":
        end = min(
            starts[index + 1] if index + 1 < len(starts) else address + 2048,
            address + 2048,
        )
    else:
        raise ValueError("ActionMap 原生规则方法缺少已核实的 unwind 范围")
    following = bisect_right(method_addresses, address)
    if following < len(method_addresses):
        end = min(end, method_addresses[following])
    return end


def _shape(image, address, length):
    data = image.read_function_bytes(address, length)
    if len(data) != length:
        raise ValueError("ActionMap 原生规则方法字节不完整")
    masked = bytearray(data)
    decoder = Decoder(64, data, ip=address)
    branches, rip = {}, {}
    covered = 0
    for instruction in decoder:
        if instruction.code == Code.INVALID:
            raise ValueError("ActionMap 原生规则遇到无法解码的指令")
        offset = instruction.ip - address
        constants = decoder.get_constant_offsets(instruction)
        if instruction.is_ip_rel_memory_operand:
            rip[offset] = instruction.ip_rel_memory_address
            for index in range(
                constants.displacement_offset,
                constants.displacement_offset + constants.displacement_size,
            ):
                masked[offset + index] = 0
        if instruction.op_count and instruction.op0_kind in _NEAR_BRANCHES:
            target = instruction.near_branch_target
            if not address <= target < address + length:
                branches[offset] = target
                for index in range(
                    constants.immediate_offset,
                    constants.immediate_offset + constants.immediate_size,
                ):
                    masked[offset + index] = 0
        covered = offset + instruction.len
    if covered != length:
        raise ValueError("ActionMap 原生规则未覆盖完整方法范围")
    return masked.hex(), branches, rip


def _verify_body(image, address, proof, records, ranges, addresses):
    end = _body_end(image, address, proof, ranges, addresses)
    if end - address != proof["length"]:
        raise ValueError("ActionMap 原生规则方法长度变化")
    shape, branches, rip = _shape(image, address, proof["length"])
    if shape != proof["maskedBytes"] or set(branches) != {
        p["offset"] for p in proof["branches"]
    }:
        raise ValueError("ActionMap 原生规则方法完整代码变化")
    for branch in proof["branches"]:
        target = branches[branch["offset"]]
        if "method" in branch:
            if target != _method(records, branch["method"]):
                raise ValueError("ActionMap 原生规则的被调方身份变化")
        elif branch.get("nestedRuntimeTarget"):
            # This is the declared limit of an anonymous helper's code identity,
            # not a claim that its nested runtime callee or effects were reviewed.
            continue
        else:
            helper = branch["helper"]
            # Anonymous helpers are checked by their reviewed code shape,
            # including its nested direct branch identities where present.
            _verify_body(image, target, helper, records, ranges, addresses)
    for check in proof.get("ripChecks", []):
        target = rip.get(check["offset"])
        if target is None:
            raise ValueError("ActionMap 原生规则的数据定位指令变化")
        if check["kind"] == "class":
            value = int.from_bytes(image.read_function_bytes(target, 8), "little")
            expected = records.get(check["type"], {}).get("address")
            if not expected or value != int(expected, 16):
                raise ValueError("ActionMap 原生规则的类型守卫变化")
        elif check["kind"] == "method_pointer":
            if int.from_bytes(
                image.read_function_bytes(target, 8), "little"
            ) != _method(records, check["method"]):
                raise ValueError("ActionMap 原生规则的函数指针身份变化")
        elif check["kind"] == "jump_table":
            data = image.read_function_bytes(target, len(check["targets"]) * 4)
            if (
                len(data) != len(check["targets"]) * 4
                or [
                    target + value - address
                    for value in struct.unpack("<" + "i" * len(check["targets"]), data)
                ]
                != check["targets"]
            ):
                raise ValueError("ActionMap 原生规则的分派表变化")
        else:
            expected = bytes.fromhex(check["bytes"])
            if image.read_function_bytes(target, len(expected)) != expected:
                raise ValueError("ActionMap 原生规则的查表值或只读常量变化")


def _needed_types(proof):
    result = {row["type"] for row in proof["fieldChecks"] + proof["enumChecks"]}

    def visit(body):
        for check in body.get("ripChecks", []):
            if check["kind"] == "class":
                result.add(check["type"])
            elif check["kind"] == "method_pointer":
                result.add(check["method"]["type"])
        for branch in body["branches"]:
            if "method" in branch:
                result.add(branch["method"]["type"])
            elif "helper" in branch:
                visit(branch["helper"])

    for row in proof["methods"]:
        result.add(row["identity"]["type"])
        visit(row["body"])
    return result


def load_native_metadata(il2cpp):
    """Keep this run's small method index and the rule types' signatures."""
    proof = json.loads(RULES_PATH.read_text(encoding="utf8"))
    return Il2CppMethodCatalog.load(
        Path(il2cpp), record_types=_needed_types(proof), strict_addresses=True
    )


def verify_native_rules(exe, il2cpp, *, metadata=None):
    """Verify this exporter's collider constants before reading resources."""
    proof = json.loads(RULES_PATH.read_text(encoding="utf8"))
    required = _needed_types(proof)
    if metadata is None:
        records, addresses = {}, set()
        for name, record in iter_il2cpp_types(Path(il2cpp)):
            if name in required:
                records[name] = record
            for method in record.get("methods", {}).values():
                if method.get("function"):
                    addresses.add(int(method["function"], 16))
        addresses = sorted(addresses)
    else:
        if (
            not metadata.strict_addresses
            or metadata.source_path != Path(il2cpp).expanduser().resolve()
        ):
            raise ValueError("ActionMap 原生规则的 metadata 索引来源不一致")
        records, addresses = metadata.records, metadata.function_addresses
    for row in proof["fieldChecks"]:
        field = records.get(row["type"], {}).get("fields", {}).get(row["field"], {})
        if (
            field.get("type") != row["fieldType"]
            or field.get("offset_from_base") != row["offset"]
        ):
            raise ValueError("ActionMap 原生规则字段布局变化：" + row["field"])
    for row in proof["enumChecks"]:
        if (
            records.get(row["type"], {})
            .get("fields", {})
            .get(row["field"], {})
            .get("default")
            != row["value"]
        ):
            raise ValueError("ActionMap 原生规则枚举变化：" + row["field"])
    with PeImage(Path(exe)) as image:
        ranges = _function_ranges(image)
        for row in proof["methods"]:
            try:
                _verify_body(
                    image,
                    _method(records, row["identity"]),
                    row["body"],
                    records,
                    ranges,
                    addresses,
                )
            except ValueError as error:
                raise ValueError(
                    row["identity"]["type"]
                    + "."
                    + row["identity"]["method"]
                    + "："
                    + str(error)
                ) from error
    from .. import shell_collider_rules as shell
    from .. import track_colliders as tracks

    actual = {"WEAPON_BODY_GROUP_OFFSET": tracks.WEAPON_BODY_GROUP_OFFSET}
    for name in proof["ruleConstants"]:
        if name != "WEAPON_BODY_GROUP_OFFSET":
            value = getattr(shell, name)
            actual[name] = (
                sorted(value) if isinstance(value, (set, frozenset)) else value
            )
    if json.loads(json.dumps(actual)) != proof["ruleConstants"]:
        raise ValueError("ActionMap 原生规则常量声明与已核实证明不一致")
    return dict(
        verifiedMethods=len(proof["methods"]),
        verifiedFields=len(proof["fieldChecks"]),
        verifiedEnums=len(proof["enumChecks"]),
    )
