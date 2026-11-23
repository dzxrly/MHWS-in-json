"""Combat action multipliers from the 1.42.0.3 executable and IL2CPP metadata.

The target layout selects a difficulty GUID, attack/HP rolls and party table.
onSetupContext (0x1458f7c40) sets the Hard flag; getLegendaryID_LegendaryParam
(0x1455bde90) resolves the effective form. getMotionSpeedRate (0x1450c8140)
reads exactly one form rate. doUpdateEnd (0x14943e828–0x14943ead2) applies
the active angry/tired parameter or its current-action override to CoreState.
doBaseActionEnter (0x1494416db–0x149441739) independently sets Action by GUID.
calcMotionSpeedTotal (0x149443690) includes Action, CoreState and Sequence
in ordinary combat, and clamps only after other active factors. The consumer
applyTotalSpeedToMotionCompSpeed passes that result to Motion.Speed.

These are combat action baselines. A live animation can further change
Sequence (cMotSpeedScale.doRangeUpdate), a single motion layer, or BlendTree
(cMotSpeedScale_MotSync.doRangeUpdate). These depend on the clip and frame.
"""

from pathlib import Path

from config import MISSION_HEALTH_KING_WHEN_NONE_IDS, MISSION_HEALTH_NO_AUTO_HARD_IDS
from src.database.missions.health import _record, legendary_form
from src.site_data.mission_actions import action_modifiers, load_action_profiles
from src.site_data.mission_damage import damage_conditions, incoming_conditions
from src.site_data.mission_shells import load_shell_names, shell_modifiers

# applyPreCalcAttack 0x1455bd2c0: without Hard, only these enemy IDs also
# apply the tempered attack multiplier to the elemental channel.
ELEMENTAL_LEGENDARY_IDS = {
    "NORMAL": {"EM0078_00_0", "EM0166_00_0"},
    "KING": {"EM0078_00_0", "EM0158_00_0", "EM0160_00_0", "EM0162_00_0", "EM0166_00_0"},
}


def load_speed_bounds(natives: Path) -> tuple[float, float]:
    common = _record(
        path=natives / "STM/GameDesign/Enemy/CommonData/Data/EmCommonData.user.3.json",
        type_name="app.user_data.EmParamCommon",
    )
    return common["TotalMotionSpeedMin"], common["TotalMotionSpeedMax"]


def _referenced(stm: Path, field: dict, type_name: str) -> dict:
    ref = field.get(type_name)
    if not ref:
        return {}
    return _record(
        path=stm / (ref["path"] + ".3.json"),
        type_name=type_name,
    )


def load_combat_profile(natives: Path, enemy: str, role: str) -> dict:
    stm = natives / "STM"
    species, variant, _ = enemy.split("_")
    stem = f"{species.title()}_{variant}"
    pack = _record(
        path=stm
        / "GameDesign/Enemy"
        / species.title()
        / variant
        / "Data"
        / f"{stem}_ParamPack.user.3.json",
        type_name="app.user_data.EnemyParamPack",
    )
    overrides = {}
    if role == "FRENZY":
        overrides = _referenced(
            stm=stm,
            field=pack["_Frenzy"],
            type_name="app.user_data.EmParamFrenzy",
        )
    profile = {}
    for field, type_name in (
        ("_Legendary", "EmParamLegendary"),
        ("_Angry", "EmParamAngry"),
        ("_Stamina", "EmParamStamina"),
    ):
        key = f"app.user_data.{type_name}"
        source = overrides.get(field + "Param", {})
        if key not in source:
            source = pack[field]
        profile[field] = _referenced(
            stm=stm,
            field=source,
            type_name=key,
        )
    profile["shellNames"] = load_shell_names(
        stm=stm,
        pack=pack,
        legendary=profile["_Legendary"],
    )
    profile["actions"] = load_action_profiles(
        natives=natives,
        enemy=enemy,
        legendary=profile["_Legendary"],
    )
    if enemy in {"EM0071_00_0", "EM0156_00_0", "EM0164_50_0", "EM0166_00_0"}:
        resident = _record(
            path=stm
            / f"GameDesign/Enemy/CommonData/StageResident/Data/{enemy.title()}_StageResident.user.3.json",
            type_name="app.user_data.EnemyStageResident",
        )
        unique = _referenced(
            stm=stm,
            field=resident["_Unique"],
            type_name="app.user_data.EmParamUnique",
        )
        profile["unique"] = unique["_SpeciesInfo"][f"app.c{stem}ParamUniqueInfo"]
    return profile


