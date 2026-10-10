"""Offline analysis entry for EM0001_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0001_00_0"
NATIVE_OWNER = "Em0001_00"

# cIsCheckNeedMoveForLeadEgg (game 1.42.0.2): AIStateManager _NextAIStateID and
# _CurrentAIStateID are not COMBAT, a LEAD interrupt is pending
# (_NextAIInterruptID) or exists (_ExistInterruptResult[LEAD]), Lead
# _CurrentLeadType or _RequestLeadType is EGG, and Lead.Egg._IsTargetUnfiar
# is false.
LEAD_TYPES = {"ITEM": 0, "EGG": 1}
FIELD_CHECKS = {
    "app.btable.Em0001_00BTableCommand.cIsCheckNeedMoveForLeadEgg": dict(
        spec=(
            "all",
            ("key:ai_state_pending", "!=", 2),
            ("key:ai_state_current", "!=", 2),
            ("any", ("key:ai_interrupt_next", "==", 5), ("key:ai_interrupt_exists:5",)),
            (
                "any",
                ("context:Lead._CurrentLeadType", "==", 1),
                ("context:Lead._RequestLeadType", "==", 1),
            ),
            ("not", ("context:Lead.Egg._IsTargetUnfiar",)),
        ),
        evidence=[
            dict(
                type="app.btable.Em0001_00BTableCommand.cIsCheckNeedMoveForLeadEgg",
                method="onExecute1233624",
                address="0x1450a7890",
                end="0x1450a7910",
            )
        ],
        summary="非战斗 AI 状态下有诱导中断，诱导类型为 EGG，且 Egg._IsTargetUnfiar 不成立",
        enums={
            "context:Lead._CurrentLeadType": LEAD_TYPES,
            "context:Lead._RequestLeadType": LEAD_TYPES,
        },
    ),
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    return declared_condition(FIELD_CHECKS, node)


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
