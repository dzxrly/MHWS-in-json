"""Reviewed 1.42.0.2 command-to-Extend tail call and one phase field copy."""

ENEMY_ID = "EM0166_00_0"
NATIVE_OWNER = "Em0166_00"

# Reviewed native methods; local histories are split only at their actual reads.
LOCAL_HISTORY_TABLES = {
    "app.Em0166_00_BTable_CommonAttack_Export": (
        "table_0ea66412_45ac_4178_8fef_dca678cb0b52",
        "table_17f810af_7101_4119_9459_e461c30f2f67",
        "table_1fcc1adc_e0c8_4b7f_943d_1d870584c7a7",
        "table_41a88b44_06dc_47f5_9a8d_59f15c449f3d",
        "table_9943808e_5585_484e_8f7e_38d22d3d2621",
        "table_a57bc732_5194_4089_aa13_1c283709ce1c",
        "table_affe9ea4_6a7e_43a5_b60d_936beb713051",
    ),
}
FORMULA_HISTORY_TABLES = {
    "app.Em0166_00_BTable_CommonAttack_Export": (
        "table_04240aae_57b7_4416_81d1_1b61c2c51cff",
        "table_0ea66412_45ac_4178_8fef_dca678cb0b52",
        "table_17f810af_7101_4119_9459_e461c30f2f67",
        "table_1fcc1adc_e0c8_4b7f_943d_1d870584c7a7",
        "table_3324bf04_a4ed_4893_bd09_61b56637b100",
        "table_41a88b44_06dc_47f5_9a8d_59f15c449f3d",
        "table_44d6cdb8_cf9f_452d_876b_16b46421b844",
        "table_61641f0c_e17a_4bd2_b9ab_fc6101ab799c",
        "table_6c3f890a_61d9_4011_af6c_ccd702bdf181",
        "table_70d5a73d_a2b3_429c_8259_f8cbc5811b02",
        "table_8b259add_0c3d_44fa_9598_b6f04b996c4a",
        "table_9943808e_5585_484e_8f7e_38d22d3d2621",
        "table_a57bc732_5194_4089_aa13_1c283709ce1c",
        "table_affe9ea4_6a7e_43a5_b60d_936beb713051",
        "table_b0a8b98d_5da7_4dbc_b87d_da5f0f8d6c32",
        "table_b21571bb_a6c4_4482_866a_eaabf973021f",
        "table_b74f3c94_5a72_4886_b737_d242f7970821",
        "table_c52b3255_0402_4c0a_97a2_26a927540710",
        "table_e4404469_c0a7_4f72_af00_a042c67b777f",
        "table_e70abb66_4ab7_4ff0_9b49_18e67b998411",
    ),
    "app.Em0166_00_BTable_Life_Export": ("table_0027e35d_3d8c_47f7_9fac_1a3a80b66017",),
}


def table_history_policy(row):
    method = row["method"]
    policy = {}
    local = LOCAL_HISTORY_TABLES.get(row["type"], ())
    if any(method.startswith(stem) and method[len(stem) :].isdigit() for stem in local):
        policy["local"] = True
    formula = FORMULA_HISTORY_TABLES.get(row["type"], ())
    if any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in formula
    ):
        policy["formula"] = True
    return policy or None


# Version-specific native identities used by this recipe (game 1.42.0.2).
PHASE_APPLY_COMMAND = "app.btable.Em0166_00BTableCommand.cApplyRequestBattlePhase"
EXTEND_TYPE = "app.cEm0166_00Extend"
EXTEND_METHOD_PREFIX = "applyRequestBattlePhase"
# Offsets within the metadata-bound command and Extend methods. These sites
# retain their instruction checks when the game moves either method.
CALLER_BRANCH_OFFSET = 0x23
# mov eax,[rdx+0x254]; mov [rdx+0x22c],eax
FIELD_COPY_OFFSET = 0x24
FIELD_COPY_BYTES = "8b825402000089822c020000"
FIELD_COPY_EXPRESSION = "mov eax,[rdx+0x254]; mov [rdx+0x22c],eax"
CURRENT_PHASE_FIELD = "_CurrentPhase"
CURRENT_PHASE_OFFSET = "0x22c"
REQUEST_PHASE_FIELD = "_RequestPhase"
REQUEST_PHASE_OFFSET = "0x254"
# Verified current-phase comparison; its record lives in data/rules.v1.json.
BATTLE_PHASE_COMMAND = "app.btable.Em0166_00BTableCommand.cCheckBattlePhase"
BATTLE_PHASE_INPUT = "battle_phase"
BATTLE_PHASE_PREFIX = "PHASE_"


