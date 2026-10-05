"""Recover reviewed Combat entry pushes without a general runtime stack model."""

import copy
from functools import lru_cache
import hashlib
import json

from capstone import CS_OP_MEM

from ..config import (
    ARRAY_ELEMENTS,
    ARRAY_LENGTH,
    EVIDENCE_DIR,
    OPERATOR_EXPORT_JUMP,
    POSITION_SIZE,
    POSITION_TABLE,
    STACK_ARRAY,
    STACK_REFERENCE_TAG,
    STACK_SIZE,
    STACK_VERSION,
)
from ..native.bindings import add, pointer


@lru_cache(maxsize=1)
def evidence():
    return json.loads(
        (EVIDENCE_DIR / "combat_position_push.v1.json").read_text(encoding="utf8")
    )


def recover_entry_push(machine, branch, original):
    """Return the same typed call/continuation from both actual capacity paths.

    The proof is structural: the matched instruction prefix, the verified resize
    helper bytes and identical results on every storage case. The listed
    methods are the originally reviewed samples, not a whitelist.
    """
    proof = evidence()
    if machine.registry.data["profile"] != proof["profile"]:
        return None
    helper = proof["resizeHelper"]
    start, end = int(helper["address"], 16), int(helper["end"], 16)
    if (
        machine.pe is None
        or hashlib.sha256(machine.pe.read(start, end - start)).hexdigest()
        != helper["nativeSha256"]
    ):
        return None
    instructions = list(machine.ins.values())
    index = next(
        i for i, ins in enumerate(instructions) if ins.address == branch.address
    )
    prefix = instructions[max(0, index - 4) : index]
    if (
        branch.mnemonic != "jae"
        or len(prefix) != 4
        or [ins.mnemonic for ins in prefix] != ["mov", "mov", "mov", "cmp"]
        or machine.address(prefix[0], prefix[0].operands[1], original)
        != pointer("return_stack", STACK_SIZE)
        or machine.address(prefix[1], prefix[1].operands[1], original)
        != pointer("return_stack", STACK_ARRAY)
        or prefix[2].operands[1].type != CS_OP_MEM
        or prefix[2].operands[1].mem.disp != ARRAY_LENGTH
    ):
        return None
    results = []
    for used, capacity in ((0, 0), (0, 1), (1, 1), (1, 2)):
        for reference in (0, 0xFFFFFFFF):
            result = _trace_push(
                machine, prefix[0].address, original, used, capacity, reference, start
            )
            if result is None:
                return None
            results.append(result)
    if any(result[:3] != results[0][:3] for result in results[1:]):
        return None
    address, arguments, continuation, _ = results[0]
    state = copy.deepcopy(original)
    for register, value in zip(("rcx", "rdx", "r8", "r9"), arguments):
        state["regs"][register] = value
    state["mem"][("operator", OPERATOR_EXPORT_JUMP, 1)] = 1
    state["saved"] = continuation
    state["flags"] = None
    receipt = dict(
        kind="reviewed_combat_entry_position_push",
        capacityBranch=hex(branch.address),
        positionWriteSites=sorted({site for result in results for site in result[3]}),
        checkedStorageCases=4,
        checkedReferenceTagCases=2,
        continuation=dict(tableIndex=continuation[0], programCounter=continuation[1]),
        resizeHelper=helper,
        scope=proof["scope"],
    )
    return address, state, receipt


def _trace_push(machine, address, original, used, capacity, reference, resize):
    from .machine import Boundary

    state = copy.deepcopy(original)
    state["mem"].update(
        {
            ("return_stack", STACK_ARRAY, 8): pointer("return_stack_array"),
            ("return_stack", STACK_REFERENCE_TAG, 4): reference,
            ("return_stack", STACK_SIZE, 4): used,
            ("return_stack", STACK_VERSION, 4): 0,
            ("return_stack_array", ARRAY_LENGTH, 4): capacity,
        }
    )
    continuation, committed, sites = None, False, []
    for _ in range(160):
        ins = machine.ins.get(address)
        if ins is None:
            return None
        if ins.mnemonic == "call":
            event = machine.event(ins, state)
            if committed and event["target"] in machine.targets:
                if any(value is None for value in event["arguments"][:4]):
                    return None
                if machine.load(pointer("operator", OPERATOR_EXPORT_JUMP), 1, state) != 1:
                    return None
                return ins.address, event["arguments"][:4], continuation, sites
            if event["target"] != resize or continuation is not None:
                return None
            # The verified helper normally returns an array with the old values.
            # Its concrete address/capacity is irrelevant to the ensuing fixed
            # POSITION write; keep one logical array owner across reallocation.
            state = machine.complete_call(state, event, None)
            address += ins.size
            continue
        destination = None
        if ins.mnemonic.startswith("mov") and ins.operands[0].type == CS_OP_MEM:
            destination = machine.address(ins, ins.operands[0], state)
        try:
            address = machine.step(ins, state)
        except Boundary:
            return None
        element = ARRAY_ELEMENTS + used * POSITION_SIZE
        if destination == pointer("return_stack_array", element + POSITION_TABLE):
            location = add(destination, -POSITION_TABLE)
            if not isinstance(machine.load(location, 4, state), int):
                return None
            continuation = machine.position(location, state)
            if continuation is None:
                return None
            sites.append(hex(ins.address))
        if destination == pointer("return_stack", STACK_SIZE):
            committed = (
                continuation is not None
                and machine.load(destination, 4, state) == used + 1
            )
    return None
