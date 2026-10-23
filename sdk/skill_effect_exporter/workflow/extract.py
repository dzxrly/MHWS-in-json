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
    DIMENSION_EXCLUDED,
    DIMENSIONS,
    EVALUATE_SKIP_PREFIXES,
    HUNTER_SKILL,
    LIMIT_STATUSES,
    MAX_ACCESSOR_SKILLS,
    MAX_RECORDED_PATHS,
    SCHEMA_VERSION,
    SKILL_PARAM_TYPES,
)
from ..native.emulator import PathEnd
from ..runtime.evaluate import Evaluator, argument_domains
from ..runtime.scenario import Scenario, SkillWorld
from ..native.values import Unk, V
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


def merge_paths(paths, negations):
    """Merge paths with the same outcome whose conditions differ only in one
    condition and its negation: that branch does not change the result.
    Repeats until no pair is left, so conditions that never matter disappear."""
    items = []
    for path in paths:
        record = {k: v for k, v in path.items() if k != "conditions"}
        key = json.dumps(record, ensure_ascii=False, sort_keys=True)
        items.append((key, list(path.get("conditions", [])), record))
    while True:
        # One pass pairs every path with at most one partner, then merges them.
        seen, used, merges = {}, set(), []
        for i, (key, conditions, _) in enumerate(items):
            present = set(conditions)
            for condition in conditions:
                negation = negations.get(condition)
                if negation is None or negation in present:
                    continue
                rest = frozenset(present - {condition})
                partner = seen.get((key, rest, negation))
                if partner is not None and partner not in used and i not in used:
                    used.update((partner, i))
                    merges.append((partner, i, condition))
                    break
                seen.setdefault((key, rest, condition), i)
        if not merges:
            break
        for first, second, condition in merges:
            key, conditions, record = items[second]
            dropped = {condition, negations[condition]}
            items[first] = (key, [c for c in conditions if c not in dropped], record)
        removed = {second for _, second, _ in merges}
        items = [item for i, item in enumerate(items) if i not in removed]
    merged, done = [], set()
    for key, conditions, record in items:
        if (key, tuple(conditions)) in done:
            continue
        done.add((key, tuple(conditions)))
        merged.append(dict(record, conditions=conditions) if conditions else record)
    return merged


def limit_recorded(paths):
    """At most MAX_RECORDED_PATHS paths per case, those with fewest conditions
    first; the rest are counted in one "truncated" record."""
    if len(paths) <= MAX_RECORDED_PATHS:
        return paths
    ordered = sorted(paths, key=lambda p: len(p.get("conditions", [])))
    kept = ordered[:MAX_RECORDED_PATHS]
    rest = len(paths) - len(kept)
    return kept + [
        dict(status="truncated", detail=f"另有 {rest} 条条件更多的路径未列出")
    ]