def prepare_player_graph(graph, registry):
    """Bind the phase rule; it must never apply to another monster's graph."""
    for table in graph["tables"]:
        for node in table["nodes"]:
            if (
                node["kind"] == "condition"
                and node.get("commandType") == BATTLE_PHASE_COMMAND
            ):
                if graph["enemyId"] != ENEMY_ID:
                    raise ValueError("EM166 阶段配方不能用于其他怪物")
                node["predicate"] = registry.bind(
                    node["commandType"], node["argumentType"], node["argument"]
                )


def _compile_battle_phase(compiler, predicate, values):
    from ..shared.logic.values import enum_number
    from ..shared.models.player_view import comparison

    value = enum_number(values["value"])
    options = compiler.rules[predicate["commandType"]]["enumValues"]
    compiler.choices(
        BATTLE_PHASE_INPUT,
        "当前战斗阶段",
        [
            dict(label=name.replace(BATTLE_PHASE_PREFIX, "阶段 "), value=number)
            for name, number in options.items()
            if name.startswith(BATTLE_PHASE_PREFIX)
        ],
    )
    return comparison(BATTLE_PHASE_INPUT, "eq", value)


def _evaluate_battle_phase(rule, bound, context, state):
    from ..shared.logic.predicates import context_value
    from ..shared.logic.values import MissingState, enum_number, required

    if (
        required(context, "valid_command_work") is not True
        or required(state, "valid") is not True
    ):
        raise MissingState("阶段判断需要有效命令工作及匹配类型的自身 Extend")
    return context_value(state, bound["contextBinding"]) == enum_number(
        bound["values"]["value"]
    )


RULE_KINDS = {
    "battle_phase": dict(compile=_compile_battle_phase, evaluate=_evaluate_battle_phase)
}


def recover_phase_apply(row, metadata, pe):
    if row["type"] != PHASE_APPLY_COMMAND:
        return []
    caller_start = int(row["address"], 16)
    caller_end = int(row["end"], 16)
    caller_method = (
        (metadata.get(PHASE_APPLY_COMMAND) or {})
        .get("methods", {})
        .get(row["method"], {})
    )
    if int(caller_method.get("function", "0"), 16) != caller_start:
        raise ValueError("EM0166 阶段应用命令身份不匹配")
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
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    branch_site = caller_start + CALLER_BRANCH_OFFSET
    copy_site = address + FIELD_COPY_OFFSET
    if not (
        caller_start <= branch_site <= caller_end - 6
        and address <= copy_site <= end - 12
    ):
        raise ValueError("EM0166 阶段应用指令位置超出方法范围")
    caller = [
        i
        for i in decoder.disasm(
            pe.read(caller_start, caller_end - caller_start), caller_start
        )
        if i.address == branch_site
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
    copy_bytes = pe.read(copy_site, 12)
    copy = list(decoder.disasm(copy_bytes, copy_site))
    if copy_bytes != bytes.fromhex(FIELD_COPY_BYTES) or len(copy) != 2:
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
            instructionSite=hex(copy[1].address),
            evidence={key: row[key] for key in ("type", "method", "address", "end")},
            supportingEvidence=supporting,
            callerBranchSite=hex(branch_site),
            semanticStatus="individual_native_field_write_from_verified_tail",
            guard="入口中的工作与自身 Extend 非空，且精确类型检查通过后，je 跳到当前元数据确认的 applyRequestBattlePhase；后续回调与同步效果仍未全部恢复",
        )
    ]


# Reviewed native writes collected by the shared command catalog.
recover_command_effects = recover_phase_apply


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
