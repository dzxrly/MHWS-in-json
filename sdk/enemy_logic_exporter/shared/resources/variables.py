"""Index BTable variable definitions (timers, floats, Booleans) by GUID.

A table may read variables declared in another monster's shared list, so the
index covers every BTableVariable resource. Only definitions are recorded:
initial values say nothing about the live value during a fight.
"""

import hashlib
import json

from .reader import typed

VARIABLE_LISTS = {
    "TimerValueInfoList": "timer",
    "FloatValueInfoList": "float",
    "BoolValueInfoList": "bool",
}
VARIABLE_RESOURCE_SUFFIX = "_btablevariable.user.3.json"


def _index(resources):
    result = {}
    for key, path in sorted(resources.paths.items()):
        if not key.endswith(VARIABLE_RESOURCE_SUFFIX):
            continue
        source = path.relative_to(resources.root).as_posix()
        raw = path.read_bytes()
        data = json.loads(raw)
        for item in data if isinstance(data, list) else [data]:
            _, body = typed(item)
            for field, kind in VARIABLE_LISTS.items():
                for entry in body.get(field, []):
                    _, value = typed(entry)
                    guid = value["InstanceGUID"]
                    record = dict(
                        kind=kind,
                        default=value.get("_DefaultValue"),
                        life=str(value.get("_Life", "")).split("] ", 1)[-1],
                        resource=source,
                        resourceSha256=hashlib.sha256(raw).hexdigest(),
                    )
                    if guid in result and result[guid] != record:
                        result[guid]["alsoDeclaredIn"] = sorted(
                            set(result[guid].get("alsoDeclaredIn", [])) | {source}
                        )
                    else:
                        result.setdefault(guid, record)
    return result


_CACHE = {}


def variable_index(resources):
    key = str(resources.root)
    if key not in _CACHE:
        _CACHE[key] = _index(resources)
    return _CACHE[key]


def referenced_variables(model, resources):
    """Definitions of the timer/variable GUIDs that this model's checks read."""
    guids = set()
    for table in model["tables"]:
        for node in table["nodes"]:
            values = node.get("predicate", {}).get("values", {})
            if "variable" in values:
                guids.add(str(values["variable"]))
            source = node.get("argument", {}).get("_SourceValue")
            if isinstance(source, dict):
                guids.update(str(v) for v in source.values() if isinstance(v, str))
    index = variable_index(resources)
    return {guid: index[guid] for guid in sorted(guids) if guid in index}
