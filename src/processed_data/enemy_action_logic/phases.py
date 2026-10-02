"""Small, explicit adapters for monster-specific combat phase definitions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseRule:
    command: str
    field: str
    definition: str
    scope: str
    phases: tuple[tuple[str, str], ...]
    note: str = ""
    include_regular: bool = False


# These values were checked against Enums_Internal and actual BTable arguments.
# PHASE_5 exists in the EM164/166 enum but is absent from the active PhaseList;
# it must not become a fifth diagram just because the enum declares it.
PHASE_COMPATIBILITY = {
    "EM0078_00": PhaseRule(
        "app.btable.Em0078_00BTableCommand.cCheckPhaseArg",
        "_EditArg",
        "app.Em0078_00_Def.PHASE",
        "battle",
        (
            ("[0] EARLY", "阶段 1 · 前期"),
            ("[1] MIDFIELD", "阶段 2 · 中期"),
            ("[2] FINAL", "阶段 3 · 后期"),
        ),
        "阶段编号来自巨戟龙的专用阶段命令；血量配置的实际比较和切换时机尚未恢复。",
    ),
    "EM0162_00": PhaseRule(
        "app.btable.Em0162_00BTableCommand.cCheckPhaseArg",
        "_ChoicePhase",
        "app.Em0162Def.QUEST_PHASE",
        "quest_battle",
        tuple((f"[{i}] PHASE_{i}", f"阶段 {i}") for i in range(1, 5)),
        "这是冻峰龙的任务战斗阶段；阶段切换条件与每个阶段的动作归属尚未恢复。",
    ),
    "EM0164_50": PhaseRule(
        "app.btable.Em0164_50BTableCommand.cCheckBattlePhaseArg",
        "_EditArg",
        "app.Em0164_50_Def.BATTLE_PHASE",
        "battle",
        tuple((f"[{i - 1}] PHASE_{i}", f"阶段 {i}") for i in range(1, 5)),
    ),
    "EM0166_00": PhaseRule(
        "app.btable.Em0166_00BTableCommand.cCheckBattlePhaseArg",
        "_EditArg",
        "app.Em0166_00_Def.BATTLE_PHASE",
        "battle",
        tuple((f"[{i - 1}] PHASE_{i}", f"阶段 {i}") for i in range(1, 5)),
    ),
    "EM0046_00": PhaseRule(
        "app.btable.Em0046_00BTableCommandArg.cCheckSwimCombatPhaseType",
        "_SwimCombatPhase",
        "app.btable.Em0046_00BTableCommandArg.cCheckSwimCombatPhaseType.SWIM_COMBAT_PHASE",
        "swim_combat",
        (
            ("[0] ELECTRIC_LEVEL_2", "游泳战斗 · 电力等级 2"),
            ("[1] ELECTRIC_LEVEL_3", "游泳战斗 · 电力等级 3"),
            ("[2] FINISH", "游泳战斗 · 结束段"),
        ),
        "这三个阶段属于海龙的游泳战斗过程，不能视为整场战斗的单向阶段。常规战斗另行展示。",
        include_regular=True,
    ),
}


def resolve_phases(prefix: str, explicit: list[dict], tables: list[dict]) -> list[dict]:
    """Prefer active lists; use an exact EM/command adapter for other formats."""
    rule = PHASE_COMPATIBILITY.get(prefix.upper())
    if rule is None:
        return explicit
    expected = dict(rule.phases)
    references = {key: [] for key in expected}
    for table in tables:
        for argument in table["guardArguments"]:
            if argument["type"] != rule.command:
                continue
            value = argument["raw"].get(rule.field)
            if not isinstance(value, str) or value not in expected:
                raise ValueError(f"Unexpected combat phase for {prefix}: {value}")
            references[value].append(
                {
                    "source": table["source"],
                    "index": argument["index"],
                    "field": rule.field,
                    "command": rule.command,
                    "raw": argument["raw"],
                }
            )
    if not any(references.values()):
        return explicit  # An EM number alone is insufficient evidence.
    if explicit and {row["id"] for row in explicit} != set(expected):
        raise ValueError(
            f"Combat phase list conflicts with EM compatibility for {prefix}"
        )
    if not rule.include_regular and not all(references.values()):
        raise ValueError(f"Incomplete combat phase references for {prefix}")
    by_id = {row["id"]: row for row in explicit}
    result = []
    if rule.include_regular:
        result.append(
            {
                "id": "regular_combat",
                "title": "常规战斗（游泳战斗外）",
                "scope": "regular_combat",
                "basis": "compatibility_context",
                "configurations": [],
                "note": "保留游泳战斗外的常规动作入口；进入游泳战斗的实际条件尚未恢复。",
            }
        )
    for phase_id, title in rule.phases:
        item = dict(by_id.get(phase_id, {"id": phase_id, "configurations": []}))
        item.update(
            title=title,
            scope=rule.scope,
            basis=(
                "resource_phase_list" if phase_id in by_id else "fixed_em_compatibility"
            ),
            definition=rule.definition,
            guardReferences=references[phase_id],
            note=rule.note,
        )
        if not references[phase_id]:
            item[
                "note"
            ] += " 此阶段值由兼容配置保留，依据是已核对的专用枚举；行为表没有直接检查该值。"
        result.append(item)
    return result
