"""Shared hunting-horn melodies, distinct from weapon-only self improvement."""

import json
import math
from pathlib import Path

from src.shared.text.catalog import TextSource
from .weapon_states import MUSIC_SOURCE

MELODIES = {
    "small": ("ATK_UP_S", "f9101a27-9275-4dda-9fb0-658816e4851a"),
    "large": ("ATK_UP_L", "ed91bb2e-3674-4bba-9cc0-8e06c2caafde"),
    "element": ("ELEM_ATK_UP", "55024332-ddc8-426f-83e0-9d40a5bc7d2b"),
}


def music_parameters(natives_dir: Path, text_source: TextSource) -> dict:
    params = json.loads((natives_dir / MUSIC_SOURCE).read_text(encoding="utf-8"))[0]["app.user_data.PlayerMusicSkillParam"]
    rows = [next(iter(row.values())) for row in next(iter(params["_MusicSkillData"].values()))["_ParamList"]]
    text = text_source.build(13)
    result = {"source": MUSIC_SOURCE, "attack": [], "element": []}
    for identity, (symbol, guid) in MELODIES.items():
        row = next(row for row in rows if row["EnumValue"].split("] ")[-1] == symbol)
        name = text.get(guid)
        if not name:
            raise ValueError(f"Missing official melody name: {guid}")
        for encore, field in ((False, "_ValueDatas"), (True, "_WValueDatas")):
            result["element" if identity == "element" else "attack"].append({
                "id": identity + ("Encore" if encore else ""), "name": name + (" · 重奏" if encore else ""),
                "nameGuid": guid, "rate": row[field][0]["app.user_data.PlayerMusicSkillParam.cMusicSkillValueData"],
                "parameter": f"{symbol}.{field}[0]",
            })
    # getSkillRate 0x145312380 selects one ATK_UP_L/S and normal/encore value.
    # calcCurrentAttackPower 0x147590584 -> 0x147590821 -> capped rate at 0x1475908E3.
    # calcElemFireRate 0x1455EBB25 (and the other four elements) multiplies the
    # melody into the element rate; calcAttrPower adds flats then caps at 0x1475912E9+.
    validate_music(result)
    return result


def validate_music(music: dict) -> None:
    if music.get("source") != MUSIC_SOURCE:
        raise ValueError("Invalid melody source")
    for category, expected in (("attack", {"small", "smallEncore", "large", "largeEncore"}),
                               ("element", {"element", "elementEncore"})):
        entries = music.get(category, [])
        if len(entries) != len(expected) or {entry.get("id") for entry in entries} != expected:
            raise ValueError("Invalid melody choices")
        for entry in entries:
            rate = entry.get("rate")
            if (not entry.get("name") or not entry.get("parameter")
                    or entry.get("nameGuid") != MELODIES[entry["id"].removesuffix("Encore")][1]
                    or isinstance(rate, bool) or not isinstance(rate, (int, float))
                    or not math.isfinite(rate) or rate <= 0):
                raise ValueError("Invalid melody parameter")
