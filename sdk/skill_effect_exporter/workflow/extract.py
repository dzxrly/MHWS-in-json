"""Assemble the skill link document: references, evaluations, sources."""

from __future__ import annotations

import json
import re
import struct
import time
from collections import defaultdict
from pathlib import Path

from sdk.enemy_logic_exporter.shared.native.evidence import digest
from sdk.enemy_logic_exporter.shared.native.metadata import Il2cppMetadata
from sdk.enemy_logic_exporter.shared.native.pe import PE

from sdk import versions

from .. import notes
from ..config import (
    EVALUATE_SKIP_PREFIXES,
    LIMIT_STATUSES,
    SCHEMA_VERSION,
)
from ..native.emulator import PathEnd
from ..runtime.evaluate import Evaluator, argument_domains
from ..runtime.scenario import Scenario, SkillWorld
from ..native.values import Unk
from ..native.scan import NativeIndex, method_stem

CONSTANT = re.compile(r"^EXE 常量 (0x[0-9a-f]+):([0-9a-f]+)$")
SCENARIO_PREFIXES = ("装备技能等级", "参数", "HunterSkillDef.SkillToGroupSkill")


def helper_kind(method):
    stem = method_stem(method)
    if stem.startswith("getSkillValue"):
        return "value"
    if stem in ("getSkillLevel", "getSkillLevelCore", "getPrevSkillLevel"):
        return "level"
    if stem.startswith(("checkSkillActive", "IsSkillLevelMax")):
        return "active"
    return "other"


def clean_sources(prov):
    """Leaf data paths, decoded EXE constants and scenario inputs, deduplicated."""
    data, constants = [], []
    paths = sorted(
        p for p in prov if not CONSTANT.match(p) and not p.startswith(SCENARIO_PREFIXES)
    )
    for path in paths:
        if any(
            other != path and other.startswith((path + ".", path + "["))
            for other in paths
        ):
            continue
        if path.endswith(" 最大等级"):
            continue
        data.append(path)
    for item in sorted(prov):
        match = CONSTANT.match(item)
        if match:
            raw = bytes.fromhex(match.group(2))
            entry = dict(address=match.group(1), hex=raw.hex())
            if len(raw) == 4:
                entry["float"] = float(f"{struct.unpack('<f', raw)[0]:.7g}")
                entry["int"] = int.from_bytes(raw, "little", signed=True)
            constants.append(entry)
    return data, constants


def path_record(result):
    record = dict(status=result["status"])
    if result.get("conditions"):
        record["conditions"] = list(result["conditions"])
    if result["status"] == "ok":
        value = result["value"]
        if isinstance(value, Unk):
            record["expression"] = value.name
        elif isinstance(value, float):
            record["value"] = float(f"{value:.7g}")
        elif value is not None:
            record["value"] = value
        data, constants = clean_sources(result.get("prov", ()))
        if data:
            record["sources"] = data
        if constants:
            record["constants"] = constants
        if result.get("opaque"):
            record["opaque"] = sorted(set(result["opaque"]))
        writes = []
        for write in result.get("writes", ()):
            data, constants = clean_sources(write["prov"])
            entry = dict(target=write["target"], value=write["value"])
            if write["type"]:
                entry["type"] = write["type"]
            if data:
                entry["sources"] = data
            if constants:
                entry["constants"] = constants
            writes.append(entry)
        if writes:
            record["writes"] = writes
    elif result.get("detail"):
        record["detail"] = result["detail"]
    return record


def extract(
    exe, il2cpp, natives, *, skills=None, log=lambda text: print(text, flush=True)
):
    started = time.time()
    exe, il2cpp, natives = Path(exe), Path(il2cpp), Path(natives)
    with PE(exe) as pe, Il2cppMetadata(il2cpp) as metadata:
        # The digests live only in sdk/game_versions.json; the output names the version.
        game_version = versions.identify(digest(exe), metadata.sha256)
        index = NativeIndex(pe, metadata)
        world = SkillWorld(natives, metadata, pe, index)
        helpers = index.skill_helpers()
        references = index.references(helpers, world.runtime_names, world.fixed_names)
        log(
            f"技能参数方法 {len(helpers)} 个，调用点 {len(references)} 个，用时 {time.time() - started:.0f}s"
        )
        by_function = defaultdict(list)
        for row in references:
            by_function[row["function"]].append(row)
        functions, links = {}, []
        evaluator = Evaluator(world)
        scenarios = {}
        stats = defaultdict(int)
        for address, rows in sorted(by_function.items()):
            names = index.catalog.get(address, [])
            info, owner = None, None
            for type_name, method in names:
                candidate = (
                    (metadata.get(type_name) or {}).get("methods", {}).get(method)
                )
                if candidate:
                    info, owner = candidate, (type_name, method)
                    break
            key = f"{address:#x}"
            returns = (info or {}).get("returns", {}).get("type", "?")
            functions[key] = dict(
                type=owner[0] if owner else None,
                method=owner[1] if owner else None,
                address=key,
                returns=returns,
                params=[p.get("type") for p in (info or {}).get("params", [])],
            )
            referenced = defaultdict(list)
            for row in rows:
                if row["skill"] in (None, "NONE"):
                    continue
                helper = helpers[row["helper"]]
                referenced[row["skill"]].append(
                    dict(
                        helper=f"{helper['type']}.{helper['method']}",
                        kind=helper_kind(helper["method"]),
                        site=f"{row['site']:#x}",
                        intArgs=row["intArgs"],
                    )
                )
            evaluable = (
                info is not None
                and returns != "?"
                and not owner[1].startswith((".ctor", ".cctor"))
                and not owner[0].startswith(EVALUATE_SKIP_PREFIXES)
            )
            for via, uses in sorted(referenced.items()):
                equipped = world.remap.get(via, via)
                if skills and equipped not in skills:
                    continue
                link = dict(skill=equipped, via=via, function=key, uses=uses)
                levels = [
                    row["_SkillLv"]
                    for row in world.levels.get(equipped, ())
                    if row["_SkillLv"] > 0
                ]
                if evaluable and levels:
                    link["results"] = evaluate_link(
                        evaluator,
                        world,
                        scenarios,
                        equipped,
                        levels,
                        functions[key],
                        info,
                        stats,
                    )
                links.append(link)
            stats["functions"] += 1
            if stats["functions"] % 200 == 0:
                log(
                    f"  已处理函数 {stats['functions']}/{len(by_function)}，用时 {time.time() - started:.0f}s"
                )
        document = dict(
            schemaVersion=SCHEMA_VERSION,
            gameVersion=game_version,
            assumptions=[
                "每次只装备一个技能；组合/系列技能的等级是装备件数",
                "未导出的运行时状态保持未知，并在条件或表达式中按字段路径列出",
                "运行时对象引用均视为存在（不展开空引用分支）",
            ],
            skills=skill_table(
                world, {l["skill"] for l in links} | {l["via"] for l in links}
            ),
            remap=[dict(skill=s, group=g) for s, g in sorted(world.remap.items())],
            remapDifferences=remap_differences(world),
            functions=functions,
            links=links,
            notes=dict(general=notes.GENERAL, skills=notes.NOTES),
            stats=dict(stats, seconds=round(time.time() - started)),
        )
        validate(document)
        return document


