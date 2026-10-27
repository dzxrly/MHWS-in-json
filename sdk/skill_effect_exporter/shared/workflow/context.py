"""Shared state of one extraction, and the per-skill steps skill modules call.

The native scan, the evaluator and the links found so far belong to the
context. The work is planned per skill up front (which functions use the
skill, which callers of its accessors to evaluate); a skill module's
``extract`` evaluates its planned links with ``extract_skill``, and once every
skill has done so, its ``extract_parameters`` focuses on the parameter fields
that no path valued (``extract_parameters`` needs all first-step links).
"""

from __future__ import annotations

import time
from collections import defaultdict

from capstone import x86_const as X

from ...config import (
    DISPLAY_PARAM_FIELDS,
    EVALUATE_SKIP_PREFIXES,
    HUNTER_SKILL,
    MAX_ACCESSOR_SKILLS,
    PARAM_GETTER,
    PLAYER_GLOBAL_TYPE,
    SCHEMA_VERSION,
    SKILL_PARAM_TYPES,
)
from ..native.scan import NativeIndex, method_stem
from ..runtime.evaluate import Evaluator
from ..runtime.scenario import Scenario, SkillWorld
from .extract import (
    coverage,
    evaluate_link,
    evaluate_usage,
    helper_kind,
    parameter_readers,
    remap_differences,
    short_type,
    skill_param_types,
    skill_table,
    traced,
    valued_fields,
)

ASSUMPTIONS = [
    "每次只装备一个技能；组合/系列技能的等级是装备件数",
    "未导出的运行时状态保持未知，并在条件或表达式中按字段路径列出",
    "运行时对象引用均视为存在（不展开空引用分支）",
    "读取装备武器类型或弹种的函数按每种取值分别求值，参数中的“武器”“弹种”“弹药参数类型”即情境中的装备武器与所用弹药",
    "分支过多的函数只追踪经过技能读取点的路径；在一个等级下某一武器或弹药没有路径经过读取点时，其他等级视为同样不经过",
]


