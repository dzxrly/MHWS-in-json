"""Bind individual command writes to the already verified resource arguments."""

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path


def annotate_effects(annotation, catalog):
    if annotation["kind"] != "command":
        return
    name = (
        catalog.get("inheritedCommands", {})
        .get(annotation["commandType"], {})
        .get("implementationType", annotation["commandType"])
    )
    effects = []
    for record in catalog.get("commands", {}).get(name, []):
        for effect in record.get("recoveredWrites", []):
            effect = copy.deepcopy(effect)
            value = effect["value"]
            if value["kind"] == "resource_argument_field":
                if value["argumentType"] != annotation.get("argumentType") or value[
                    "field"
                ] not in annotation.get("argument", {}):
                    continue
                value["resourceValue"] = annotation["argument"][value["field"]]
            effects.append(effect)
    annotation["partialImplementationEffects"] = effects
    annotation["commandEffectsComplete"] = False
    if effects and not annotation.get("effectSummaryAdded"):
        summaries = []
        for effect in effects:
            value = effect["value"]
            source = (
                value["field"]
                if value["kind"] == "self_extend_field"
                else json.dumps(
                    (
                        value["resourceValue"]
                        if value["kind"] == "resource_argument_field"
                        else value["value"]
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            summaries.append(effect["destination"]["field"] + " ← " + source)
        annotation["summary"] += (
            "；执行到写入分支时：" + "；".join(summaries) + "（其他条件和副作用见实现）"
        )
        annotation["effectSummaryAdded"] = True


def enrich_existing(annotations, catalog_path):
    """Update only command effects; retain all native blocks and field bindings."""
    path = Path(annotations).resolve()
    root = Path(__file__).resolve().parents[3]
    if not path.is_relative_to(root / ".agents"):
        raise ValueError("注释更新只能写入 .agents")
    index = json.loads(path.read_text(encoding="utf8"))
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf8"))
    if index["profile"] != catalog["profile"]:
        raise ValueError("命令与注释来源不匹配")
    updated = Counter()
    for source, reference in index["resources"].items():
        resource_path = path.parent / reference["path"]
        raw = resource_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("注释摘要变化")
        resource = json.loads(raw)
        sites = 0
        for method in resource["methods"]:
            for annotation in method["annotations"]:
                annotate_effects(annotation, catalog)
                if annotation.get("partialImplementationEffects"):
                    sites += 1
        resource["counts"]["partial_field_write_command"] = sites
        resource_path.write_text(
            json.dumps(resource, ensure_ascii=False, separators=(",", ":")),
            encoding="utf8",
        )
        reference["sha256"] = hashlib.sha256(resource_path.read_bytes()).hexdigest()
        reference["counts"] = resource["counts"]
        updated.update(resource["counts"])
    index["counts"] = dict(updated)
    for monster in index["monsters"]:
        counts = Counter()
        for source in monster["resources"]:
            counts.update(index["resources"][source]["counts"])
        monster["counts"] = dict(counts)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf8")
    return index
