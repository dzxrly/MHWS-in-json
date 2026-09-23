"""Source-backed item bonuses retained in the damage calculator catalog."""

import json
from pathlib import Path

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


def item_catalog(natives_dir: Path) -> dict:
    raw = json.loads((natives_dir / ITEM_PATH).read_text(encoding="utf-8"))
    item_values = raw[0]["app.user_data.PlayerItemParam"]
    items = []
    for item_id, (name, field, group) in ITEM_FIELDS.items():
        value = item_values[field]
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"Invalid item bonus: {field}")
        items.append({"id": item_id, "name": name, "flat": value, "group": group})
    return {"items": items}
