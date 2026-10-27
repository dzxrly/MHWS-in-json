"""Offline analysis entry for EM0070_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0070_00_0"
NATIVE_OWNER = "Em0070_00"

# Reviewed native methods; local histories are split only at their actual reads.
LOCAL_HISTORY_TABLES = {
    "app.Em0070_00_BTable_CommonAttack_Export": (
        "table_569db6c2_e9b4_4448_9c04_0589038f8cd8",
        "table_7088ed9e_ac74_4185_b14d_a14ad97f92ca",
    ),
}


FORMULA_HISTORY_TABLES = {
    "app.Em0070_00_BTable_CommonAttack_Export": (
        "table_128ca6b1_4d4e_4dca_9424_394f338e6b7e",
        "table_276c7fd1_7913_4b36_84ca_75d2f4ff516c",
        "table_7088ed9e_ac74_4185_b14d_a14ad97f92ca",
        "table_915c5b07_22ce_4cdc_805c_b312baa7dbea",
        "table_b909566a_0d49_4fc2_ba38_bbe9d5d08c5f",
        "table_c02b98c9_ef67_423c_acb2_ee29d7d5383f",
        "table_f6981aa2_dacb_4f06_a16a_aadc3a57fb97",
        "table_fe3aa129_b69e_49a7_b407_6298051dbde5",
    ),
    "app.Em0070_00_BTable_Life_Export": ("table_d2c620a6_5ba8_4539_b74f_609f41caa856",),
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


SIDE_WALK_COMMAND = "app.btable.Em0070_00BTableCommand.cSideWalkOffset"
SIDE_WALK_ARGUMENT = SIDE_WALK_COMMAND + "Arg"
SIDE_WALK_EXTEND = "app.cEm0070_00Extend"
SIDE_WALK_RECEIPT = "em0070_target_effects.v1.json"
GRAPPLING_COMMAND = "app.btable.Em0070_00BTableCommand.cGrapplingCheck"
GRAPPLING_RECEIPT = "em0070_grappling.v1.json"
# Current native float constants, in their actual multiplication order.
SIDE_WALK_ANGLE_MULTIPLIERS = (
    0.0055555556900799274,
    3.1415927410125732,
    3.1415927410125732,
)


def verify_native_recipes(pe, metadata):
    from ..shared.logic.target_command_effects import verify_target_receipt
    from ..shared.logic.grappling_checks import verify_receipt

    verify_target_receipt(pe, metadata, SIDE_WALK_RECEIPT)
    return verify_receipt(pe, metadata, GRAPPLING_RECEIPT)


def recover_boolean_command_effect(row, metadata, pe):
    if row.get("type") != GRAPPLING_COMMAND:
        return None
    from ..shared.logic import grappling_checks as check
    from ..shared.logic.expressions import combined, compare, runtime

    proof = check.evidence(row, metadata, pe, GRAPPLING_RECEIPT)
    return dict(
        guard=dict(
            expression=runtime(
                "enemy_command_work_valid",
                "命令工作存在且类型为 cEnemyBTableCommandWork",
            ),
            summary="检查抓取命令工作",
            semanticEvidence=proof,
        ),
        condition=dict(
            expression=combined(
                "all",
                runtime(check.TARGET_READY, "主目标怪物可用且初始化结束"),
                compare(check.TARGET_ID, 5, source="目标 Basic.EmID == EM0009_00_0"),
                combined(
                    "any",
                    compare(
                        check.SELF_ROLE, 5, source="自身 Basic.RoleID == ROLE_COLLAB_01"
                    ),
                    compare(
                        check.TARGET_PART_COUNT,
                        0,
                        "gt",
                        source="目标 _BreakParts 中 BreakCount>0 且 BreakParamIndex==0 的元素数大于0",
                    ),
                    dict(kind="unknown", reason=check.MANAGER_BOUNDARY),
                ),
            ),
            summary="目标为毒怪鸟，且自身角色或目标指定破坏部位满足条件；后续管理器查询待核实",
            semanticStatus="reviewed_native_semantics_partial",
            reviewedBooleanCommand=True,
            semanticEvidence=proof,
            inputDefinitions=check.inputs(
                metadata, part_key=check.TARGET_PART_COUNT, part_subject="目标怪物"
            ),
            queryContracts=[
                check.part_query(check.TARGET_PART_COUNT, "selected_enemy")
            ],
        ),
        onTrue={},
        onFalse={},
        effectSummary="抓取判断不写入毒怪鸟的搬运状态",
    )


def recover_target_command_effect(bound, evidence):
    from ..shared.logic.target_command_effects import side_walk_target_effect

    return side_walk_target_effect(
        bound,
        evidence,
        command=SIDE_WALK_COMMAND,
        argument_type=SIDE_WALK_ARGUMENT,
        extend_type=SIDE_WALK_EXTEND,
        receipt_name=SIDE_WALK_RECEIPT,
        angle_multipliers=SIDE_WALK_ANGLE_MULTIPLIERS,
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
