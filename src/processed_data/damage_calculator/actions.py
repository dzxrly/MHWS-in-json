"""Selectable actions tied to exact collision records and shell resources."""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from config import ACTION_MAP_PATH, ZH_HANS_LANGUAGE_ID
from src.shared.action_values.catalog import load_action_value_catalog, mapping_names
from src.shared.text.catalog import TextSource
from src.processed_data.skill_effects.specs import WEAPONS
from .weapon_states import bow_parameters, shared_bow_parameters, chargeblade_phial_kind
from .gunlance import SHELL_TYPES, SUPPORTED_TYPES

def profile_id(key) -> str:
    return f"{key.scope}|{key.rcol}|{key.request_set_id}|{key.key_hash}|{key.source_ordinal}"


def collision_skill_tags(scope: str, key, properties: dict, gunlance: dict | None = None) -> list[str]:
    tags = ["hien"] if properties.get("_IsSkillHien") else []
    if re.fullmatch(r"Wp(?:0[0-9]|10)", scope) and (
        not properties.get("_IsNoUseKireaji") or properties.get("_IsForceUseKireajiAttackRate")
    ):
        tags.append("sharpness")
    if chargeblade_phial_kind(scope, key.rcol, key.request_set_id, properties) == "impact":
        tags.append("chargeblade_artillery")
    if gunlance and gunlance["type"] in SUPPORTED_TYPES:
        tags.append("gunlance_artillery")
    return tags


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


def gunlance_resource(natives_dir: Path, path: str) -> dict | None:
    shot = next((row["app.cShellminiParamPlWp07Shot"] for row in shell_parameters(natives_dir, path)
                 if "app.cShellminiParamPlWp07Shot" in row), None)
    if shot is None:
        return None
    kind = re.sub(r"^\[-?\d+\]\s*", "", shot["_ShellType"])
    if kind not in SHELL_TYPES:
        raise ValueError(f"Unknown gunlance projectile type: {kind}")
    return {"source": "STM/" + path + ".3.json", "type": kind}


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
                # Share the common MappingName resolver, including internal/resource
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
                    gunlance = gunlance_resource(natives_dir, path)
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
                        "skillTags": collision_skill_tags(scope, key, record.properties, gunlance),
                        # Normal/spread and elemental shells share resources across levels.
                        # cHunterWpGunHandling.doOnHit_AttackPre reads the runtime Lv2/Lv3 rates.
                        # WeaponData._ShellLv entries for FIRE/WATER/ELEC/ICE use SL_000/001.
                        "ammoLevels": shared_levels or [level or 1],
                        "arrowType": arrow_type(natives_dir, path) or (next(iter(arrows)) if len(arrows) == 1 else None),
                        "shell": shell,
                        "gunlance": gunlance,
                        "bow": bow_resource(natives_dir, path) if path else shared_bow_parameters(
                            profile_bows.get((scope, key.rcol, key.request_set_id, key.key_hash, key.source_ordinal), [])),
                    })
                    labels.setdefault(key, set()).add(name)
    # An unnamed collision is still a selectable, exactly identified hit. Do
    # not invent an action relation or a translated name for missing mappings.
    bound = {action["profileId"] for action in actions}
    for scope, records in catalog.records.items():
        if not re.fullmatch(r"Wp\d\d", scope):
            continue  # Shared ammunition needs explicit weapon/resource evidence.
        for record in records:
            identity = profile_id(record.key)
            if identity in bound:
                continue
            actions.append({
                "id": hashlib.sha256(f"unmapped|{identity}".encode()).hexdigest()[:24],
                "name": f"未命名命中 {Path(record.key.rcol).name.split('.')[0]} #{record.key.request_set_id}",
                "profileId": identity, "weapons": [WEAPONS[int(scope[2:])]],
                "kind": "Unmapped", "nameSource": "exact_collision_identity",
                "mappingIdentity": "", "confidence": "profile_only", "conditions": "",
                "ammoLevel": 1, "ammoLevels": [1], "arrowType": None,
                "skillTags": collision_skill_tags(scope, record.key, record.properties),
                "shell": None, "bow": None,
            })
    return {key: sorted(names) for key, names in labels.items()}, actions, {
        "sha256": hashlib.sha256(ACTION_MAP_PATH.read_bytes()).hexdigest(),
        "inputs": document["inputs"], "nativeEvidenceReused": False,
    }
