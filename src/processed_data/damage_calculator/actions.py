"""Selectable actions tied to exact collision records and shell resources."""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from config import ACTION_MAP_PATH, ZH_HANS_LANGUAGE_ID
from src.database.action_values.build import load_action_value_catalog, mapping_names
from src.shared.text.catalog import TextSource
from src.processed_data.skill_effects.specs import WEAPONS
from .weapon_states import bow_parameters, shared_bow_parameters

def profile_id(key) -> str:
    return f"{key.scope}|{key.rcol}|{key.request_set_id}|{key.key_hash}|{key.source_ordinal}"


@lru_cache(maxsize=1024)
def shell_parameters(natives_dir: Path, path: str) -> list[dict]:
    if not path:
        return []
    source = "STM/" + path + ".3.json"
    document = json.loads((natives_dir / source).read_text(encoding="utf-8"))
    return document[0]["ace.user_data.ShellMainParam"]["_ShellMiniParams"]


def gun_parameters(natives_dir: Path, path: str) -> dict | None:
    mini = shell_parameters(natives_dir, path)
    gun = next((row["app.cShellminiParamPlGun"] for row in mini
                if "app.cShellminiParamPlGun" in row), None)
    if gun is None:
        return None
    return {"source": "STM/" + path + ".3.json", "type": re.sub(r"^\[-?\d+\]\s*", "", gun["_ShellType"]),
            "parameters": {key: value for key, value in gun.items()
                           if key.startswith("_") and isinstance(value, (float, int))
                           and not isinstance(value, bool)}}


def arrow_type(natives_dir: Path, path: str) -> str | None:
    arrow = next((row["app.cShellminiParamPlWp11Arrow"] for row in shell_parameters(natives_dir, path)
                  if "app.cShellminiParamPlWp11Arrow" in row), None)
    return re.sub(r"^\[-?\d+\]\s*", "", arrow["_ArrowType"]) if arrow else None


def bow_resource(natives_dir: Path, path: str) -> dict | None:
    arrow = next((row["app.cShellminiParamPlWp11Arrow"] for row in shell_parameters(natives_dir, path)
                  if "app.cShellminiParamPlWp11Arrow" in row), None)
    return bow_parameters(natives_dir, "STM/" + path + ".3.json", arrow) if arrow else None


def action_catalog(natives_dir: Path, text_source: TextSource) -> tuple[dict, list, dict]:
    catalog = load_action_value_catalog(natives_dir, ACTION_MAP_PATH)
    texts = text_source.build(ZH_HANS_LANGUAGE_ID)
    names = mapping_names(catalog, texts.get)
    document = json.loads(ACTION_MAP_PATH.read_text(encoding="utf-8"))
    resource_evidence = {}
    profile_arrows = {}
    profile_bows = {}
    for row in document["resourceRelations"]:
        key = (row["scope"], row["rcol"], row["requestSetId"], row["keyHash"],
               row["sourceRequestSetOrdinal"], row["resourceIdentity"])
        resource_evidence[key] = row.get("evidence", [])
        if row["scope"] == "Wp11":
            for evidence in row.get("evidence", []):
                kind = arrow_type(natives_dir, evidence.get("mainParamPath", ""))
                if kind:
                    profile_arrows.setdefault(key[:5], set()).add(kind)
                    profile_bows.setdefault(key[:5], []).append(bow_resource(natives_dir, evidence.get("mainParamPath", "")))
    labels, actions, seen = {}, [], set()
    for scope, records in catalog.records.items():
        for record in records:
            key = record.key
            for binding in catalog.bindings.get(key, ()):
                # Share the DATABASE MappingName resolver, including internal/resource
                # fallbacks. Naming provenance does not change formula support status.
                name = names[(scope, binding.identity)]
                if not name:
                    continue
                evidence = resource_evidence.get((scope, key.rcol, key.request_set_id,
                            key.key_hash, key.source_ordinal, binding.identity), [])
                if scope == "Ammo":
                    weapons = sorted({WEAPONS[int(e["sourceScope"][2:])]
                                      for e in evidence if e.get("sourceScope") in {"Wp12", "Wp13"}})
                else:
                    weapons = [WEAPONS[int(scope[2:])]]
                if not weapons:
                    continue
                configurations = {(e.get("mainParamPath", ""), e.get("ammoLevel"))
                                  for e in evidence} or {("", None)}
                for path, level in sorted(configurations, key=str):
                    if scope == "Ammo":
                        weapons = sorted({WEAPONS[int(e["sourceScope"][2:])]
                                          for e in evidence
                                          if e.get("sourceScope") in {"Wp12", "Wp13"}
                                          and (e.get("mainParamPath", ""), e.get("ammoLevel")) == (path, level)})
                        if not weapons:
                            continue
                    identity = f"{binding.identity}|{profile_id(key)}|{path}|{level}"
                    if identity in seen:
                        continue
                    seen.add(identity)
                    shell = gun_parameters(natives_dir, path)
                    # A resource relation's level is not exclusive when the runtime
                    # applies level multipliers to one shared normal/spread/element shell.
                    shared_levels = ({"NORMAL": [1, 2, 3], "SHOT_GUN": [1, 2, 3],
                                      "ELEMENT": [1, 2]}.get(shell["type"]) if shell else None)
                    arrows = profile_arrows.get((scope, key.rcol, key.request_set_id,
                                                 key.key_hash, key.source_ordinal), set())
                    actions.append({
                        "id": hashlib.sha256(identity.encode()).hexdigest()[:24],
                        "name": name + (f" Lv{level}" if level and not shared_levels else ""),
                        "profileId": profile_id(key), "weapons": weapons,
                        "kind": binding.kind, "nameSource": binding.name_source,
                        "mappingIdentity": binding.identity, "confidence": binding.confidence,
                        "conditions": binding.condition, "ammoLevel": level or 1,
                        # Normal/spread and elemental shells share resources across levels.
                        # cHunterWpGunHandling.doOnHit_AttackPre reads the runtime Lv2/Lv3 rates.
                        # WeaponData._ShellLv entries for FIRE/WATER/ELEC/ICE use SL_000/001.
                        "ammoLevels": shared_levels or [level or 1],
                        "arrowType": arrow_type(natives_dir, path) or (next(iter(arrows)) if len(arrows) == 1 else None),
                        "shell": shell,
                        "bow": bow_resource(natives_dir, path) if path else shared_bow_parameters(
                            profile_bows.get((scope, key.rcol, key.request_set_id, key.key_hash, key.source_ordinal), [])),
                    })
                    labels.setdefault(key, set()).add(name)
    return {key: sorted(names) for key, names in labels.items()}, actions, {
        "sha256": hashlib.sha256(ACTION_MAP_PATH.read_bytes()).hexdigest(),
        "inputs": document["inputs"], "nativeEvidenceReused": False,
    }