def _state_rates(
    profile: dict,
    enemy: str,
    form: str,
    hard: bool,
    upper: bool,
) -> tuple[dict, float]:
    legendary = profile["_Legendary"]
    suffix = ("_King" if form == "KING" else "") + ("_Hard" if hard else "")
    tempered = form != "NONE"
    elemental = tempered and (hard or enemy in ELEMENTAL_LEGENDARY_IDS[form])
    base_speed = 1.0
    if tempered:
        base_speed = legendary["MotionSpeedRate_Hard" if hard else "MotionSpeedRate"]
        if (
            form == "KING"
            and hard
            and legendary["IsEnableOverrideMotionSpeed_King_Hard"]
        ):
            base_speed = legendary["OverrideMotionSpeed_King_Hard"]
    state_params = {"normal": {}}
    # QuestUtil.getQuestRank / EnvironmentManager.get_CurrentRank select
    # upper from quest level 4. onSetupContext (0x1458f8dc2–0x1458f8e02)
    # separately selects Hard from the target's reward rank and form.
    rank = "_DataLvUpper" if upper else "_DataLvLower"
    # Angry/Tired.initialize (0x145feb910/0x1452e7af0): positive duration
    # enables the condition. When both flags are set, the angry branch wins.
    for state, param, record, duration in (
        ("angry", "_Angry", "app.user_data.EmParamAngry.cData", "_AngrySec"),
        ("tired", "_Stamina", "app.user_data.EmParamStamina.Data", "_TiredSec"),
    ):
        settings = profile[param].get(rank, {}).get(record)
        if settings and settings[duration] > 0:
            state_params[state] = settings
    rates = {}
    for state, settings in state_params.items():
        attack_field = "AngryAttackRate" if state == "angry" else "NoAngryAttackRate"
        attack = settings["_AttackRate"] if state == "angry" else 1.0
        legendary_attack = legendary[attack_field + suffix] if tempered else 1.0
        # Keep this product unclamped until all selected action/phase factors
        # are present. calcMotionSpeedTotal clamps the combined product.
        motion = settings.get("_MotionRate", 1.0)
        form_element = legendary_attack if elemental else 1.0
        rates[state] = {
            "speed": round(number=base_speed * motion, ndigits=9),
            "physical": attack * legendary_attack,
            "element": attack * form_element,
            "damage": settings["_DamageRate"] if state == "angry" else 1.0,
            "factors": {
                "motion": motion,
                "attack": attack,
                "formPhysical": legendary_attack,
                "formElement": form_element,
            },
        }
    if enemy == "EM0071_00_0" and "angry" in rates:
        # Gore Magala's SUPER state forces anger. Its virtual motion getter
        # replaces the angry rate; adjustAttackParam scales physical only.
        # 0x147bb57d0, 0x147bb4420, 0x147bb4460.
        unique = profile["unique"]
        rates["angrySuper"] = {
            **rates["angry"],
            "speed": base_speed * unique["StateSuperofAngryMotionRate"],
            "physical": rates["angry"]["physical"]
            * unique["StateSuperofAngryAttackRate"],
            "factors": {
                **rates["angry"]["factors"],
                "motion": unique["StateSuperofAngryMotionRate"],
                "speciesPhysical": unique["StateSuperofAngryAttackRate"],
            },
        }
    return rates, legendary["PartsVitalRate" + suffix] if tempered else 1.0