class SkillContext:
    def __init__(self, pe, metadata, natives, skills, log, all_links=False):
        started = time.time()
        self.metadata, self.only, self.log = metadata, skills or set(), log
        # Evaluate the functions skill modules skip as well (checks after a
        # game update whether a skipped function now gives the skill a value).
        self.all_links = all_links
        index = self.index = NativeIndex(pe, metadata)
        world = self.world = SkillWorld(natives, metadata, pe, index)
        helpers = index.skill_helpers()
        references = index.references(helpers, world.runtime_names, world.fixed_names)
        log(
            f"技能参数方法 {len(helpers)} 个，调用点 {len(references)} 个，用时 {time.time() - started:.0f}s"
        )
        self.by_function = defaultdict(list)
        for row in references:
            self.by_function[row["function"]].append(row)
        self.functions, self.links = {}, []
        _, getter, _ = index.method(HUNTER_SKILL, PARAM_GETTER)
        self.reads = index.param_reads(
            world.chain_root,
            world.chain_offsets,
            getter,
            world.layouts,
            PLAYER_GLOBAL_TYPE,
        )
        self.param_types = set(skill_param_types(world))
        skilled = {
            address
            for address, rows in self.by_function.items()
            if any(row["skill"] not in (None, "NONE") for row in rows)
        }
        self.reader_callers = parameter_readers(
            index, self.reads, skilled, self.param_types
        )
        self.evaluator = Evaluator(world)
        self.evaluator.skill_calls = frozenset(helpers)
        self.evaluator.param_roots = frozenset(short_type(t) for t in self.param_types)
        self.scenarios = {}
        self.stats = defaultdict(int)
        self.plan = defaultdict(list)  # skill -> [(layer, function, via, uses, sites)]
        self.vias = defaultdict(set)  # function -> skills it is evaluated for
        self.plan_functions(helpers)
        self.plan_accessor_callers()
        self.targets = None  # parameter read sites, once every skill's links exist
        self.unused_skips = {}  # skill -> skipped functions no link matched yet

    # ------------------------------------------------------------ planning
    def equipped(self, via):
        """The skill a link belongs to: an open skill maps to its group skill."""
        return self.world.remap.get(via, via)

    def selected(self, skill):
        return not self.only or skill in self.only

    def levels(self, skill):
        return [
            r["_SkillLv"] for r in self.world.levels.get(skill, ()) if r["_SkillLv"] > 0
        ]

    def plan_functions(self, helpers):
        """First layer: every function calling a skill method with a skill ID."""
        for address, rows in sorted(self.by_function.items()):
            key, info, evaluable = self.describe(address)
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
            # such as a weapon's hit handling or the per-frame cHunterSkill.update
            # (no result), apply skills to actions, ammo or skill state.
            function = self.functions[key]
            focusable = (
                len(referenced) <= MAX_ACCESSOR_SKILLS
                or function["type"] != HUNTER_SKILL
                or function["returns"] == "System.Void"
            )
            if referenced:  # rows with an unresolved skill only: not evaluated
                self.vias[address].update(referenced)
            for via, uses in sorted(referenced.items()):
                sites = {int(use["site"], 16) for use in uses} if focusable else None
                self.plan[self.equipped(via)].append(
                    ("function", address, via, uses, sites)
                )
            self.stats["functions"] += 1

    def plan_accessor_callers(self):
        """Second layer: a cHunterSkill accessor that takes no skill argument
        (getSkillDodgeNoHitLv, getSkillGunnerAmmo_Normal_Rate) returns a level
        or rate that its callers turn into the effect (invulnerable frames per
        weapon action, which shells the rate applies to). Those callers are
        evaluated in the same scenario, with the accessor run inline."""
        accessors, linked = defaultdict(set), set()
        for skill, items in self.plan.items():
            if not self.selected(skill):
                continue
            for _, address, via, _, _ in items:
                linked.add((address, via))
                key, info, evaluable = self.describe(address)
                function = self.functions[key]
                if (
                    function["type"] == HUNTER_SKILL
                    and function["returns"] not in ("System.Void", "?")
                    and not set(SKILL_PARAM_TYPES) & set(function["params"])
                    and evaluable
                    and self.levels(skill)
                ):
                    accessors[address].add(via)
        accessors = {
            a: v for a, v in accessors.items() if len(v) <= MAX_ACCESSOR_SKILLS
        }
        second = defaultdict(list)
        for target, owners in self.index.calls_to(set(accessors)).items():
            helper = self.functions[f"{target:#x}"]
            for owner, sites in owners.items():
                if owner in self.by_function:  # uses skills itself: a first-layer link
                    continue
                for via in accessors[target]:
                    if (owner, via) in linked:
                        continue
                    second[(owner, via)] += [
                        dict(
                            helper=f"{helper['type']}.{helper['method']}",
                            kind="accessor",
                            site=f"{site:#x}",
                        )
                        for site in sites
                    ]
        self.log(f"技能取值函数 {len(accessors)} 个，其调用方链路 {len(second)} 条")
        for (owner, via), uses in sorted(second.items()):
            sites = {int(u["site"], 16) for u in uses}
            self.plan[self.equipped(via)].append(("accessor", owner, via, uses, sites))
            self.vias[owner].add(via)

    def skills(self):
        """Skills with planned links, in ID order (the selected ones only)."""
        return [s for s in sorted(self.plan) if self.selected(s)]

    def preflight_entries(self, modules):
        """Reject selected entry jumps whose target the supplied dump omits.

        This checks planned links and the selected modules' declared methods,
        before evaluating any of them. Other unknown paths remain ordinary
        partial results; an entry jump outside the readable dump cannot supply
        the selected function's implementation.
        """
        addresses = {
            address
            for skill, items in self.plan.items()
            if self.selected(skill)
            for _, address, _, _, _ in items
        }
        for skill, module in modules.items():
            if self.selected(skill):
                for type_name, method, *_ in getattr(module, "DECLARED_METHODS", ()):
                    _, address, _ = self.index.method(type_name, method)
                    addresses.add(address)
        missing = []
        pe = self.index.pe
        for address in sorted(addresses):
            instructions = self.index.disasm(address)
            if not instructions:
                continue
            first = instructions[0]
            if first.mnemonic != "jmp" or first.operands[0].type != X.X86_OP_IMM:
                continue
            target = first.operands[0].imm
            if pe.contains(target) and pe.read(target, 1):
                continue
            identity = " / ".join(
                f"{type_name}.{method}"
                for type_name, method in self.index.catalog.get(address, ())
            )
            missing.append(
                f"{identity or '未命名函数'}：入口 {address:#x} → 目标 {target:#x}"
            )
        if missing:
            raise ValueError(
                "输入 dump 缺失以下函数入口直接 JMP 的目标，无法提取所选函数；"
                "请提供包含目标代码的 dump。未写出技能链路：\n" + "\n".join(missing)
            )

    # ------------------------------------------------------------ evaluation
    def describe(self, address):
        """il2cpp method record of a function; also lists it in functions."""
        info, owner = None, None
        for type_name, method in self.index.catalog.get(address, []):
            candidate = (
                (self.metadata.get(type_name) or {}).get("methods", {}).get(method)
            )
            if candidate:
                info, owner = candidate, (type_name, method)
                break
        key = f"{address:#x}"
        returns = (info or {}).get("returns", {}).get("type", "?")
        self.functions[key] = dict(
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

    def skip_reason(self, address, skipped, unused):
        """The reason a skill module gives for not evaluating the function at
        address, or None; a matched entry is removed from unused."""
        for type_name, method in self.index.catalog.get(address, []):
            entry = (type_name, method_stem(method))
            if entry in skipped:
                unused.discard(entry)
                return None if self.all_links else skipped[entry]
        return None

    def report_unused(self, skill_id, unused):
        for type_name, method in sorted(unused):
            self.log(
                f"{skill_id} 的 SKIPPED_FUNCTIONS 中 {type_name}.{method} 没有对应的链路，可以删除"
            )

    def add_link(self, address, via, uses, sites, focus_first=False, skipped=None):
        key, info, evaluable = self.describe(address)
        equipped = self.equipped(via)
        link = dict(skill=equipped, via=via, function=key, uses=uses)
        levels = self.levels(equipped)
        if skipped:
            # Kept as a link of the skill, not evaluated (the module's reason).
            link["skipped"] = skipped
            self.stats["module_skipped"] += 1
        elif evaluable and levels:
            link["results"] = evaluate_link(
                self.evaluator,
                self.world,
                self.scenarios,
                equipped,
                levels,
                self.functions[key],
                info,
                self.stats,
                sites,
                focus_first,
            )
            # Usage tracing replaces the skill reads at the uses' call sites;
            # param and module links name read sites, not skill calls.
            if traced(self.functions[key]) and uses[0]["kind"] not in (
                "param",
                "module",
            ):
                scenario = self.scenarios.get((equipped, levels[-1]))
                if scenario is None:
                    scenario = self.scenarios[(equipped, levels[-1])] = Scenario(
                        self.world, equipped, levels[-1]
                    )
                link["usage"] = evaluate_usage(
                    self.evaluator,
                    self.world,
                    scenario,
                    self.functions[key],
                    info,
                    via,
                    uses,
                )
                self.stats["usage_runs"] += 1
        self.links.append(link)
        return link

    def extract_skill(self, skill_id, skipped=None):
        """The links of the functions using the skill and of the callers of its
        accessors. skipped: [(type, method, reason)] from the skill's module,
        functions recorded as links but not evaluated."""
        skipped = {(t, m): reason for t, m, reason in skipped or ()}
        unused = set(skipped)
        links = []
        for layer, address, via, uses, sites in self.plan.get(skill_id, ()):
            reason = self.skip_reason(address, skipped, unused)
            links.append(self.add_link(address, via, uses, sites, skipped=reason))
            if layer == "accessor":
                self.stats["accessor_callers"] += 1
        self.unused_skips[skill_id] = unused
        return links

    def extract_method(self, skill_id, type_name, method, reason, fields=()):
        """A link the skill's module declares: a function that belongs to the
        skill but that the scan cannot tie to it (called under a skill check
        it cannot resolve, or through an unnamed call), or one whose value the
        shared steps reach only by chance. It is evaluated in the skill's
        scenario; past the limits, focused on its reads of skill parameters,
        or only of the given fields (in a function many skills share). reason
        (the reviewed evidence) is kept in the link."""
        _, address, _ = self.index.method(type_name, method)
        # Read sites in the function, and its calls to readers of the fields
        # (as for parameter_targets).
        sites = set()
        for (owner_type, field), owners in self.reads.items():
            if owner_type not in self.param_types or (fields and field not in fields):
                continue
            for owner, found in owners.items():
                if owner == address:
                    sites.update(found)
                else:
                    sites.update(self.reader_callers.get(owner, {}).get(address, ()))
        sites = sorted(sites)
        if fields and not sites:
            raise ValueError(
                f"{type_name}.{method} 中没有读取 {'、'.join(fields)} 的位置"
            )
        uses = [dict(kind="module", reason=reason, site=f"{s:#x}") for s in sites]
        link = self.add_link(
            address, skill_id, uses or [dict(kind="module", reason=reason)], set(sites)
        )
        self.stats["module_links"] += 1
        return [link]

    def parameter_targets(self):
        """function -> [(field label, site)]: parameter fields that no evaluated
        path valued, read there or in a reader it calls. Static read sites
        become focus targets in the functions that use the skill (a level-3
        bonus inside a large hit handler, a threshold next to a skill check)."""
        if self.targets is None:
            valued = valued_fields(self.links)
            self.targets = defaultdict(list)
            for (type_name, field), owners in self.reads.items():
                label = f"{short_type(type_name)}.{field}"
                if (
                    label in valued
                    or type_name not in self.param_types
                    or field in DISPLAY_PARAM_FIELDS
                ):
                    continue
                for owner, sites in owners.items():
                    if owner in self.vias:
                        self.targets[owner] += [(label, site) for site in sites]
                        continue
                    # Read where no skill is used: focus on the calls to the
                    # reader in the functions that use skills.
                    for caller, calls in self.reader_callers.get(owner, {}).items():
                        if caller in self.vias:
                            self.targets[caller] += [(label, site) for site in calls]
            self.log(f"未求得数值的参数字段读取点分布在 {len(self.targets)} 个函数中")
        return self.targets

    def extract_parameters(self, skill_id, skipped=None):
        """Links focused on the read sites of unvalued parameter fields in the
        functions evaluated for the skill (call after every skill's extract).
        skipped: as for extract_skill."""
        skipped = {(t, m): reason for t, m, reason in skipped or ()}
        unused = self.unused_skips.get(skill_id, set(skipped))
        links = []
        for owner, items in sorted(self.parameter_targets().items()):
            for via in sorted(self.vias[owner]):
                if self.equipped(via) != skill_id:
                    continue
                uses = [
                    dict(kind="param", field=label, site=f"{site:#x}")
                    for label, site in sorted(
                        set(items), key=lambda item: (item[1], item[0])
                    )
                ]
                reason = self.skip_reason(owner, skipped, unused)
                links.append(
                    self.add_link(
                        owner,
                        via,
                        uses,
                        {site for _, site in items},
                        focus_first=True,
                        skipped=reason,
                    )
                )
                self.stats["param_links"] += 1
        self.report_unused(skill_id, unused)
        return links

    # ------------------------------------------------------------ document
    def document(self, started):
        links = self.links
        return dict(
            schemaVersion=SCHEMA_VERSION,
            assumptions=ASSUMPTIONS,
            skills=skill_table(
                self.world, {l["skill"] for l in links} | {l["via"] for l in links}
            ),
            remap=[dict(skill=s, group=g) for s, g in sorted(self.world.remap.items())],
            remapDifferences=remap_differences(self.world),
            functions=self.functions,
            links=links,
            coverage=coverage(
                self.world, links, self.reads, lambda address: self.describe(address)
            ),
            stats=dict(self.stats, seconds=round(time.time() - started)),
        )
