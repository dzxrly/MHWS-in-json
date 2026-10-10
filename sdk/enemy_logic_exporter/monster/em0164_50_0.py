"""Offline analysis entry for EM0164_50_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0164_50_0"
NATIVE_OWNER = "Em0164_50"

# Parameterless Em0164_50 commands (game 1.42.0.2); onExecute reads the Extend
# at work+0x28 -> +0x78 -> +0x10 after an exact cEm0164_50Extend type check and
# inlines one Extend method:
# cIsRequestChangeBattlePhase = isRequestChangeBattlePhase(),
#   _RequestPhase (+0x110) != _CurrentPhase (+0x10c);
# cCheckRampage = isRampagePartsState(HEAD), _IsEnchantControllerSetuped
#   (+0x125) and _EnchantController[0]._PartsState == RAMPAGE.
EXTEND = "app.cEm0164_50Extend"
COMMAND_PREFIX = "app.btable.Em0164_50BTableCommand."
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
