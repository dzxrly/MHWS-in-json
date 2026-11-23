"""Conditional combat-phase and navigation speed inputs for fixed quest targets."""

from pathlib import Path

from src.database.missions.health import _record


def load_motion_sizes(natives: Path) -> dict[str, tuple[int, int]]:
    data = _record(
        path=natives
        / "STM/GameDesign/Enemy/CommonData/Data/EmCommonRandomSize.user.3.json",
        type_name="app.user_data.EmParamRandomSize",
    )
    array_type = (
        "ace.cInstanceGuidArray`1<app.user_data.EmParamRandomSize.cRandomSizeData>"
    )
    tables = {}
    for item in data["_RandomSizeTblArray"][array_type]["_DataArray"]:
        table = item["app.user_data.EmParamRandomSize.cRandomSizeData"]
        sizes = [
            row["_Scale"]
            for entry in table["_ProbDataTbl"]
            if (row := entry["app.user_data.EmParamRandomSize.cProbData"])["_Prob"] > 0
        ]
        tables[table["_InstanceGuid"]] = (min(sizes), max(sizes))
    return tables


def target_sizes(row: dict, size_tables: dict[str, tuple[int, int]]) -> tuple[int, int]:
    # In 1.42.0.3 createMainTargetContext (0x14a0115a2) sets a fixed size or
    # passes the random table. All random targets in these quests supply a GUID.
    # updateInstantiate (0x1458f9242) writes size / 100 to the boss mesh scale.
    # ContinueFlag 89 (e.g. cMoveNaviBase.doUpdate, 0x145f48dc0) enables its
    # reciprocal in the motion-speed product (0x149470900).
    if row["_IsUseRandomSize"]:
        return size_tables[row["randomSizeTable"]]
    return row["_FixedSize"], row["_FixedSize"]


def motion_phases(natives: Path, enemy: str, upper: bool) -> dict[str, float]:
    # The two extenders write MotionSpeed.Base in combat. Both reset it to one
    # when dying, respawning or handling a damage interrupt.
    if enemy == "EM0078_00_0":
        data = _record(
            path=natives
            / "STM/GameDesign/Enemy/Em0078/00/Data/Em0078_00_Param_Unique.user.3.json",
            type_name="app.user_data.EmParamUnique",
        )
        info = data["_SpeciesInfo"]["app.cEm0078_00ParamUniqueInfo"]["_Info"][
            "app.cEm0078_00ParamUniqueInfo.Info"
        ]["Common"]["app.cEm0078_00ParamUniqueInfo.cCommon"]
        # cEm0078_00Extend.updatePhase: 0x14464990e / b3b / 990.
        return {
            "初期战斗": info["EarlySpeedRate"],
            "中期战斗": info["MidfiledSpeedRate"],
            "最终阶段战斗": info["FinalSpeedRate"],
        }
    if enemy == "EM0164_50_0" and upper:
        data = _record(
            path=natives
            / "STM/GameDesign/Enemy/Em0164/50/Data/Em0164_50_Param_Unique.user.3.json",
            type_name="app.user_data.EmParamUnique",
        )
        info = data["_SpeciesInfo"]["app.cEm0164_50ParamUniqueInfo"]
        # cEm0164_50Extend.doUpdateBegin: the EX rank branch reads +0xa0/a4
        # in PHASE_3 / PHASE_4 (0x1490a3156). Other phase IDs do not write.
        return {
            "初始阶段战斗": 1.0,
            "第三阶段战斗": info["_MotSpeedRate_Phase3_EX"],
            "第四阶段战斗": info["_MotSpeedRate_Phase4_EX"],
        }
    return {}
