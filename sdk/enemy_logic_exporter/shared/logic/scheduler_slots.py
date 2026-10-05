"""Recover which AI states and interrupts queue each BTable slot.

The slot is accepted only when the BTABLE_ID argument register is written by an
immediate inside the same method before the request call, with no intervening
call. Other arguments stay explicit dynamic boundaries. The Unique interrupt's
slot table is checked against the exact static-constructor bytes.
"""

from copy import deepcopy
from functools import lru_cache
import json

from ..config import (
    BTABLE_SLOT_ENUM,
    EVIDENCE_DIR,
    SLOT_GROUPS,
    SLOT_LABELS,
    SLOT_REQUEST_ARGUMENT,
    SLOT_REQUEST_METHODS,
    SLOT_REQUEST_OWNER_PREFIXES,
    SUPPORTED_PROFILE,
    UNIQUE_SLOT_REQUESTER,
    UNIQUE_SLOT_TABLE,
)

EVIDENCE_PATH = EVIDENCE_DIR / "scheduler_slots.v1.json"
# A slot added by a game update keeps its raw name here until it is reviewed.
UNCLASSIFIED_GROUP = "未分类行为表"
ARGUMENT_REGISTERS = {
    "r8": {"r8", "r8d", "r8w", "r8b"},
}


@lru_cache(maxsize=1)
def receipt():
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf8"))


def _immediate_argument(instructions, index):
    """Return (value, reason) for the slot register before instructions[index]."""
    from capstone import CS_OP_IMM, CS_OP_REG

    names = ARGUMENT_REGISTERS[SLOT_REQUEST_ARGUMENT]
    for ins in reversed(instructions[max(0, index - 40) : index]):
        if ins.mnemonic == "call":
            return None, "crossed_call"
        _, writes = ins.regs_access()
        if not {ins.reg_name(r) for r in writes} & names:
            continue
        operands = ins.operands
        if ins.mnemonic == "mov" and operands[1].type == CS_OP_IMM:
            return operands[1].imm, "immediate"
        if (
            ins.mnemonic == "xor"
            and operands[0].type == operands[1].type == CS_OP_REG
            and operands[0].reg == operands[1].reg
        ):
            return 0, "immediate"
        return None, f"dynamic:{ins.mnemonic} {ins.op_str}"
    return None, "not_found"


def recover_slot_requests(pe, metadata, catalog):
    """Scan every method of the owner families for direct slot requests."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM

    if metadata.sha256 != SUPPORTED_PROFILE["metadataSha256"]:
        raise ValueError("调度槽配方的元数据来源变化")
    _, slots = metadata.enum(BTABLE_SLOT_ENUM)
    names = {
        (value if value < 1 << 31 else value - (1 << 32)): name
        for name, value in slots.items()
    }
    for address, (owner, method, _) in SLOT_REQUEST_METHODS.items():
        if (owner, method) not in catalog.get(address, []):
            raise ValueError(f"调度槽请求方法地址变化：{owner}.{method}")
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    requests, boundaries, scanned = [], [], 0
    for address, aliases in sorted(catalog.items()):
        owners = [a for a in aliases if a[0].startswith(SLOT_REQUEST_OWNER_PREFIXES)]
        if not owners or address in SLOT_REQUEST_METHODS:
            continue
        scanned += 1
        end = pe.end(address)
        instructions = list(decoder.disasm(pe.read(address, end - address), address))
        for index, ins in enumerate(instructions):
            if ins.mnemonic not in ("call", "jmp") or not ins.operands:
                continue
            target = ins.operands[0]
            if target.type != CS_OP_IMM or target.imm not in SLOT_REQUEST_METHODS:
                continue
            value, reason = _immediate_argument(instructions, index)
            record = dict(
                owner=owners[0][0],
                method=owners[0][1],
                aliases=[list(a) for a in owners[1:]],
                site=hex(ins.address),
                mode=SLOT_REQUEST_METHODS[target.imm][2],
            )
            if value is None:
                boundaries.append(dict(record, reason=reason))
                continue
            signed = value if value < 1 << 31 else value - (1 << 32)
            requests.append(dict(record, slot=names.get(signed, signed)))
    table = UNIQUE_SLOT_TABLE
    site = table["site"]
    if pe.read(site, len(table["bytes"]) // 2).hex() != table["bytes"]:
        raise ValueError("专用中断槽映射的初始化字节变化")
    unique = [names.get(value, value) for value in table["values"]]
    return dict(
        schemaVersion=1,
        profile=dict(SUPPORTED_PROFILE),
        requestMethods={
            hex(a): dict(owner=o, method=m, mode=k)
            for a, (o, m, k) in SLOT_REQUEST_METHODS.items()
        },
        scope="扫描所有者类型族的全部方法中对槽请求方法的直接调用；槽参数只接受同方法内、请求前且未跨调用的立即数。",
        scannedMethods=scanned,
        requests=requests,
        boundaries=boundaries,
        uniqueSlots=dict(
            requester=".".join(UNIQUE_SLOT_REQUESTER),
            contextField=table["contextField"],
            staticArray=table["global_address"],
            initializer=f"{table['owner']}.{table['method']}",
            initializerSite=hex(site),
            byIndex=unique,
        ),
    )


def write_slot_evidence(exe, metadata_path, output=EVIDENCE_PATH):
    from ..native.metadata import Il2cppMetadata
    from ..native.pe import PE, address_catalog
    from ..native.evidence import digest

    if digest(exe) != SUPPORTED_PROFILE["exeSha256"]:
        raise ValueError("EXE 与调度槽配方版本不匹配")
    with PE(exe) as pe, Il2cppMetadata(metadata_path) as metadata:
        result = recover_slot_requests(pe, metadata, address_catalog(metadata))
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return result


def scheduler_slots(model):
    """Bind this monster's declared slots to the AI states that queue them."""
    evidence = receipt()
    if evidence["profile"] != model["profile"]:
        raise ValueError("调度槽证据与模型来源版本不匹配")
    bindings = model.get("combatScheduler", {}).get("slotBindings", {})
    unique = evidence["uniqueSlots"]
    groups = {slot: name for name, slots in SLOT_GROUPS for slot in slots}
    result = []
    for slot, binding in bindings.items():
        requested = [
            dict(owner=r["owner"], method=r["method"], site=r["site"], mode=r["mode"])
            for r in evidence["requests"]
            if r["slot"] == slot
        ]
        if slot in unique["byIndex"]:
            requested.append(
                dict(
                    owner=unique["requester"].rsplit(".", 1)[0],
                    method=unique["requester"].rsplit(".", 1)[1],
                    site=unique["initializerSite"],
                    mode="change_or_jump",
                    uniqueIndex=unique["byIndex"].index(slot),
                    contextField=unique["contextField"],
                )
            )
        result.append(
            dict(
                slot=slot,
                label=SLOT_LABELS.get(slot, slot),
                group=groups.get(
                    slot, "非战斗与生态" if slot in SLOT_LABELS else UNCLASSIFIED_GROUP
                ),
                resource=binding["resource"],
                dispatchTarget=binding.get("dispatchTarget"),
                requestedBy=deepcopy(requested),
            )
        )
    return result
