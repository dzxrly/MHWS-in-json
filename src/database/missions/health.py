"""Calculate initial solo health for enemies in mission main-target layouts."""

import json
import math
import re
import struct
from pathlib import Path

from config import MISSION_HEALTH_KING_WHEN_NONE_IDS, MISSION_HEALTH_NO_AUTO_HARD_IDS


ENEMY_ID = re.compile(r"EM(\d{4})_(\d{2})_\d+")
REWARD_RANK = re.compile(r"REWARD_RANK_(\d+)$")


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _record(path: Path, type_name: str) -> dict:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)[0][type_name]


def _reference(data: dict, field: str, type_name: str) -> str:
    return data[field][type_name]["path"]


def calculate_solo_health(
    *,
    enemy_id: str,
    base_health: int,
    quest_health_rate: float,
    legendary_id: str,
    reward_rank: int,
    legendary_rates: dict,
    random_rate_table: dict,
    random_probability_tables: list[dict],
    difficulty_adjust_range: int,
    king_when_none_ids: frozenset[str],
    no_auto_hard_ids: frozenset[str],
    preset_hard: bool = False,
) -> int | str:
    """Calculate all possible initial solo HP values from resolved user3 inputs.

    In IL2CPP, locate EnemyUtil.getMaxHealth_Difficulty in il2cpp_dump.json,
    then inspect its address in the *matching game's executable*. The dump
    gives method addresses and field metadata, not the native instructions.
    Follow its base-health, quest-difficulty, random-rate and legendary-rate
    reads, and trace the caller that converts max HP to an integer. Inspect
    EnemyUtil.getLegendaryID_LegendaryParam for the King override, and
    cContextInstanceController_Enemy.onSetupContext for the automatic Hard
    branch. Compare field offsets with EmParamParts, EmParamDifficulty2,
    EmParamLegendary and cEmModuleBasic in the same dump. Recheck compiled
    enemy-ID checks after a game update; user3 does not encode them.

    Formula for one random grade: ceil(float32(float32(_BaseHealth) *
    float32(quest _Health) * float32(random _Value*) * float32(legend rate))).
    The selected _DifficultyAdjustRange chooses a probability table; every
    _Prob* field with positive probability pairs with its _Value* field.
    Distinct outcomes are returned in ascending order, joined with `、`.
    """
    # The rates themselves are user3 fields. A pre-set Hard flag survives
    # onSetupContext; otherwise reward rank can set it, except for the native
    # no-auto-Hard enemy IDs. The separate King override forces Hard itself.
    hard = preset_hard
    if not hard and enemy_id not in no_auto_hard_ids:
        hard = (
            (legendary_id == "NORMAL" and reward_rank >= 9)
            or (legendary_id == "KING" and reward_rank >= 10)
        )
    if legendary_id == "NONE":
        if reward_rank == 10 and enemy_id in king_when_none_ids:
            legendary_rate = legendary_rates["HealthRate_King_Hard"]
        else:
            if (
                reward_rank == 10 and enemy_id not in king_when_none_ids
                and legendary_rates["HealthRate_King_Hard"] != 1.0
            ):
                raise ValueError(
                    f"Ambiguous rank-10 NONE legendary rate for {enemy_id}; "
                    "check the matching IL2CPP executable and config.py"
                )
            legendary_rate = 1.0
    elif legendary_id == "NORMAL":
        rate_field = "HealthRate_Hard" if hard else "HealthRate"
        legendary_rate = legendary_rates[rate_field]
    elif legendary_id == "KING":
        rate_field = "HealthRate_King_Hard" if hard else "HealthRate_King"
        legendary_rate = legendary_rates[rate_field]
    else:
        raise ValueError(f"Unknown legendary ID {legendary_id} for {enemy_id}")

    if not 0 <= difficulty_adjust_range < len(random_probability_tables):
        raise ValueError(f"Unknown difficulty adjust range {difficulty_adjust_range} for {enemy_id}")
    probabilities = random_probability_tables[difficulty_adjust_range]
    health_values = set()
    for field, probability in probabilities.items():
        if not field.startswith("_Prob") or probability <= 0:
            continue
        suffix = field.removeprefix("_Prob")
        rate_field = f"_Value{suffix}"
        if rate_field not in random_rate_table:
            raise ValueError(f"Missing random health rate {rate_field} for {enemy_id}")
        health_values.add(math.ceil(_float32(
            _float32(base_health)
            * _float32(quest_health_rate)
            * _float32(random_rate_table[rate_field])
            * _float32(legendary_rate)
        )))
    if not health_values:
        raise ValueError(f"No health random grades for {enemy_id} range {difficulty_adjust_range}")
    sorted_values = sorted(health_values)
    return sorted_values[0] if len(sorted_values) == 1 else "、".join(map(str, sorted_values))


