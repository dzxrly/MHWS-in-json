"""Evidence and scene facts shared by the two reviewed grappling checks.

The manager query remains a native boundary. No input represents the command's
whole result; the part input is the cardinality of one explicit array predicate.
"""

from copy import deepcopy
from functools import lru_cache
import json

from ..config import EVIDENCE_DIR
from ..native.symbols import method_stem

TARGET_READY = "selected_enemy_ready"
TARGET_ID = "selected_enemy_id"
TARGET_ROLE = "grappling_selected_enemy_role_id"
SELF_ROLE = "context:Basic.RoleID"
SELF_PART_COUNT = "grappling_self_break_param_zero_count"
TARGET_PART_COUNT = "grappling_selected_enemy_break_param_zero_count"
MANAGER_BOUNDARY = (
    "部位条件不成立后仍需原生管理器查询：0x146038260 内的列表来源、多级筛选和临时集合尚未完整核实；"
    "随后才检查返回集合中是否存在 Basic.EmID=EM0009_00_0。此处不提供整个查询或命令的真假输入。"
)


@lru_cache(maxsize=2)
def receipt(name):
    return json.loads((EVIDENCE_DIR / name).read_text(encoding="utf8"))


def _method(metadata, row):
    found = [
        (name, detail)
        for name, detail in (metadata.get(row["type"]) or {}).get("methods", {}).items()
        if method_stem(name) == row["methodBaseName"]
        and detail.get("returns", {}).get("type") == row["returns"]
        and [p.get("type") for p in detail.get("params", [])] == row["parameters"]
        and [p.get("modifier") for p in detail.get("params", [])]
        == row["parameterModifiers"]
        and detail.get("impl_flags", "") == row["implFlags"]
    ]
    if len(found) != 1 or method_stem(row["method"]) != row["methodBaseName"]:
        raise ValueError("抓取检查的方法身份或签名不唯一：" + row["type"])
    return found[0]


def verify_receipt(pe, metadata, name):
    """Check suffix-independent methods, current bytes, layouts and RIP guards."""
    proof = receipt(name)
    for row in proof["methods"]:
        _, method = _method(metadata, row)
        start, end = int(row["address"], 16), int(row["end"], 16)
        expected = bytes.fromhex(row["nativeBytes"])
        if (
            int(method.get("function", "0"), 16) != start
            or len(expected) != end - start
            or pe.read(start, end - start) != expected
        ):
            raise ValueError("抓取检查的原生实现变化：" + row["type"])
    for row in proof["fieldChecks"]:
        field = metadata.fields(row["type"]).get(row["field"], {})
        if (
            field.get("type") != row["fieldType"]
            or field.get("offset_from_base") != row["offset"]
        ):
            raise ValueError("抓取检查的字段布局变化：" + row["field"])
    for row in proof["enumChecks"]:
        if (metadata.get(row["type"]) or {}).get("fields", {}).get(
            row["field"], {}
        ).get("default") != row["value"]:
            raise ValueError("抓取检查的枚举值变化：" + row["field"])
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    for check in proof["classChecks"]:
        row = next(
            row
            for row in proof["methods"]
            if row["methodBaseName"] == check["methodBaseName"]
        )
        address = int(row["address"], 16) + check["instructionOffset"]
        ins = next(decoder.disasm(pe.read(address, 15), address), None)
        if ins is None or ins.mnemonic != "cmp":
            raise ValueError("抓取检查的类型检查指令变化")
        operand = ins.operands[check["operandIndex"]]
        if operand.type != CS_OP_MEM or ins.reg_name(operand.mem.base) != "rip":
            raise ValueError("抓取检查的类型检查来源变化")
        actual = (metadata.get(check["expectedType"]) or {}).get("address")
        slot = ins.address + ins.size + operand.mem.disp
        if not actual or int.from_bytes(pe.read(slot, 8), "little") != int(actual, 16):
            raise ValueError("抓取检查的类型检查身份变化")
    return True


def evidence(row, metadata, pe, name):
    verify_receipt(pe, metadata, name)
    proof = receipt(name)
    command = proof["methods"][0]
    if (
        any(row.get(key) != command[key] for key in ("type", "address", "end"))
        or method_stem(row.get("method", "")) != command["methodBaseName"]
    ):
        raise ValueError("抓取检查的调用上下文不匹配")
    return [
        dict(
            type=item["type"],
            method=_method(metadata, item)[0],
            address=item["address"],
            end=item["end"],
        )
        for item in proof["methods"]
    ]


def inputs(metadata, *, part_key, part_subject):
    roles = metadata.enum("app.EnemyDef.ROLE_ID")[1]
    ids = metadata.enum("app.EnemyDef.ID")[1]
    role_options = [
        dict(label=name, value=value) for name, value in roles.items() if name != "MAX"
    ]
    return {
        TARGET_READY: dict(
            label="目标怪物已完成初始化",
            boolean=True,
            hint="主目标经 getTarget(FIRST, true, false) 和 getEnemyManageInfo 查到有效 ContextHolder，且 _FlagArray[DONE_CONTEXT_SETUP_END=7] 为真。",
        ),
        TARGET_ID: dict(
            label="目标怪物种类",
            options=[
                dict(label=name, value=value)
                for name, value in ids.items()
                if name not in ("MAX", "INVALID")
            ],
            hint="目标怪物 Basic.EmID；是怪物种类枚举，不是阶段。",
        ),
        TARGET_ROLE: dict(
            label="目标怪物角色分类",
            options=deepcopy(role_options),
            hint="目标 Basic.RoleID；ROLE_COLLAB_01=5 的正式含义未由本配方扩展解释。",
        ),
        SELF_ROLE: dict(
            label="自身角色分类",
            options=deepcopy(role_options),
            hint="自身 Basic.RoleID；不把角色分类解释为战斗阶段。",
        ),
        part_key: dict(
            label=part_subject + "满足指定破坏条件的部位数",
            number=True,
            numericRange=dict(min=0, max=2147483647),
            options=[
                dict(label="没有", value=0),
                dict(
                    label="至少一个",
                    value=dict(min=1, max=2147483647, minClosed=True, maxClosed=True),
                ),
            ],
            hint=part_subject
            + " Parts._BreakParts 数组中 _BreakCount>0 且 _BreakParamIndex==0 的元素数；空数组为0。它不是伤害量、未破坏部位数或整个抓取检查的结果。",
        ),
    }


def part_query(key, subject):
    return dict(
        input=key,
        source=subject + ".Parts._BreakParts",
        aggregate="count",
        predicate=dict(
            all=[
                dict(field="_BreakCount", operator="gt", value=0),
                dict(field="_BreakParamIndex", operator="eq", value=0),
            ]
        ),
        emptyArrayValue=0,
        boundary="数组及元素引用须有效；未执行游戏内数组查询。后续管理器查询仍保留原生未知边界。",
    )
