"""Offline analysis entry for EM0164_50_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0164_50_0"
NATIVE_OWNER = "Em0164_50"

# Reviewed native methods; local histories are split only at their actual reads.
LOCAL_HISTORY_TABLES = {
    "app.Em0164_50_BTable_CommonAttack_Export": (
        "table_1b08d3be_6146_4db4_8577_562cdd3002dd",
    ),
}


def table_history_policy(row):
    method = row["method"]
    stems = LOCAL_HISTORY_TABLES.get(row["type"], ())
    local = any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in stems
    )
    return dict(local=True) if local else None


# Parameterless Em0164_50 commands (game 1.42.0.2); onExecute reads the Extend
# at work+0x28 -> +0x78 -> +0x10 after an exact cEm0164_50Extend type check and
# inlines one Extend method:
# cIsRequestChangeBattlePhase = isRequestChangeBattlePhase(),
#   _RequestPhase (+0x110) != _CurrentPhase (+0x10c);
# cCheckRampage = isRampagePartsState(HEAD), _IsEnchantControllerSetuped
#   (+0x125) and _EnchantController[0]._PartsState == RAMPAGE.
EXTEND = "app.cEm0164_50Extend"
COMMAND_PREFIX = "app.btable.Em0164_50BTableCommand."
PHASE_APPLY_COMMAND = COMMAND_PREFIX + "cApplyRequestBattlePhase"
PHASE_EVIDENCE_FILE = "em0164_phase_apply.v1.json"
EXTEND_CHECKS = {
    "cIsRequestChangeBattlePhase": (
        "isRequestChangeBattlePhase()",
        "_RequestPhase 与 _CurrentPhase 不同",
        dict(method="onExecute1234525", address="0x1464034b0", end="0x1464034f0"),
        dict(
            method="isRequestChangeBattlePhase554076",
            address="0x14c91db30",
            end="0x14c91db40",
        ),
    ),
    "cCheckRampage": (
        "isRampagePartsState(HEAD)",
        "_IsEnchantControllerSetuped 且 _EnchantController[HEAD]._PartsState 为 RAMPAGE",
        dict(method="onExecute1234533", address="0x147346eb0", end="0x147346f00"),
        dict(
            method="isRampagePartsState554032", address="0x1490a5520", end="0x1490a553d"
        ),
    ),
}


def recover_phase_apply(row, metadata, pe):
    """Verify this monster's own tail call and guarded phase copy.

    Applying the phase also updates enchant timers, calls the last-phase
    callback, and may synchronize over the network. Only the field copy is
    represented as a complete write; the command retains that boundary.
    """
    if row["type"] != PHASE_APPLY_COMMAND:
        return []
    import json

    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM
    from ..shared.config import EVIDENCE_DIR

    proof = json.loads((EVIDENCE_DIR / PHASE_EVIDENCE_FILE).read_text(encoding="utf8"))
    command, helper = proof["methods"]
    for key in ("type", "method", "address", "end"):
        if row.get(key) != command[key]:
            raise ValueError("EM0164 阶段应用命令身份不匹配")
    for expected in proof["methods"]:
        address, end = int(expected["address"], 16), int(expected["end"], 16)
        record = metadata.get(expected["type"]) or {}
        method = record.get("methods", {}).get(expected["method"], {})
        if int(method.get("function", "0"), 16) != address:
            raise ValueError("EM0164 阶段应用方法身份变化")
        if pe.read(address, end - address).hex() != expected["nativeBytes"]:
            raise ValueError("EM0164 阶段应用原生字节变化")
    for owner, expected in proof["layouts"].items():
        fields = metadata.fields(owner)
        if any(
            fields.get(name, {}).get("type") != field["type"]
            or fields.get(name, {}).get("offset_from_base") != field["offset"]
            for name, field in expected.items()
        ):
            raise ValueError("EM0164 阶段字段布局变化")
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    site = int(proof["tailBranch"], 16)
    branch = next(decoder.disasm(pe.read(site, 6), site), None)
    if (
        branch is None
        or branch.mnemonic != "je"
        or branch.operands[0].type != CS_OP_IMM
        or branch.operands[0].imm != int(helper["address"], 16)
    ):
        raise ValueError("EM0164 阶段应用尾跳变化")
    if pe.read(int(proof["fieldCopy"], 16), 12).hex() != proof["copyBytes"]:
        raise ValueError("EM0164 阶段字段复制变化")
    fields = proof["layouts"][EXTEND]
    return [
        dict(
            destination=dict(
                contextType=EXTEND,
                field="_CurrentPhase",
                fieldType=fields["_CurrentPhase"]["type"],
                offset=fields["_CurrentPhase"]["offset"],
            ),
            value=dict(
                kind="self_extend_field",
                contextType=EXTEND,
                field="_RequestPhase",
                fieldType=fields["_RequestPhase"]["type"],
                offset=fields["_RequestPhase"]["offset"],
            ),
            nativeExpression="mov eax,[rdx+0x110]; mov [rdx+0x10c],eax",
            instructionSite=proof["storeSite"],
            evidence={
                key: command[key] for key in ("type", "method", "address", "end")
            },
            supportingEvidence={
                key: helper[key] for key in ("type", "method", "address", "end")
            },
            callerBranchSite=proof["tailBranch"],
            semanticStatus="individual_native_field_write_from_verified_tail",
            guard="命令工作及自身 Extend 非空且精确类型匹配后，将请求阶段复制为当前阶段；附着计时器、末阶段回调与同步处理仍保留边界",
        )
    ]


recover_command_effects = recover_phase_apply


def recover_condition(node, enemy_id, resources):
    """Reviewed parameterless checks that inline one Extend method."""
    from ..shared.logic.expressions import combined, runtime

    name = str(node.get("commandType")).removeprefix(COMMAND_PREFIX)
    if name not in EXTEND_CHECKS:
        return None
    method, meaning, command, helper = EXTEND_CHECKS[name]
    return dict(
        expression=combined(
            "all",
            runtime("enemy_command_work_valid", "命令工作存在"),
            runtime("self_extend_valid", "自身 Extend 存在且是 cEm0164_50Extend"),
            runtime(f"extend:{EXTEND}.{method}", meaning),
        ),
        summary=f"{method} 成立",
        semanticStatus="reviewed_native_semantics",
        semanticEvidence=[
            dict(type=COMMAND_PREFIX + name, **command),
            dict(type=EXTEND, **helper),
        ],
    )


def extract(context):
    """Select this monster's declared tables, imports and native method contexts."""
    return context.extract_enemy(ENEMY_ID, NATIVE_OWNER)


def build_model(
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    *,
    requests_path=None,
    inventory_path=None,
    context=None,
):
    """Extract this EM from its real slot/import closure and typed native calls."""
    from ..shared.models.native_recipe import build_monster

    return build_monster(
        ENEMY_ID,
        NATIVE_OWNER,
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        requests_path=requests_path,
        inventory_path=inventory_path,
        context=context,
    )
