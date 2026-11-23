"""Damage modifiers for enemy projectiles, keyed by the game's fixed shell ID."""

from pathlib import Path

from src.database.missions.health import _record

SHELL_NAMES = {
    "FacialTongueGas": "面前舌部喷气",
    "ApproachTongueGas": "近身舌部喷气",
    "AllureDetonationSign": "诱爆预兆",
    "TongueGasBreath_00": "舌部喷气吐息（近段）",
    "TongueGasBreath_01": "舌部喷气吐息（中段）",
    "AutoGasEruptionSign_Event": "自动喷气预兆（活动）",
}


def load_shell_names(stm: Path, pack: dict, legendary: dict) -> dict[int, str]:
    ids = {
        shell["_ShellListNo"]
        for field in (
            "_ShellCustomData_King",
            "_ShellCustomData_Hard",
            "_ShellCustomData_King_Hard",
        )
        for wrapped in legendary.get(field, [])
        for shell in [wrapped["app.user_data.EmParamLegendary.ShellCustomData"]]
        if shell["AttackRate"] != 1 or shell["IsIgnoreActionAttackRate"]
    }
    if not ids:
        return {}

    creator_type = "ace.user_data.ShellCreatorInfoData"
    creator = _record(
        path=stm / (pack["_ShellCreatorInfoData"][creator_type]["path"] + ".3.json"),
        type_name=creator_type,
    )
    list_type = "ace.user_data.ShellList"
    shell_list = _record(
        path=stm / (creator["_ShellList"][list_type]["path"] + ".3.json"),
        type_name=list_type,
    )
    names = {}
    # evShell_PostCreate maps the name hash to an index, then to the fixed ID
    # (0x140538339, 0x140538353). These differ e.g. for Rompopolo shell 44.
    for wrapped in shell_list["_DataList"]:
        entry = wrapped["ace.user_data.ShellList.cData"]
        if entry["_FixedID"] in ids:
            package = entry["_ShellPackage"]["ace.cShellPackage"]
            path = package["_MainParam"]["ace.user_data.ShellMainParam"]["path"]
            name = (
                Path(path).stem.split("_", 2)[-1].removesuffix("MainParam").rstrip("_")
            )
            names[entry["_FixedID"]] = SHELL_NAMES.get(name, name)
    return names


def shell_modifiers(
    legendary: dict, names: dict, form: str, hard: bool, enemy: str, actions: list[dict]
) -> list[dict]:
    # getShellCustomDataDic (0x1450c8b10) overlays King, Hard and finally
    # King_Hard by fixed ID. A later neutral entry also replaces an earlier one.
    selected = {}
    for applies, field in (
        (form == "KING", "_ShellCustomData_King"),
        (hard, "_ShellCustomData_Hard"),
        (form == "KING" and hard, "_ShellCustomData_King_Hard"),
    ):
        if applies:
            for wrapped in legendary.get(field, []):
                row = wrapped["app.user_data.EmParamLegendary.ShellCustomData"]
                selected[row["_ShellListNo"]] = row
    shells = []
    # Em0155's action constructors bind motion groups 0x2b0a775af99d
    # (0x144e949e5) and 0x2bde09eef6f7 (0x1498d6f04). Bank 2 resolves
    # them to 16/17 and 85/86. Their ShellCreate tracks emit creator IDs
    # 0 and 1/43, respectively, which resolve to fixed shell IDs 0 and 1.
    sources = {
        0: ("b3675870-15ae-422d-bd13-a287d193390b", "面前舌部喷气"),
        1: ("6c066818-c9b0-44da-b950-abf9847d2e43", "毒气漂移"),
    }
    for fixed_id, row in sorted(selected.items()):
        if row["AttackRate"] == 1 and not row["IsIgnoreActionAttackRate"]:
            continue
        shell = {
            "id": fixed_id,
            "name": names[fixed_id],
            "attack": row["AttackRate"],
            "ignoreAction": row["IsIgnoreActionAttackRate"],
        }
        if enemy == "EM0155_00_0" and fixed_id in sources:
            source_guid, name = sources[fixed_id]
            # All non-neutral action attack modifiers are included in actions.
            rate = next((a["attack"] for a in actions if a["guid"] == source_guid), 1.0)
            shell["sources"] = [{"name": name, "attack": rate}]
        shells.append(shell)
    return shells
