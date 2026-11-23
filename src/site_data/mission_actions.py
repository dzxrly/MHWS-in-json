"""Resolve main-layer combat action rates from the monster's action assets."""

from pathlib import Path

from src.database.missions.difficulty import ZERO_GUID
from src.database.missions.health import _record

# Descriptions of the Arch-tempered Arkveld action classes. Most actions have
# no game-localized name; keep their class name when no description is known.
ARKVELD_ACTIONS = {
    "cHeadAttack": "头部攻击",
    "cJabWhip": "锁刃刺击",
    "cTailWhipSlam": "甩尾下砸",
    "cTailWhipSpinAttackLeft": "向左回旋甩尾",
    "cTailWhipSpinAttackRight": "向右回旋甩尾",
    "cAllWhipCrossAttack": "双锁刃交叉攻击",
}


def _parameters(stm: Path, source: str, names: dict[str, str]) -> dict:
    asset = _record(
        path=stm / f"{source}.3.json",
        type_name="ace.user_data.ActionParam",
    )
    parent = asset["_BaseActionParam"].get("ace.user_data.ActionParam")
    base = (
        _parameters(
            stm=stm,
            source=parent["path"],
            names=names,
        )
        if parent
        else {}
    )
    result = {}
    for index, wrapper in enumerate(asset["_ActionInfoList"]):
        info = wrapper["ace.user_data.ActionParam.cInfo"]
        guid = info["_ActionGuid"]
        if guid not in names:
            continue
        if parent and info["_IsBaseAction"] and not info["_OverrideOwnerAction"]:
            result[guid] = base[guid]
            continue
        classes = [asset["_ActionClassList"][index]]
        if asset["_IsUseBranchedParam"]:
            branch = asset["_BranchedParamsList"][index][
                "ace.user_data.ActionParam.cBranchedParams"
            ]
            classes.extend(
                variant["ace.user_data.ActionParam.cBranchedParam"]["_ActionClass"]
                for variant in branch["_Params"]
            )
        rates = []
        for action in classes:
            data = next(iter(action.values()))
            # doUpdateEnd 0x14943e91e/0x14943e9c4: only option bits 0/1
            # enable the corresponding replacement; stored defaults alone do not.
            flags = data.get("_OptionBit", 0)
            rates.append(
                (
                    data["_OverrideMotionRate_Angry"] if flags & 1 else None,
                    data["_OverrideMotionRate_Tired"] if flags & 2 else None,
                )
            )
        result[guid] = rates
    return result


def load_action_profiles(natives: Path, enemy: str, legendary: dict) -> list[dict]:
    stm = natives / "STM"
    species, variant, _ = enemy.split("_")
    stem = f"{species.title()}_{variant}"
    pack = _record(
        path=stm
        / "GameDesign/Enemy"
        / species.title()
        / variant
        / "Data"
        / f"{stem}_CharacterParamPack.user.3.json",
        type_name="app.user_data.CharacterParamPack",
    )
    custom = {
        row["app.user_data.EmParamLegendary.ActionCustomData"]["_ActionGuid"]
        for key, rows in legendary.items()
        if key.startswith("_ActionCustomData_")
        for row in rows
    }
    profiles = []
    # The full-body rate reads the main action controller's current ACTION_ID.
    # Other holders, e.g. a tentacle's sub-action layer, control different tracks.
    main = pack["_ActionDataSetHolder"][0]["app.user_data.ActionDataSetHolder"]
    for wrapper in main["_DataSet"]:
        dataset = wrapper["app.user_data.ActionDataSet"]
        param = dataset["_Param"].get("ace.user_data.ActionParam")
        if not param:
            continue
        source = dataset["_ID"]["ace.cActionIDHolder"]["_ActionID"][
            "ace.user_data.ActionID"
        ]["path"]
        ids = _record(
            path=stm / f"{source}.3.json",
            type_name="ace.user_data.ActionID",
        )
        names = {}
        for wrapped in ids["_ActionIDArray"][
            "ace.cInstanceGuidArray`1<ace.user_data.ActionID.cID>"
        ]["_DataArray"]:
            action = wrapped["ace.user_data.ActionID.cID"]
            guid = action["_BaseActionGuid"]
            if guid == ZERO_GUID:
                guid = action["_InstanceGuid"]
            names[guid] = action["_Class"]
        parameters = _parameters(
            stm=stm,
            source=param["path"],
            names=names,
        )
        for guid, rates in parameters.items():
            if guid not in custom and not any(
                angry is not None or tired is not None for angry, tired in rates
            ):
                continue
            name = names[guid]
            if species == "EM0160":
                name = ARKVELD_ACTIONS.get(name, name)
            # A default and variants with identical rates can share the same
            # row. Keep variant positions when the player-visible totals differ.
            if all(rate == rates[0] for rate in rates):
                rates = rates[:1]
            for index, (angry, tired) in enumerate(rates):
                suffix = ""
                if len(rates) > 1:
                    suffix = f"（变体 {index}）" if index else "（默认）"
                profiles.append(
                    {
                        "guid": guid,
                        "name": name + suffix,
                        "angry": angry,
                        "tired": tired,
                    }
                )
    return profiles


def action_modifiers(
    actions: list[dict], legendary: dict, form: str, hard: bool
) -> list[dict]:
    # getActionCustomDataDic 0x1450c88a0 builds a dictionary by action GUID.
    # For King+Hard it assigns King, then Hard, then King_Hard (last wins).
    custom = {}
    for enabled, table in (
        (form == "KING", "_ActionCustomData_King"),
        (form != "NONE" and hard, "_ActionCustomData_Hard"),
        (form == "KING" and hard, "_ActionCustomData_King_Hard"),
    ):
        if enabled:
            for wrapped in legendary[table]:
                row = wrapped["app.user_data.EmParamLegendary.ActionCustomData"]
                custom[row["_ActionGuid"]] = row
    result = []
    for action in actions:
        row = custom.get(action["guid"], {})
        speed, attack = row.get("SpeedRate", 1.0), row.get("AttackRate", 1.0)
        if (
            speed != 1
            or attack != 1
            or action["angry"] is not None
            or action["tired"] is not None
        ):
            result.append(
                {
                    "guid": action["guid"],
                    "name": action["name"],
                    "speed": speed,
                    "attack": attack,
                    "angry": action["angry"],
                    "tired": action["tired"],
                }
            )
    return result