class SoloHealthCalculator:
    """Resolve user3 inputs, then delegate arithmetic to calculate_solo_health.

    QuestData's clear target is matched to the selected MsData enemy set and
    BossZako layout main target in difficulty.py. That target's difficulty
    GUID selects a rate in EmCommonDifficulty2; its range selects the random
    probability row. The target EmID selects Resident._Parts._BaseHealth and
    ParamPack._Legendary's four HealthRate fields.
    """

    def __init__(self, natives_dir: Path, difficulty_data: dict):
        self.stm_dir = natives_dir / "STM"
        # The native health path reads the first random-rate table; grade
        # names and their probabilities are discovered from user3 fields.
        self.health_random_table = difficulty_data["_RandomRateTblArray"][0][
            "app.user_data.EmParamDifficulty2.cRandomRateTable"
        ]
        self.random_probabilities = [
            item["app.user_data.EmParamDifficulty2.cRandomProbabilityTable"]
            for item in difficulty_data["_RandomProbabilityTblArray"]
        ]
        self.enemy_params: dict[str, tuple[int, dict]] = {}

    def calculate(self, main_target: dict, difficulty_rate: dict) -> int | str:
        enemy_id = main_target["_EmID"].split()[-1]
        legendary_id = main_target["_LegendaryID"].split()[-1]
        rank_name = difficulty_rate["_RewardRank"].split()[-1]
        rank_match = REWARD_RANK.fullmatch(rank_name)
        if rank_match is None:
            raise ValueError(f"Unknown reward rank {rank_name} for {enemy_id}")
        base_health, legendary = self._params(enemy_id)
        return calculate_solo_health(
            enemy_id=enemy_id,
            base_health=base_health,
            quest_health_rate=difficulty_rate["_Health"],
            legendary_id=legendary_id,
            reward_rank=int(rank_match.group(1)),
            legendary_rates=legendary,
            random_rate_table=self.health_random_table,
            random_probability_tables=self.random_probabilities,
            difficulty_adjust_range=int(main_target["_DifficultyAdjustRange"]),
            king_when_none_ids=MISSION_HEALTH_KING_WHEN_NONE_IDS,
            no_auto_hard_ids=MISSION_HEALTH_NO_AUTO_HARD_IDS,
            preset_hard=False,  # MainTarget user3 does not carry this runtime flag.
        )

    def _params(self, enemy_id: str) -> tuple[int, dict]:
        cached = self.enemy_params.get(enemy_id)
        if cached is not None:
            return cached
        match = ENEMY_ID.fullmatch(enemy_id)
        if match is None:
            raise ValueError(f"Unknown enemy ID {enemy_id}")
        species, variant = match.groups()
        resident = _record(
            self.stm_dir / "GameDesign/Enemy/Resident" / f"{enemy_id}_Resident.user.3.json",
            "app.user_data.EnemyResident",
        )
        parts_path = _reference(resident, "_Parts", "app.user_data.EmParamParts")
        parts = _record(self.stm_dir / f"{parts_path}.3.json", "app.user_data.EmParamParts")

        pack = _record(
            self.stm_dir / "GameDesign/Enemy" / f"Em{species}" / variant / "Data"
            / f"Em{species}_{variant}_ParamPack.user.3.json",
            "app.user_data.EnemyParamPack",
        )
        legendary_path = _reference(pack, "_Legendary", "app.user_data.EmParamLegendary")
        legendary = _record(
            self.stm_dir / f"{legendary_path}.3.json", "app.user_data.EmParamLegendary"
        )
        result = int(parts["_BaseHealth"]), legendary
        self.enemy_params[enemy_id] = result
        return result
