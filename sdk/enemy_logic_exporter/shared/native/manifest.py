"""Select fresh method locations from the matching dump; preserve address aliases."""

import hashlib
import re
from .metadata import Il2cppMetadata
from .pe import PE, address_catalog
from .evidence import digest, pack_methods

SCHEDULER_TYPES = {
    "app.cEmAIState",
    "app.cEmAIStateCombat",
    "app.cEmAIStateCaution",
    "app.cEmAIStateAreaMove",
    "app.cEmAIStateDie",
    "app.cEmAIInterruptDamage",
    "app.cEmAIUpdateBTable",
    "app.cMasterEnemyControllerEntity",
    "app.cEnemyBTableManager",
    "app.cEnemyControllerEntityBase",
    "app.cEmAIStateManager",
}


def relevant_type(name, enemy):
    return (
        name in SCHEDULER_TYPES
        or name == "app.cEnemyContext"
        or name.startswith(("app.cEmAIState", "app.cEmAIInterrupt"))
        or name.casefold().startswith(f"app.{enemy}_btable".casefold())
        or name.startswith(
            (
                f"app.{enemy}_BTable",
                f"app.{enemy}BTableCommand.",
                "app.btable.EmCommonCommand.",
                f"app.btable.{enemy}BTableCommand.",
                "ace.btable.",
            )
        )
        or any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in (f"app.c{enemy}Extend", f"app.c{enemy.split('_')[0]}Extend")
        )
    )


def discovery_types(metadata, enemy):
    """Keep concrete contexts and walk declared parents instead of naming only Export."""
    names = metadata._objects or metadata._offsets
    selected_types = {
        name for name in names if relevant_type(name, enemy) and "[]" not in name
    }
    pending = list(selected_types)
    while pending:
        name = pending.pop()
        parent = (metadata.get(name) or {}).get("parent")
        if (
            parent in names
            and parent not in selected_types
            and parent != "System.Object"
        ):
            selected_types.add(parent)
            pending.append(parent)
    return sorted(selected_types)


def selected(name, method, enemy, selection):
    if selection == "all":
        # Include parent, scheduler and special-command methods, not only Export.
        return relevant_type(name, enemy) and "[]" not in name
    enemy_type = (
        name.casefold().startswith(f"app.{enemy}_btable_".casefold())
        and "<" not in name
    )
    base_type = (
        name.startswith("app.btable.Em") or name.startswith("ace.btable.c")
    ) and "<" not in name
    base_type |= (
        name
        == "ace.btable.cCommandFunc`2<app.btable.EmCommonCommand.cCheckDistanceArg,System.Boolean>"
    )
    if selection == "base":
        return (base_type or enemy_type) and (
            enemy_type
            and "CommonAttack_Export" in name
            and method.startswith(("table_", ".ctor"))
            or method.startswith(
                (
                    "onExecute",
                    "updateTableInpl",
                    "execute",
                    "setCurrentPosition",
                    "get_TargetPosition",
                )
            )
        )
    if selection == "upstream":
        return (enemy_type or name.startswith("ace.btable") and "<" not in name) and (
            enemy_type
            and "Combat_Export" in name
            or any(
                token in method
                for token in (
                    "Script",
                    "Random",
                    "Timer",
                    "setup",
                    "Setup",
                    "Import",
                    "init",
                    "Init",
                )
            )
            or name == "ace.btable.cVariableStorage"
            and method.startswith("update")
        )
    return (
        selected(name, method, enemy, "base")
        or selected(name, method, enemy, "upstream")
        or (enemy_type and "_Export" in name)
    )


def build_manifest(exe, metadata_path, enemy, selection, version, helpers=()):
    if not re.fullmatch(r"Em\d{4}_\d{2}", enemy):
        raise ValueError("Enemy must look like Em0001_00")
    rows, skipped, fields = [], [], {}
    with Il2cppMetadata(metadata_path) as metadata, PE(exe) as pe:
        aliases = address_catalog(metadata)
        pe.method_starts = sorted(aliases)
        for name in discovery_types(metadata, enemy):
            info = metadata.get(name)
            for method, details in info.get("methods", {}).items():
                if selection != "all" and not selected(name, method, enemy, selection):
                    continue
                address = int(details.get("function", "0"), 16)
                if not address:
                    skipped.append(
                        {"type": name, "method": method, "reason": "no native address"}
                    )
                    continue
                end = pe.end(address)
                if not 0 < end - address < 200000:
                    skipped.append(
                        {
                            "type": name,
                            "method": method,
                            "reason": "unreviewed function bound",
                        }
                    )
                    continue
                rows.append(
                    method_row(pe, metadata, aliases, name, method, address, end)
                )
        for address in helpers:
            name, method = aliases.get(address, [("native_helper", hex(address))])[0]
            rows.append(
                method_row(
                    pe, metadata, aliases, name, method, address, pe.end(address)
                )
            )
        for name in (
            "ace.btable.cVariableStorage",
            "ace.btable.cVariableStorage.cRuntimeTimer",
            "ace.btable.user_data.BTableVariable.TimerValueInfo",
            "app.cEnemyBTableCommandWork",
            "app.cEnemyBTableOperatorWork",
            "app.btable.EmCommonCommand.cCheckStatusStatusArg.CONDITION_TYPE",
        ):
            fields[name] = metadata.fields(name)
        profile = {
            "gameVersion": version,
            "exeSha256": digest(exe),
            "metadataSha256": metadata.sha256,
        }
    return pack_methods(
        rows, profile, enemy=enemy, selection=selection, fields=fields, skipped=skipped
    )


def method_row(pe, metadata, aliases, name, method, address, end):
    info = metadata.get(name) or {}
    details = info.get("methods", {}).get(method, {})
    body = pe.read(address, end - address)
    if len(body) != end - address:
        raise ValueError(f"Method is not fully backed by file bytes: {hex(address)}")
    return dict(
        type=name,
        method=method,
        address=hex(address),
        end=hex(end),
        label="mhws_" + hashlib.sha256((name + method).encode()).hexdigest()[:16],
        parameters=details.get("params"),
        nativeSha256=hashlib.sha256(body).hexdigest(),
        fields=info.get("fields", {}),
        addressAliases=aliases.get(address, []),
    )
