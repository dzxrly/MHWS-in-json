"""Reviewed 1.42.0.2 command-to-Extend tail call and one phase field copy."""

import hashlib

ENEMY_ID = "EM0166_00_0"
NATIVE_OWNER = "Em0166_00"

# Version-specific native identities used by this recipe (game 1.42.0.2).
PHASE_APPLY_COMMAND = "app.btable.Em0166_00BTableCommand.cApplyRequestBattlePhase"
PHASE_APPLY_COMMAND_SHA256 = (
    "0bb35418a44985bc4c64dfd6141e189d1285544bc3eee2ab2962f25ac2d91477"
)
EXTEND_TYPE = "app.cEm0166_00Extend"
EXTEND_METHOD_PREFIX = "applyRequestBattlePhase"
EXTEND_TAIL_SHA256 = "2781eb2116ff0b91e9b30de4efdb07986b6e57cd8c0a25d84d40e2f869ce8f38"
# je from the command entry to the Extend method.
CALLER_BRANCH_SITE = 0x144195763
# mov eax,[rdx+0x254]; mov [rdx+0x22c],eax
FIELD_COPY_SITE = 0x143DDECC4
FIELD_COPY_STORE_SITE = "0x143ddecca"
FIELD_COPY_BYTES = "8b825402000089822c020000"
FIELD_COPY_EXPRESSION = "mov eax,[rdx+0x254]; mov [rdx+0x22c],eax"
CURRENT_PHASE_FIELD = "_CurrentPhase"
CURRENT_PHASE_OFFSET = "0x22c"
REQUEST_PHASE_FIELD = "_RequestPhase"
REQUEST_PHASE_OFFSET = "0x254"


def recover_phase_apply(row, metadata, pe):
    if row["type"] != PHASE_APPLY_COMMAND:
        return []
    if row["nativeSha256"] != PHASE_APPLY_COMMAND_SHA256:
        raise ValueError("EM0166 阶段应用入口字节变化，需要重新审核")
    methods = [
        (name, details)
        for name, details in (metadata.get(EXTEND_TYPE) or {})
        .get("methods", {})
        .items()
        if name.startswith(EXTEND_METHOD_PREFIX)
    ]
    if len(methods) != 1:
        raise ValueError("EM0166 阶段应用 Extend 方法无法唯一定位")
    method, details = methods[0]
    address = int(details["function"], 16)
    end = pe.end(address)
    native = pe.read(address, end - address)
    digest = hashlib.sha256(native).hexdigest()
    if digest != EXTEND_TAIL_SHA256:
        raise ValueError("EM0166 阶段应用共享尾部变化，需要重新审核")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    caller = [
        i
        for i in decoder.disasm(
            pe.read(
                int(row["address"], 16), int(row["end"], 16) - int(row["address"], 16)
            ),
            int(row["address"], 16),
        )
        if i.address == CALLER_BRANCH_SITE
    ]
    if (
        len(caller) != 1
        or caller[0].mnemonic != "je"
        or caller[0].operands[0].type != CS_OP_IMM
        or caller[0].operands[0].imm != address
    ):
        raise ValueError("EM0166 阶段应用真实跳转不匹配")
    # The copy runs after the caller checked work, self Extend and its exact
    # runtime type.
    if pe.read(FIELD_COPY_SITE, 12) != bytes.fromhex(FIELD_COPY_BYTES):
        raise ValueError("EM0166 阶段字段复制指令变化")
    fields = metadata.fields(EXTEND_TYPE)
    current = fields[CURRENT_PHASE_FIELD]
    requested = fields[REQUEST_PHASE_FIELD]
    if (
        current["offset_from_base"] != CURRENT_PHASE_OFFSET
        or requested["offset_from_base"] != REQUEST_PHASE_OFFSET
        or current["type"] != requested["type"]
    ):
        raise ValueError("EM0166 阶段字段布局变化")
    supporting = dict(
        type=EXTEND_TYPE,
        method=method,
        address=hex(address),
        end=hex(end),
        nativeSha256=digest,
    )
    return [
        dict(
            destination=dict(
                contextType=EXTEND_TYPE,
                field=CURRENT_PHASE_FIELD,
                fieldType=current["type"],
                offset=CURRENT_PHASE_OFFSET,
            ),
            value=dict(
                kind="self_extend_field",
                contextType=EXTEND_TYPE,
                field=REQUEST_PHASE_FIELD,
                fieldType=requested["type"],
                offset=REQUEST_PHASE_OFFSET,
            ),
            nativeExpression=FIELD_COPY_EXPRESSION,
            instructionSite=FIELD_COPY_STORE_SITE,
            evidence={
                key: row[key]
                for key in ("type", "method", "address", "end", "nativeSha256")
            },
            supportingEvidence=supporting,
            callerBranchSite=hex(CALLER_BRANCH_SITE),
            semanticStatus="individual_native_field_write_from_verified_tail",
            guard="入口中的工作与自身 Extend 非空，且精确类型检查通过后，je 跳到当前元数据确认的 applyRequestBattlePhase；后续回调与同步效果仍未全部恢复",
        )
    ]



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
    context=None
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
