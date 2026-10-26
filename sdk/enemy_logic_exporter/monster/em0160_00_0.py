"""Offline analysis entry for EM0160_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0160_00_0"
NATIVE_OWNER = "Em0160_00"

MODE_COMMAND = "app.Em0160_00BTableCommand.cCheckChangeMode"
MIN_MODE_THRESHOLD = 0.0010000000474974513  # float32 at the reviewed native constant
UNIQUE_SPEC = dict(
    package="STM/GameDesign/Enemy/CommonData/StageResident/Data/{enemy}_StageResident.user.3.json",
    fields=["_Unique", "_GenusInfo"],
)


def recover_condition(node, enemy_id, resources):
    if node.get("commandType") != MODE_COMMAND:
        return None
    from ..shared.logic.expressions import combined, compare
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition

    parameters, sources = resources.package_value(enemy_id, UNIQUE_SPEC)
    threshold = parameters["UnleashModeChangeThreshold"]
    if type(threshold) not in (int, float):
        raise ValueError("锁刃龙模式切换的生命阈值不是数值")
    result = reviewed_condition(
        (
            combined(
                "all",
                compare(
                    "self_basic_legendary_id", 2, source="Basic.LegendaryID == KING"
                ),
                compare(
                    "extend:app.cEm0160Extend._Mode",
                    1,
                    "ne",
                    source="当前模式不为 UNLEASH",
                ),
                compare(
                    "health_percent",
                    threshold,
                    "lt",
                    source="HealthNormalized × 100 严格小于 UnleashModeChangeThreshold",
                ),
            )
            if threshold >= MIN_MODE_THRESHOLD
            else dict(kind="constant", value=False)
        ),
        condition_evidence("arkveld_unleash"),
        summary=f"历战分类为 KING、当前不是 UNLEASH，且生命值 < {threshold:g}%",
        extend="app.cEm0160Extend",
        inputs={
            "health_percent": dict(
                label="生命值百分比", number=True, min=0, max=100, unit="%"
            ),
            "extend:app.cEm0160Extend._Mode": dict(
                label="当前模式",
                options=[
                    dict(label="DEFAULT", value=0),
                    dict(label="UNLEASH", value=1),
                ],
            ),
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