def path_record(result):
    record = dict(status=result["status"])
    if result.get("focused"):
        record["focused"] = True
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
        evaluator.skill_calls = frozenset(helpers)

        scenarios = {}
        stats = defaultdict(int)
        def describe(address):
            """il2cpp method record of a function; also lists it in functions."""
            info, owner = None, None
            for type_name, method in index.catalog.get(address, []):
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
            evaluable = (
                info is not None
                and returns != "?"
                and not owner[1].startswith((".ctor", ".cctor"))
                and not owner[0].startswith(EVALUATE_SKIP_PREFIXES)
            )
            return key, info, evaluable

        def add_link(key, info, evaluable, via, uses, sites):
            equipped = world.remap.get(via, via)
            if skills and equipped not in skills:
                return
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
                    sites,
                )
            links.append(link)

        for address, rows in sorted(by_function.items()):
            key, info, evaluable = describe(address)
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
            # cHunterSkill methods over many skills are sums (calcAttackRate,
            # calcElemFireRate): they keep their limit status. Other functions,
            # such as a weapon's hit handling, apply skills to actions or ammo.
            focusable = (
                len(referenced) <= MAX_ACCESSOR_SKILLS
                or functions[key]["type"] != HUNTER_SKILL
            )
            for via, uses in sorted(referenced.items()):
                sites = {int(use["site"], 16) for use in uses} if focusable else None
                add_link(key, info, evaluable, via, uses, sites)
            stats["functions"] += 1
            if stats["functions"] % 200 == 0:
                log(
                    f"  已处理函数 {stats['functions']}/{len(by_function)}，用时 {time.time() - started:.0f}s"
                )

        # Second layer: a cHunterSkill accessor that takes no skill argument
        # (getSkillDodgeNoHitLv, getSkillGunnerAmmo_Normal_Rate) returns a level
        # or rate that its callers turn into the effect (invulnerable frames per
        # weapon action, which shells the rate applies to). Those callers are
        # evaluated in the same scenario, with the accessor run inline.
        accessors = defaultdict(set)
        for link in links:
            function = functions[link["function"]]
            if (
                function["type"] == HUNTER_SKILL
                and function["returns"] not in ("System.Void", "?")
                and not set(SKILL_PARAM_TYPES) & set(function["params"])
                and "results" in link
            ):
                accessors[int(link["function"], 16)].add(link["via"])
        accessors = {
            address: vias
            for address, vias in accessors.items()
            if len(vias) <= MAX_ACCESSOR_SKILLS
        }
        linked = {(link["function"], link["via"]) for link in links}
        second = defaultdict(list)
        for target, owners in index.calls_to(set(accessors)).items():
            helper = functions[f"{target:#x}"]
            for owner, sites in owners.items():
                if owner in by_function:  # uses skills itself: a first-layer link
                    continue
                for via in accessors[target]:
                    if (f"{owner:#x}", via) in linked:
                        continue
                    second[(owner, via)] += [
                        dict(
                            helper=f"{helper['type']}.{helper['method']}",
                            kind="accessor",
                            site=f"{site:#x}",
                        )
                        for site in sites
                    ]
        log(f"技能取值函数 {len(accessors)} 个，其调用方链路 {len(second)} 条")
        for (owner, via), uses in sorted(second.items()):
            key, info, evaluable = describe(owner)
            add_link(
                key, info, evaluable, via, uses, {int(u["site"], 16) for u in uses}
            )
            stats["accessor_callers"] += 1

        document = dict(
            schemaVersion=SCHEMA_VERSION,
            gameVersion=game_version,
            assumptions=[
                "每次只装备一个技能；组合/系列技能的等级是装备件数",
                "未导出的运行时状态保持未知，并在条件或表达式中按字段路径列出",
                "运行时对象引用均视为存在（不展开空引用分支）",
                "读取装备武器类型或弹种的函数按每种取值分别求值，参数中的“武器”“弹种”“弹药参数类型”即情境中的装备武器与所用弹药",
                "分支过多的函数只追踪经过技能读取点的路径；在一个等级下某一武器或弹药没有路径经过读取点时，其他等级视为同样不经过",
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


def evaluate_link(
    evaluator, world, scenarios, skill, levels, function, info, stats, sites
):
    groups = {}
    combos = argument_domains(world.layouts, info.get("params", []))
    domains = {}
    for combo in combos:
        for i, (param, (label, _)) in enumerate(zip(info.get("params", []), combo)):
            key = f"{i + 1}:{param.get('type', '').rsplit('.', 1)[-1]}"
            if label is not None and label not in domains.setdefault(key, []):
                domains[key].append(label)
    values = {
        dimension["name"]: sorted(
            (value & 0xFFFFFFFF, label)
            for label, value in world.layouts.enum_values(dimension["enum"]).items()
            if label not in DIMENSION_EXCLUDED
        )
        for dimension in DIMENSIONS
    }
    order = [dimension["name"] for dimension in DIMENSIONS]
    only = {dimension["name"]: dimension.get("only", {}) for dimension in DIMENSIONS}
    settled = {}  # arguments with dimension values -> results reused at other levels
    limited = None  # first limit this function hit: later cases reuse it
    focus_only = False  # the whole function exceeded a limit: run focused at once

    def attempt(scenario, combo, fixed):
        """One evaluation with the dimensions in fixed set: name -> (value, label)."""
        heap = scenario.heap
        heap.inputs = {
            name: V(value, frozenset({f"参数 {name}={label}"}))
            for name, (value, label) in fixed.items()
        }
        heap.inputs_read = set()
        nonlocal focus_only
        results, end = None, None
        if not focus_only:
            try:
                results = evaluator.run(scenario, function, info, combo)
            except PathEnd as error:
                results, end = [dict(status=error.status, detail=error.detail)], error
            stats["runs"] += 1
        if focus_only or (end is not None and end.status in LIMIT_STATUSES and sites):
            # Too large as a whole: keep only the paths through the skill's use.
            try:
                focused = evaluator.run(scenario, function, info, combo, sites)
                results, end = [dict(r, focused=True) for r in focused], None
                focus_only = True
            except PathEnd as error:
                # The skill is used on this case, its value still not complete.
                detail = f"只追踪可能经过技能读取点的路径仍超限：{error.detail}"
                results = [dict(status=error.status, detail=detail, focused=True)]
                end = end or error
            stats["focused_runs"] += 1
        unset = [
            n
            for n in order
            if n in heap.inputs_read
            and n not in fixed
            and all(
                fixed[other][1] in allowed
                for other, allowed in only[n].items()
                if other in fixed
            )
        ]
        return results, end, unset

    def limit_of(end):
        if end is None or end.status not in LIMIT_STATUSES:
            return None
        return dict(
            status=end.status,
            detail=end.detail + "（同一函数的其他情形未再单独求值）",
        )

    def expand(scenario, combo, args, fixed):
        """(args, results) of one case, split by every dimension the code reads."""
        nonlocal limited
        # With focused evaluation, dimension values differ in which code they
        # reach: what one value gave (no path through the skill, or a limit) is
        # reused only for the same arguments and value at the other levels.
        under = tuple(sorted(args.items()))
        if sites and fixed and under in settled:
            stats["skipped"] += 1
            return [(args, settled[under])]
        if limited is not None and not (sites and fixed):
            stats["skipped"] += 1
            return [(args, [limited])]
        results, end, unset = attempt(scenario, combo, fixed)
        if not unset:
            if sites and fixed:
                if not results:  # no path reaches the skill under these values
                    settled[under] = []
                elif limit_of(end) is not None and len(results) == 1:
                    first = results[0]
                    settled[under] = [
                        dict(
                            first,
                            detail=first.get("detail", "")
                            + "（同一函数的其他情形未再单独求值）",
                        )
                    ]
            else:
                limited = limit_of(end)
            return [(args, results)]
        # Fixing a dimension usually removes branches, so a limit hit while it
        # was unknown does not stop the runs per value.
        name = unset[0]
        domains[name] = [label for _, label in values[name]]
        cases = []
        for value, label in values[name]:
            cases += expand(
                scenario, combo, {**args, name: label}, {**fixed, name: (value, label)}
            )
        return cases

    for level in levels:
        scenario = scenarios.get((skill, level))
        if scenario is None:
            scenario = scenarios[(skill, level)] = Scenario(world, skill, level)
        for combo in combos:
            args = {
                f"{i + 1}:{p.get('type', '').rsplit('.', 1)[-1]}": label
                for i, (p, (label, _)) in enumerate(zip(info.get("params", []), combo))
                if label is not None
            }
            cases = expand(scenario, combo, args, {})
            for case_args, results in cases:
                paths = limit_recorded(
                    merge_paths([path_record(r) for r in results], evaluator.negations)
                )
                for p in paths:
                    stats["path_" + p["status"]] += 1
                signature = json.dumps(paths, ensure_ascii=False, sort_keys=True)
                group = groups.setdefault(signature, dict(paths=paths, cases=[]))
                group["cases"].append(dict(level=level, args=case_args))
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
