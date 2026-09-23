"""A narrow, source-backed set of attack and elemental bonuses."""

import json
from pathlib import Path

from config import SUPPORT_FILES, ZH_HANS_LANGUAGE_ID
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource

SKILL_IDS = {
    "HunterSkill_000": ("attack", "always", "rate_flat"),
    "HunterSkill_005": ("fire", "always", "rate_flat"),
    "HunterSkill_006": ("water", "always", "rate_flat"),
    "HunterSkill_007": ("ice", "always", "rate_flat"),
    "HunterSkill_008": ("thunder", "always", "rate_flat"),
    "HunterSkill_009": ("dragon", "always", "rate_flat"),
    "HunterSkill_028": ("attack", "guard", "rate"),
    "HunterSkill_059": ("attack", "fullHealth", "flat"),
    "HunterSkill_060": ("attack", "redHealth", "flat"),
    "HunterSkill_110": ("attack", "knockback", "flat"),
    "HunterSkill_115": ("attack", "evade", "flat"),
}

ITEM_FIELDS = {
    "powercharm": ("力量护符", "_Talisman_Attack_Add", "charm"),
    "demondrug": ("鬼人药", "_KijinDrink_AddAttack", "drink"),
    "megademondrug": ("鬼人药G", "_KijinDrink_G_AddAttack", "drink"),
    "mightseed": ("怪力种子", "_Kairiki_AddAttack", "seed"),
    "mightpill": ("怪力药丸", "_Kairiki_G_AddAttack", "seed"),
    "demonpowder": ("鬼人粉尘", "_KijinPowder_AddAttack", "powder"),
    "demonammo": ("鬼人弹", "_KijinAmmo_AddAttack", "ammo"),
}

ITEM_PATH = Path("STM/GameDesign/Player/ActionData/Common/GlobalParam/PlayerItemParam.user.3.json")


def bonus_catalog(
    natives_dir: Path, repository: SourceRepository, text_source: TextSource
) -> dict:
    names = text_source.build(ZH_HANS_LANGUAGE_ID)
    common = {row["skillId"]: row for row in repository.table(SUPPORT_FILES["skill_common"])}
    levels_by_id: dict[str, list[dict]] = {}
    for row in repository.table("STM/GameDesign/Common/Equip/SkillData.user.3.json"):
        levels_by_id.setdefault(row["skillId"], []).append(row)
    selected = []
    for skill_id, (channel, condition, mode) in SKILL_IDS.items():
        skill = common[skill_id]
        levels = []
        for row in sorted(levels_by_id[skill_id], key=lambda entry: entry["SkillLv"]):
            values = row["value"]
            if len(values) < 2:
                raise ValueError(f"Incomplete skill values: {skill_id}")
            if mode == "rate_flat":
                percent, flat = values[:2]
            elif mode == "rate":
                percent, flat = values[0], 0
            else:
                percent, flat = 100, values[0]
            levels.append({"level": row["SkillLv"], "percent": percent, "flat": flat})
        selected.append({"id": skill_id, "name": names.get(skill["skillName"]) or skill_id,
                         "channel": channel, "condition": condition,
                         "levels": levels})
    raw = json.loads((natives_dir / ITEM_PATH).read_text(encoding="utf-8"))
    item_values = raw[0]["app.user_data.PlayerItemParam"]
    items = []
    for item_id, (name, field, group) in ITEM_FIELDS.items():
        value = item_values[field]
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"Invalid item bonus: {field}")
        items.append({"id": item_id, "name": name, "flat": value, "group": group})
    return {"skills": selected, "items": items}
