"""Offline analysis entry for EM0078_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0078_00_0"
NATIVE_OWNER = "Em0078_00"

# cCheckUnusedHill (game 1.42.0.2): cEm0078_00Extend _Phase (+0x2e8) is
# MIDFIELD and _IsUnusedHill (+0x341) is true.
FIELD_CHECKS = {
    "app.btable.Em0078_00BTableCommand.cCheckUnusedHill": dict(
        spec=("all", ("extend:_Phase", "==", 1), ("extend:_IsUnusedHill",)),
        extend="app.cEm0078_00Extend",
        evidence=[
            dict(
                type="app.btable.Em0078_00BTableCommand.cCheckUnusedHill",
                method="onExecute1233936",
                address="0x144d29ad0",
                end="0x144d29b10",
            )
        ],
        summary="Phase 为 MIDFIELD 且 IsUnusedHill 成立",
        enums={"extend:_Phase": {"EARLY": 0, "MIDFIELD": 1, "FINAL": 2}},
    ),
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    return declared_condition(FIELD_CHECKS, node)


# cCheckPhase (game 1.42.0.2, onExecute 0x143ba5250..0x143ba52b6): when
# cEm0078_00Extend._Phase (0x2e8) is FINAL and _IsFinishAreaMove (0x345) is
# false, the argument is compared with MIDFIELD; otherwise with _Phase. The
# reviewed record, enum values and evidence live in data/rules.v1.json.
PHASE_COMMAND = "app.btable.Em0078_00BTableCommand.cCheckPhase"
PHASE_FINAL = "FINAL"
PHASE_MIDFIELD = "MIDFIELD"


def _compile_phase(compiler, predicate, values):
    from ..shared.logic.values import enum_number
    from ..shared.models.player_view import comparison, extend_field_label

    binding = predicate["contextBinding"]
    phase = f"extend:{binding['type']}.{binding['field']}"
    finished = f"extend:{binding['type']}.{binding['flagField']}"
    names = compiler.rules[predicate["commandType"]]["enumValues"]
    compiler.choices(
        phase,
        "专用状态 " + extend_field_label(phase),
        [dict(label=name, value=value) for name, value in names.items()],
    )
    compiler.boolean(finished, "专用状态 " + extend_field_label(finished))
    expected = enum_number(values["value"])
    final, midfield = names[PHASE_FINAL], names[PHASE_MIDFIELD]
    # A FINAL phase reads as MIDFIELD until the area move has finished.
    if expected == midfield:
        return dict(
            op="any",
            items=[
                comparison(phase, "eq", midfield),
                dict(
                    op="all",
                    items=[
                        comparison(phase, "eq", final),
                        comparison(finished, "eq", False),
                    ],
                ),
            ],
        )
    if expected == final:
        return dict(
            op="all",
            items=[comparison(phase, "eq", final), comparison(finished, "eq", True)],
        )
    return comparison(phase, "eq", expected)


def _evaluate_phase(rule, bound, context, state):
    from ..shared.logic.predicates import context_value
    from ..shared.logic.values import MissingState, enum_number, required

    binding = bound["contextBinding"]
    actual = context_value(state, binding)
    names = rule["enumValues"]
    finished = required(state, binding["flagField"])
    if type(finished) is not bool:
        raise MissingState("区域移动结束标志必须是布尔值")
    if actual == names[PHASE_FINAL] and not finished:
        actual = names[PHASE_MIDFIELD]
    return actual == enum_number(bound["values"]["value"])


RULE_KINDS = {
    "phase_after_area_move": dict(compile=_compile_phase, evaluate=_evaluate_phase)
}


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
