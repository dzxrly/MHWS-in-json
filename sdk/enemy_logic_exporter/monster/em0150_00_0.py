"""Offline analysis entry for EM0150_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0150_00_0"
NATIVE_OWNER = "Em0150_00"

MODE_CHANGE_COMMAND = "app.btable.Em0150_00BTableCommand.cCheckModeChange"
MIN_MODE_THRESHOLD = 0.0010000000474974513  # float32 at the reviewed native constant
UNIQUE_SPEC = dict(
    package="STM/GameDesign/Enemy/CommonData/StageResident/Data/{enemy}_StageResident.user.3.json",
    fields=["_Unique", "_SpeciesInfo"],
)


def recover_condition(node, enemy_id, resources):
    if node.get("commandType") != MODE_CHANGE_COMMAND:
        return None
    from ..shared.logic.expressions import combined, compare
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition

    parameters, sources = resources.package_value(enemy_id, UNIQUE_SPEC)
    lower, upper, legendary = (
        parameters[k]
        for k in (
            "ModeChangeThreshold_Lower",
            "ModeChangeThreshold_Upper",
            "ModeChangeThreshold_Legendary",
        )
    )
    if any(type(value) not in (int, float) for value in (lower, upper, legendary)):
        raise ValueError("辟兽模式切换的生命阈值不是数值")
    health = "health_percent"
    rank = "environment_current_rank"
    history = "self_basic_legendary_id"
    mode = "extend:app.cEm0150_00Extend.Mode"
    # For non-legendary enemies RANK==1 selects Lower, all other ranks Upper.
    branches = []
    for guards, threshold in (
        ((compare(history, 0, "ne", source="Basic.LegendaryID"),), legendary),
        (
            (
                compare(history, 0, source="Basic.LegendaryID"),
                compare(rank, 1, source="EnvironmentManager.CurrentRank"),
            ),
            lower,
        ),
        (
            (
                compare(history, 0, source="Basic.LegendaryID"),
                compare(rank, 1, "ne", source="EnvironmentManager.CurrentRank"),
            ),
            upper,
        ),
    ):
        if threshold >= MIN_MODE_THRESHOLD:
            branches.append(
                combined(
                    "all",
                    *guards,
                    compare(
                        health,
                        threshold,
                        "lt",
                        source="HealthNormalized × 100，原生严格小于模式切换阈值",
                    ),
                )
            )
    result = reviewed_condition(
        combined(
            "all",
            compare(mode, 1, "ne", source="当前模式不为 SUPER_BURST"),
            (
                combined("any", *branches)
                if branches
                else dict(kind="constant", value=False)
            ),
        ),
        condition_evidence("doshaguma_mode"),
        summary=f"非 SUPER_BURST；普通生命低于 {lower:g}%（下位）或 {upper:g}%（其他任务等级），历战低于 {legendary:g}%",
        extend="app.cEm0150_00Extend",
        inputs={
            health: dict(label="生命值百分比", number=True, min=0, max=100, unit="%"),
            mode: dict(
                label="当前模式",
                options=[
                    dict(label="DEFAULT", value=0),
                    dict(label="SUPER_BURST", value=1),
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
