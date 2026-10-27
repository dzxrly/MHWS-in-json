"""Assemble the skill link document: references, evaluations, sources."""

from __future__ import annotations

import json
import re
import struct
import time
from collections import defaultdict
from pathlib import Path

from sdk.enemy_logic_exporter.shared.native.metadata import Il2cppMetadata
from sdk.progress import track
from sdk.enemy_logic_exporter.shared.native.pe import PE


from ...config import (
    DIMENSION_EXCLUDED,
    DIMENSIONS,
    EVALUATE_SKIP_PREFIXES,
    HUNTER_SKILL,
    LIMIT_STATUSES,
    MAX_ACCESSOR_SKILLS,
    MAX_READER_DEPTH,
    MAX_RECORDED_PATHS,
    MAX_USAGE_COMBINATIONS,
    MAX_USAGE_PATHS,
    PARAM_GETTER,
    PLAYER_GLOBAL_TYPE,
    SCHEMA_VERSION,
    SKILL_PARAM_SUFFIX,
    SKILL_PARAM_TYPES,
)

# How an evaluated path used a data item (see path_sources).
USE_KINDS = ("value", "write", "compare")
from ..native.emulator import PathEnd
from ..runtime.evaluate import Evaluator, argument_domains
from ..runtime.scenario import Scenario, SkillWorld
from ..native.values import Unk, V
from ..native.scan import NativeIndex, method_stem
from .annotate import apply_annotations

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
    Repeats until no pair is left, so conditions that never matter disappear.
    The data the conditions compared ("compared") follows the conditions: the
    merged path keeps what either one compared."""
    items = []
    for path in paths:
        record = {k: v for k, v in path.items() if k not in ("conditions", "compared")}
        key = json.dumps(record, ensure_ascii=False, sort_keys=True)
        record["compared"] = set(path.get("compared", ()))
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
            record = dict(
                record, compared=record["compared"] | items[first][2]["compared"]
            )
            items[first] = (key, [c for c in conditions if c not in dropped], record)
        removed = {second for _, second, _ in merges}
        items = [item for i, item in enumerate(items) if i not in removed]
    merged, done = [], {}
    for key, conditions, record in items:
        if (key, tuple(conditions)) in done:
            done[(key, tuple(conditions))]["compared"] |= record["compared"]
            continue
        record = dict(record, conditions=conditions) if conditions else dict(record)
        done[(key, tuple(conditions))] = record
        merged.append(record)
    for record in merged:
        compared = sorted(record.pop("compared"))
        if compared:
            record["compared"] = compared
    return merged


def limit_recorded(paths, limit=MAX_RECORDED_PATHS):
    """At most limit paths per case, those with fewest conditions first; the
    rest are counted in one "truncated" record."""
    if len(paths) <= limit:
        return paths
    ordered = sorted(paths, key=lambda p: len(p.get("conditions", [])))
    kept = ordered[:limit]
    rest = len(paths) - len(kept)
    return kept + [
        dict(status="truncated", detail=f"另有 {rest} 条条件更多的路径未列出")
    ]


def path_record(result):
    record = dict(status=result["status"])
    if result.get("focused"):
        record["focused"] = True
    if result.get("narrow"):
        record["narrow"] = True
    if result.get("conditions"):
        record["conditions"] = list(result["conditions"])
        compared, _ = clean_sources(result.get("condition_prov", ()))
        if compared:
            record["compared"] = compared
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
    exe,
    il2cpp,
    natives,
    *,
    skills=None,
    all_links=False,
    log=lambda text: print(text, flush=True),
):
    """The link document. Each skill's module (skills/<id>.py) runs its own
    steps on a shared SkillContext: first every skill's extract (functions
    using it, callers of its accessors), then every skill's
    extract_parameters (parameter fields no path valued). all_links also
    evaluates the functions the modules skip (SKIPPED_FUNCTIONS)."""
    from ...skills import entry
    from .context import SkillContext

    started = time.time()
    with PE(Path(exe)) as pe, Il2cppMetadata(Path(il2cpp)) as metadata:
        context = SkillContext(pe, metadata, Path(natives), skills, log, all_links)
        order = context.skills()
        modules = {skill_id: entry(skill_id) for skill_id in order}
        context.preflight_entries(modules)
        for skill_id in track(order, "求值各技能的链路"):
            modules[skill_id].extract(context)
        for skill_id in track(order, "聚焦求值参数字段读取点"):
            modules[skill_id].extract_parameters(context)
        document = context.document(started)
    missing, extra = apply_annotations(document)
    if missing and not skills:
        log(f"以下技能还没有技能模块（new-skill --skill <ID>）：{'、'.join(missing)}")
    if extra and not skills:
        log(f"以下技能模块的技能已不在技能表中：{'、'.join(extra)}")
    validate(document)
    return document


def parameter_readers(index, reads, skilled, param_types):
    """Functions that read skill parameters (fields of param_types) but use no
    known skill (not in skilled), with the functions calling them: reader ->
    {caller -> [call site]}. A focused run of a skill-using caller at those
    sites runs the reader inline, so its reads belong to the caller's skill.

    A caller that uses no skill either counts as a reader (cHunterSkill.
    beginKnight calls cHunterSkillParamInfo.beginKnight): callers within
    MAX_READER_DEPTH calls are listed. Display and network functions are left out.
    """

    def plain(address):
        names = index.catalog.get(address, [])
        return address not in skilled and not any(
            type_name.startswith(EVALUATE_SKIP_PREFIXES) for type_name, _ in names
        )

    readers = {
        owner
        for (type_name, _), owners in reads.items()
        if type_name in param_types
        for owner in owners
        if plain(owner)
    }
    callers = defaultdict(dict)  # reader -> {caller -> sites}
    origins = {reader: {reader} for reader in readers}  # function -> readers below it
    frontier = set(readers)
    for _ in range(MAX_READER_DEPTH):
        found = index.calls_to(frontier)
        frontier = set()
        for target, owners in found.items():
            for owner, sites in owners.items():
                for reader in origins[target]:
                    callers[reader].setdefault(owner, []).extend(sites)
                if plain(owner) and owner not in origins:
                    origins[owner] = set(origins[target])
                    frontier.add(owner)
                elif plain(owner):
                    origins[owner] |= origins[target]
    return {reader: dict(found) for reader, found in callers.items()}


def traced(function):
    """Whether a link's function gets usage tracing: everything except the
    cHunterSkill getters themselves (getSkill*/isSkill*), whose only use of
    the skill is the table lookup; their callers are traced instead."""
    return not (
        function["type"] == HUNTER_SKILL
        and re.match(r"(get|is)skill", function["method"] or "", re.I)
    )


def usage_label(use, via):
    """Name the skill read at a call site is replaced by in usage tracing."""
    helper = method_stem(use["helper"].rsplit(".", 1)[-1])
    if use["kind"] == "accessor":
        return f"取值〈{helper}〉"
    if use["kind"] == "value":
        slot = next((i for i in use.get("intArgs", []) if i is not None), None)
        return f"技能数值〈{via}{'' if slot is None else f' 槽{slot}'}〉"
    if use["kind"] == "level":
        return f"技能等级〈{via}〉"
    if use["kind"] == "active":
        return f"技能发动〈{via}〉"
    return f"技能〈{via} {helper}〉"


def evaluate_usage(evaluator, world, scenario, function, info, via, uses):
    """How the function uses the skill's values: each skill read (helper call
    or accessor call) stays an unknown named by usage_label, so conditions,
    results and writes show what it is compared with, combined with and
    stored into. Paths that never touch a label are dropped. Dimensions stay
    unknown and appear in the conditions."""
    usage = {int(use["site"], 16): usage_label(use, via) for use in uses}
    labels = sorted(set(usage.values()))
    groups, domains = {}, {}
    combos = argument_domains(world.layouts, info.get("params", []))
    for combo in combos[:MAX_USAGE_COMBINATIONS]:
        args = {}
        for i, (param, (label, _)) in enumerate(zip(info.get("params", []), combo)):
            if label is not None:
                key = f"{i + 1}:{param.get('type', '').rsplit('.', 1)[-1]}"
                args[key] = label
                if label not in domains.setdefault(key, []):
                    domains[key].append(label)
        scenario.heap.inputs, scenario.heap.inputs_read = {}, set()
        for narrow in (False, True):
            try:
                results = evaluator.run(
                    scenario, function, info, combo, set(usage), usage, narrow
                )
                if narrow:
                    results = [dict(r, narrow=True) for r in results]
                break
            except PathEnd as error:
                results = [
                    dict(status=error.status, detail=error.detail, narrow=narrow)
                ]
                if error.status not in LIMIT_STATUSES:
                    break
        paths = []
        for result in results:
            record = path_record(result)
            record.pop("opaque", None)
            text = json.dumps(record, ensure_ascii=False)
            if record["status"] != "ok" or any(label in text for label in labels):
                paths.append(record)
        paths = limit_recorded(merge_paths(paths, evaluator.negations), MAX_USAGE_PATHS)
        signature = json.dumps(paths, ensure_ascii=False, sort_keys=True)
        group = groups.setdefault(signature, dict(paths=paths, cases=[]))
        group["cases"].append(dict(args=args))
    record = dict(
        level=scenario.level,
        labels=labels,
        argDomains=domains,
        groups=list(groups.values()),
    )
    if len(combos) > MAX_USAGE_COMBINATIONS:
        record["omittedCases"] = len(combos) - MAX_USAGE_COMBINATIONS
    return record


def short_type(type_name):
    return type_name.rsplit(".", 1)[-1]


def path_sources(link):
    """(use, source) of the data a link's evaluated paths used: "value" for a
    returned value, "write" for a value written to runtime state, "compare"
    for data a condition compared (a threshold)."""
    for group in (link.get("results") or {}).get("groups", []):
        for path in group["paths"]:
            if path["status"] != "ok":
                continue
            yield from (("value", s) for s in path.get("sources", ()))
            for write in path.get("writes", ()):
                yield from (("write", s) for s in write.get("sources", ()))
            yield from (("compare", s) for s in path.get("compared", ()))


def field_label(source):
    """ "PlayerSkillParam._Field" of a parameter-file source path."""
    return ".".join(re.split(r"[.\[]", source)[:2])


def valued_fields(links):
    """Parameter fields some evaluated path used (returned, wrote or compared)."""
    return {
        field_label(source)
        for link in links
        for _, source in path_sources(link)
        if not source.startswith("SkillData[")
    }


def skill_param_types(world):
    """Parameter files of PlayerGlobalParam that hold skill parameters."""
    return sorted(
        {
            ftype
            for _, ftype in world.layouts.fields(PLAYER_GLOBAL_TYPE).values()
            if short_type(ftype).endswith(SKILL_PARAM_SUFFIX)
        }
    )


def coverage(world, links, reads, describe):
    """Skill parameter fields and SkillData slots against what the links used.

    params: per skill parameter file, every field with the functions that read
    it (static scan) and, per use (USE_KINDS: returned, written, compared), the
    skills whose evaluated paths used it. skillData: per skill, the SkillData
    slots that are non-zero at some level and, per use, the slots used.
    """
    by_field = defaultdict(lambda: defaultdict(set))
    slots = defaultdict(lambda: defaultdict(set))
    for link in links:
        for kind, source in path_sources(link):
            match = re.match(r"SkillData\[(\S+) Lv\d+\]\._value\[(\d+)\]", source)
            if match:
                slots[match.group(1)][kind].add(int(match.group(2)))
            else:
                by_field[field_label(source)][kind].add(link["skill"])
    params = {}
    for type_name in skill_param_types(world):
        fields = {}
        for _, (field, _) in world.layouts.fields(type_name).items():
            label = f"{short_type(type_name)}.{field}"
            used = by_field[label]
            fields[field] = dict(
                reads=sorted(
                    describe(owner)[0] for owner in reads.get((type_name, field), {})
                ),
                **{kind: sorted(used[kind]) for kind in USE_KINDS if used[kind]},
            )
        params[short_type(type_name)] = fields
    skill_data = {}
    for skill, rows in sorted(world.levels.items()):
        nonzero = sorted(
            {i for row in rows for i, value in enumerate(row["_value"]) if value}
        )
        if nonzero:
            used = slots[skill]
            skill_data[skill] = dict(
                nonzero=nonzero,
                **{kind: sorted(used[kind]) for kind in USE_KINDS if used[kind]},
            )
    return dict(params=params, skillData=skill_data)


def evaluate_link(
    evaluator,
    world,
    scenarios,
    skill,
    levels,
    function,
    info,
    stats,
    sites,
    focus_first=False,
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
    # The whole function exceeded a limit, or only the sites matter: run
    # focused; when that exceeds a limit too, narrowed (see Emulator.narrow).
    # Later cases start at the mode that last succeeded.
    mode = "focused" if focus_first else None

    def attempt(scenario, combo, fixed):
        """One evaluation with the dimensions in fixed set: name -> (value, label)."""
        heap = scenario.heap
        heap.inputs = {
            name: V(value, frozenset({f"参数 {name}={label}"}))
            for name, (value, label) in fixed.items()
        }
        heap.inputs_read = set()
        nonlocal mode
        results, end = None, None
        if mode is None:
            try:
                results = evaluator.run(scenario, function, info, combo)
            except PathEnd as error:
                results, end = [dict(status=error.status, detail=error.detail)], error
            stats["runs"] += 1
        if mode or (end is not None and end.status in LIMIT_STATUSES and sites):
            # Too large as a whole: keep only the paths through the skill's use.
            results, end = focused_run(
                evaluator, scenario, function, info, combo, sites, mode, stats
            )
            mode = "narrow" if any(r.get("narrow") for r in results) else "focused"
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
        # was unknown does not stop the runs per value, and a run narrowed
        # then is tried focused again per value (narrowing keeps one branch
        # combination only, e.g. one of 连击's two data tables).
        nonlocal mode
        if mode == "narrow":
            mode = "focused"
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


def focused_run(evaluator, scenario, function, info, combo, sites, mode, stats):
    """(results, limit end or None) of a focused evaluation; one exceeding a
    limit is narrowed: before the first site, of two branches that both lead
    there only the nearer one is taken. Mode "narrow" starts narrowed."""
    end = None
    for narrow in (False, True) if mode != "narrow" else (True,):
        flags = dict(focused=True, narrow=True) if narrow else dict(focused=True)
        stats["narrow_runs" if narrow else "focused_runs"] += 1
        try:
            results = evaluator.run(
                scenario, function, info, combo, sites, narrow=narrow
            )
            return [dict(r, **flags) for r in results], None
        except PathEnd as error:
            # The skill is used on this case, its value still not complete.
            prefix = (
                "只沿最近分支追踪到技能读取点"
                if narrow
                else "只追踪可能经过技能读取点的路径"
            )
            results = [
                dict(
                    status=error.status,
                    detail=f"{prefix}仍超限：{error.detail}",
                    **flags,
                )
            ]
            end = error
            if error.status not in LIMIT_STATUSES:
                break
    return results, end


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
