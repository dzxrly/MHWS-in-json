"""Offline analysis entry for EM0159_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0159_00_0"
NATIVE_OWNER = "Em0159_00"

BLAZING_COMMAND = "app.btable.Em0159_00BTableCommand.cCheckEnterBlazingMode"
UNIQUE_SPEC = dict(
    package="STM/GameDesign/Enemy/CommonData/StageResident/Data/{enemy}_StageResident.user.3.json",
    fields=["_Unique", "_SpeciesInfo"],
)


def recover_condition(node, enemy_id, resources):
    if node.get("commandType") != BLAZING_COMMAND:
        return None
    from ..shared.logic.expressions import combined, compare, invert, runtime
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition

    parameters, sources = resources.package_value(enemy_id, UNIQUE_SPEC)
    threshold = parameters["BlazingModeThreshold"]
    if type(threshold) not in (int, float):
        raise ValueError("赫猿兽燃烧模式的累积阈值不是数值")
    mode = "extend:app.cEm0159_00Extend._IsBlazingMode"
    accumulated = "extend:app.cEm0159_00Extend._BlazingModeAccumulatedValue"
    result = reviewed_condition(
        combined(
            "all",
            invert(runtime(mode, "当前燃烧模式标志")),
            compare(
                accumulated,
                threshold,
                "ge",
                source="燃烧累积值与 ParamUnique.BlazingModeThreshold 比较，包含相等",
            ),
            invert(runtime("tired", "cEnemyContext.get_IsTired()")),
        ),
        condition_evidence("ajarakan_blazing"),
        summary=f"尚未进入燃烧模式、燃烧累积值 ≥ {threshold:g}，且不疲劳",
        extend="app.cEm0159_00Extend",
        inputs={
            mode: dict(label="正在燃烧模式", boolean=True),
            accumulated: dict(label="燃烧模式累积值", number=True, min=0, max=None),
            "tired": dict(label="疲劳状态", boolean=True),
        },
    )
    result["parameterSources"] = sources
    result["parameterBinding"] = UNIQUE_SPEC
    return result


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