def evaluate_link(evaluator, world, scenarios, skill, levels, function, info, stats):
    groups = {}
    combos = argument_domains(world.layouts, info.get("params", []))
    domains = {}
    for combo in combos:
        for i, (param, (label, _)) in enumerate(zip(info.get("params", []), combo)):
            key = f"{i + 1}:{param.get('type', '').rsplit('.', 1)[-1]}"
            if label is not None and label not in domains.setdefault(key, []):
                domains[key].append(label)
    limited = None  # first limit this function hit: later cases reuse it
    for level in levels:
        scenario = scenarios.get((skill, level))
        if scenario is None:
            scenario = scenarios[(skill, level)] = Scenario(world, skill, level)
        for combo in combos:
            if limited is not None:
                results = [limited]
                stats["skipped"] += 1
            else:
                try:
                    results = evaluator.run(scenario, function, info, combo)
                except PathEnd as end:
                    results = [dict(status=end.status, detail=end.detail)]
                    if end.status in LIMIT_STATUSES:
                        limited = dict(
                            status=end.status,
                            detail=end.detail + "（同一函数的其他情形未再单独求值）",
                        )
                stats["runs"] += 1
            paths = [path_record(r) for r in results]
            for p in paths:
                stats["path_" + p["status"]] += 1
            args = {
                f"{i + 1}:{p.get('type', '').rsplit('.', 1)[-1]}": label
                for i, (p, (label, _)) in enumerate(zip(info.get("params", []), combo))
                if label is not None
            }
            signature = json.dumps(paths, ensure_ascii=False, sort_keys=True)
            group = groups.setdefault(signature, dict(paths=paths, cases=[]))
            group["cases"].append(dict(level=level, args=args))
    return dict(argDomains=domains, groups=list(groups.values()))


def skill_table(world, referenced):
    table = {}
    names = (
        set(world.common)
        | set(world.levels)
        | set(world.remap)
        | set(world.remap.values())
        | referenced
    )
    for name in sorted(names):
        row = world.common.get(name)
        table[name] = dict(
            runtime=world.runtime.get(name),
            fixed=world.fixed.get(name),
            category=world.category(name),
            maxLevel=world.max_level(name),
            levels=[r["_SkillLv"] for r in world.levels.get(name, ())],
            inSkillCommonData=row is not None,
            openSkills=sorted(
                {
                    o
                    for r in world.levels.get(name, ())
                    for o in (re.sub(r"^\[-?\d+\]\s*", "", x) for x in r["_openSkill"])
                    if o not in ("NONE", name)
                }
            ),
            groupSkill=world.remap.get(name),
        )
    return table


def remap_differences(world):
    """Where SkillData._openSkill and the code's SkillToGroupSkill disagree."""
    data = defaultdict(set)
    for name, rows in world.levels.items():
        for row in rows:
            for item in row["_openSkill"]:
                opened = re.sub(r"^\[-?\d+\]\s*", "", item)
                if opened not in ("NONE", name):
                    data[opened].add(name)
    result = []
    for skill, group in sorted(world.remap.items()):
        if group not in data.get(skill, ()):
            result.append(
                dict(
                    kind="code_only",
                    skill=skill,
                    group=group,
                    dataOpens=sorted(o for o, gs in data.items() if group in gs),
                )
            )
    for skill, groups in sorted(data.items()):
        for group in sorted(groups):
            if world.remap.get(skill) != group:
                result.append(dict(kind="data_only", skill=skill, group=group))
    return result


def validate(document):
    if document["schemaVersion"] != SCHEMA_VERSION or not document["links"]:
        raise ValueError("技能链路结果为空或版本不符")
    keys = set(document["functions"])
    for link in document["links"]:
        if link["function"] not in keys or link["skill"] not in document["skills"]:
            raise ValueError(f"链路引用了不存在的函数或技能：{link}")
