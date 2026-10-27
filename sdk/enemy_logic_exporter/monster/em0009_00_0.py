"""Offline analysis entry for EM0009_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0009_00_0"
NATIVE_OWNER = "Em0009_00"

GRAPPLING_COMMAND = "app.btable.Em0009_00BTableCommand.cGrapplingCheck"
GRAPPLING_RECEIPT = "em0009_grappling.v1.json"
CAPTURE_KEY = "extend:app.cEm0009_00Extend._CarryManager.IsCapture"
CARRY_MANAGER_VALID = "grappling_self_carry_manager_exists"


def verify_native_recipes(pe, metadata):
    from ..shared.logic.grappling_checks import verify_receipt

    return verify_receipt(pe, metadata, GRAPPLING_RECEIPT)


def recover_boolean_command_effect(row, metadata, pe):
    if row.get("type") != GRAPPLING_COMMAND:
        return None
    from ..shared.logic import grappling_checks as check
    from ..shared.logic.expressions import combined, compare, runtime

    proof = check.evidence(row, metadata, pe, GRAPPLING_RECEIPT)
    definitions = check.inputs(
        metadata, part_key=check.SELF_PART_COUNT, part_subject="自身"
    )
    definitions[CARRY_MANAGER_VALID] = dict(
        label="搬运管理对象存在",
        boolean=True,
        hint="自身 Extend._CarryManager 非空。命令正常计算结果后直接写 IsCapture；空引用不返回普通 false。",
    )
    return dict(
        guard=dict(
            expression=combined(
                "all",
                runtime(
                    "enemy_command_work_valid",
                    "命令工作存在且类型为 cEnemyBTableCommandWork",
                ),
                runtime(
                    "self_extend_valid", "自身 Extend 存在且类型为 cEm0009_00Extend"
                ),
            ),
            summary="检查抓取命令工作与自身扩展对象",
            semanticEvidence=proof,
        ),
        normalPrecondition=runtime(CARRY_MANAGER_VALID, "Extend._CarryManager 非空"),
        exceptionBoundary="grappleingResult 正常返回后，对 Extend._CarryManager.IsCapture 直接写入；_CarryManager 为空时是原生裸解引用异常，不是普通 false 返回。其他所用 Context/Basic/Parts/数组引用也须有效。",
        condition=dict(
            expression=combined(
                "any",
                combined(
                    "all",
                    runtime(check.TARGET_READY, "主目标怪物可用且初始化结束"),
                    compare(
                        check.TARGET_ID, 9, source="目标 Basic.EmID == EM0070_00_0"
                    ),
                    compare(
                        check.TARGET_ROLE,
                        5,
                        source="目标 Basic.RoleID == ROLE_COLLAB_01",
                    ),
                ),
                compare(
                    check.SELF_PART_COUNT,
                    0,
                    "gt",
                    source="自身 _BreakParts 中 BreakCount>0 且 BreakParamIndex==0 的元素数大于0",
                ),
                dict(kind="unknown", reason=check.MANAGER_BOUNDARY),
            ),
            summary="检查目标影蜘蛛角色或自身指定破坏部位；后续管理器查询待核实",
            semanticStatus="reviewed_native_semantics_partial",
            reviewedBooleanCommand=True,
            semanticEvidence=proof,
            inputDefinitions=definitions,
            queryContracts=[check.part_query(check.SELF_PART_COUNT, "self")],
        ),
        onTrue={CAPTURE_KEY: True},
        onFalse={CAPTURE_KEY: False},
        effectSummary="记录本次抓取检查的结果",
    )


FORMULA_HISTORY_TABLES = {
    "app.Em0009_00_BTable_Life_Export": ("table_15b93e77_10c2_43b7_8b80_b0a83d7fbe90",)
}


def table_history_policy(row):
    method = row["method"]
    policy = {}
    formula = FORMULA_HISTORY_TABLES.get(row["type"], ())
    if any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in formula
    ):
        policy["formula"] = True
    return policy or None


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