def target_combat(
    row: dict,
    profile: dict,
    enemy: str,
    state: str,
    upper: bool,
    max_players: int,
    speed_bounds: tuple[float, float],
) -> dict:
    reward_rank = int(row["_RewardRank"].removeprefix("REWARD_RANK_"))
    form, hard = legendary_form(
        enemy_id=enemy,
        legendary_id=state,
        reward_rank=reward_rank,
        king_when_none_ids=MISSION_HEALTH_KING_WHEN_NONE_IDS,
        no_auto_hard_ids=MISSION_HEALTH_NO_AUTO_HARD_IDS,
    )
    rates, parts_rate = _state_rates(
        profile=profile,
        enemy=enemy,
        form=form,
        hard=hard,
        upper=upper,
    )
    selected_actions = action_modifiers(
        actions=profile["actions"],
        legendary=profile["_Legendary"],
        form=form,
        hard=hard,
    )
    actions = []
    for action in selected_actions:
        speeds = {}
        for name, values in rates.items():
            override = action.get("angry" if name == "angrySuper" else name)
            motion = (
                values["speed"]
                if override is None
                else rates["normal"]["speed"] * override
            )
            speeds[name] = round(number=motion * action["speed"], ndigits=9)
        if action["attack"] != 1 or any(
            speeds[name] != rates[name]["speed"] for name in rates
        ):
            actions.append(
                {
                    "name": action["name"],
                    "speed": speeds,
                    "attack": action["attack"],
                    "speedRate": action["speed"],
                    "motionOverrides": {
                        key: action[key]
                        for key in ("angry", "tired")
                        if action[key] is not None
                    },
                }
            )
    grades = row["attackGrades"]
    parties = []
    for players in range(1, max_players + 1):
        # Solo has no multiplayer table row. Difficulty's unique-rate table
        # is empty in this revision. Action/projectile multipliers are neutral.
        prefix = f"_Count={players}."
        hp, party_attack, parts, damage = (
            (1.0, 1.0, 1.0, 1.0)
            if players == 1
            else (
                row[prefix + "_Health"],
                row[prefix + "_Attack"],
                row[prefix + "_PartsVital"],
                row[prefix + "_Damage"],
            )
        )
        attack = party_attack * row["_Attack"]
        states = {}
        for name, values in rates.items():
            # applyPreCalcAttack 0x1455bd2c0 and calcDamageRate 0x145ff3b70.
            incoming = damage * values["damage"]
            states[name] = {
                "speed": values["speed"],
                "physical": [
                    round(
                        number=attack * values["physical"] * rate,
                        ndigits=9,
                    )
                    for _, _, rate in grades
                ],
                "element": [
                    round(
                        number=attack * values["element"] * rate,
                        ndigits=9,
                    )
                    for _, _, rate in grades
                ],
                "slash": round(
                    number=row["_DamageSlashBlow"] * incoming,
                    ndigits=9,
                ),
                "shot": round(
                    number=row["_DamageShot"] * incoming,
                    ndigits=9,
                ),
            }
        parties.append(
            {
                "players": players,
                "hp": hp,
                "scaling": {"attack": party_attack, "parts": parts, "damage": damage},
                "health": [
                    {"hp": value, "probability": probability}
                    for value, probability in row["healthByPlayers"][players].items()
                ],
                # cEmModuleParts.applyDifficulty 0x1493dabf0, common part vital.
                "parts": round(
                    number=row["_PartsVital"] * parts * parts_rate,
                    ndigits=9,
                ),
                "states": states,
            }
        )
    return {
        "factors": {
            "form": form,
            "hard": hard,
            "rewardRank": reward_rank,
            "upper": upper,
            "formSpeed": rates["normal"]["speed"],
            "formParts": parts_rate,
            "questAttack": row["_Attack"],
            "questParts": row["_PartsVital"],
            "questSlash": row["_DamageSlashBlow"],
            "questShot": row["_DamageShot"],
            "states": {
                name: {**values["factors"], "received": values["damage"]}
                for name, values in rates.items()
            },
        },
        "speedBounds": speed_bounds,
        "actions": actions,
        "damageConditions": damage_conditions(
            enemy=enemy,
            unique=profile.get("unique", {}),
            option_tag=row["_OptionTag"],
        ),
        "incomingConditions": incoming_conditions(
            enemy=enemy,
            unique=profile.get("unique", {}),
            upper=upper,
        ),
        "shells": shell_modifiers(
            legendary=profile["_Legendary"],
            names=profile["shellNames"],
            form=form,
            hard=hard,
            enemy=enemy,
            actions=selected_actions,
        ),
        "grades": [
            {"grade": grade, "probability": probability, "rate": rate}
            for grade, probability, rate in grades
        ],
        "parties": parties,
    }
