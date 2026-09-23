"""Read the seven sharpness damage rates from the enemy common parameters."""

import json
import math
from pathlib import Path


SOURCE_PATH = "STM/GameDesign/Enemy/CommonData/Data/EmCommonData.user.3.json"
RATE_TYPE = "app.user_data.EmParamCommon.cKireajiRate"
COLORS = (
    ("RED", "红"), ("ORANGE", "橙"), ("YELLOW", "黄"),
    ("GREEN", "绿"), ("BLUE", "蓝"), ("WHITE", "白"), ("PURPLE", "紫"),
)


def sharpness_catalog(natives_dir: Path) -> list[dict]:
    document = json.loads((Path(natives_dir) / SOURCE_PATH).read_text(encoding="utf-8"))
    table = document[0]["app.user_data.EmParamCommon"]["_KireajiTable"]
    if not isinstance(table, dict) or len(table) != 1:
        raise ValueError("Invalid sharpness table wrapper")
    rows = next(iter(table.values()))["_ParamList"]
    if not isinstance(rows, list) or len(rows) != len(COLORS):
        raise ValueError("Expected seven sharpness rates")
    by_color = {}
    for entry in rows:
        value = entry[RATE_TYPE]
        color = value["EnumValue"].split("] ", 1)[-1]
        if color in by_color:
            raise ValueError(f"Duplicate sharpness color: {color}")
        rates = (value["Damage"], value["Elem"])
        if any(isinstance(rate, bool) or not isinstance(rate, (int, float))
               or not math.isfinite(rate) or rate <= 0 for rate in rates):
            raise ValueError(f"Invalid sharpness rates: {color}")
        by_color[color] = rates
    if set(by_color) != {color for color, _ in COLORS}:
        raise ValueError("Incomplete sharpness colors")
    return [
        {"id": color.lower(), "name": f"{name}斩", "physical": by_color[color][0],
         "element": by_color[color][1]}
        for color, name in COLORS
    ]
