"""Small, persistent CLI diagnostics; never part of a battle-model contract."""

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback
from uuid import uuid4

_ACTIVE = ContextVar("enemy_sdk_runtime_log", default=None)


def active_run():
    return _ACTIVE.get()


def _options(options):
    return {
        key: str(value.resolve()) if isinstance(value, Path) else value
        for key, value in options.items()
    }


def _identity(row):
    return {key: row[key] for key in ("type", "method", "address", "end") if key in row}


def _unknown_reasons(expression):
    if expression.get("kind") == "unknown":
        return {expression.get("reason", "未说明原因")}
    if expression.get("kind") == "predicate":
        status = expression.get("predicate", {}).get("status")
        return set() if status == "verified" else {"规则未核实：" + str(status)}
    if expression.get("kind") == "not":
        return _unknown_reasons(expression["item"])
    return set().union(
        *(_unknown_reasons(item) for item in expression.get("items", []))
    )


class RunDiagnostics:
    def __init__(self, command, work_dir, options):
        self.command, self.options = command, _options(options)
        self.started = time.monotonic()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = (
            Path(work_dir).resolve()
            / "logs"
            / (f"{command}-{stamp}-{os.getpid()}-{uuid4().hex[:8]}.jsonl")
        )
        self.file = None
        self.seen = set()
        self.last_native = self.last_table = None
        self.stage = "startup"
        self.policies, self.declarations, self.unknowns = {}, [], {}
        self.unknown_counts = Counter()
        self.models = []
        self.catalog_ready = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.file = self.path.open("x", encoding="utf8", newline="\n")
        except OSError as error:
            self._unavailable(error)
        if self.file is not None:
            print("SDK 诊断日志：" + str(self.path), file=sys.stderr, flush=True)
        self.event(
            "start",
            command=command,
            options=self.options,
            argv=sys.argv,
            cwd=str(Path.cwd()),
        )

    def _unavailable(self, error):
        print(f"SDK 诊断日志无法写入 {self.path}：{error}", file=sys.stderr, flush=True)

    def event(self, event, **data):
        if self.file is None:
            return
        try:
            self.file.write(
                json.dumps(
                    dict(
                        time=datetime.now(timezone.utc).isoformat(), event=event, **data
                    ),
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
            self.file.flush()
        except OSError as error:
            try:
                self.file.close()
            except OSError:
                pass
            self.file = None
            self._unavailable(error)

    def inputs(self, options):
        self.options = _options(options)
        self.event("inputs", options=self.options)

    def set_stage(self, stage):
        self.stage = stage
        self.event("stage", stage=stage)

    def set_method(self, row, *, enemy_id=None, table_guid=None, resource=None):
        value = _identity(row)
        if table_guid is not None:
            value.update(enemyId=enemy_id, tableGuid=table_guid, resource=resource)
            self.last_table = value
            kind = "table_method"
        else:
            self.last_native = value
            kind = "native_method"
        key = kind, json.dumps(value, sort_keys=True)
        if key not in self.seen:
            self.seen.add(key)
            self.event(kind, **value)

    def manual_catalog(self, metadata, rows, monsters, resource_records):
        """Observe declarations and real import owners without granting a policy."""
        from ...monster import iter_monsters

        selected = self.options.get("enemy") or list(monsters)
        if isinstance(selected, str):
            selected = [selected]
        selected_owners = {}
        for enemy in selected:
            for source in monsters.get(enemy, {}).get("tableImportClosure", []):
                owner = resource_records[source].get("exportType")
                if owner is None:
                    continue
                selected_owners.setdefault(owner, set()).add(enemy)
        declarations = {}
        for module in iter_monsters():
            for attribute, capability in (
                ("LOCAL_HISTORY_TABLES", "local"),
                ("FORMULA_HISTORY_TABLES", "formula"),
            ):
                declared = getattr(module, attribute, {})
                # Sequence declarations bind their owner explicitly, as used
                # by LOCAL_HISTORY_EXPORT; do not infer it from a monster ID.
                groups = (
                    declared.items()
                    if isinstance(declared, dict)
                    else ((module.LOCAL_HISTORY_EXPORT, declared),)
                )
                for owner, stems in groups:
                    for stem in stems:
                        item = declarations.setdefault(
                            (owner, stem),
                            dict(
                                type=owner,
                                methodStem=stem,
                                tableGuid=stem[6:42].replace("_", "-"),
                                requested={},
                                declaredBy=[],
                            ),
                        )
                        item["requested"][capability] = True
                        if module.ENEMY_ID not in item["declaredBy"]:
                            item["declaredBy"].append(module.ENEMY_ID)
        for (owner, stem), item in sorted(declarations.items()):
            description = metadata.get(owner)
            matches = [
                name
                for name in (description or {}).get("methods", {})
                if name.startswith(stem) and name[len(stem) :].isdigit()
            ]
            cached = [
                row["method"] for row in rows.get(owner, []) if row["method"] in matches
            ]
            item.update(
                methods=matches,
                cachedMethods=cached,
                selectedEnemies=sorted(selected_owners.get(owner, [])),
            )
            item["identityStatus"] = (
                "type_missing"
                if description is None
                else (
                    "method_missing"
                    if not matches
                    else (
                        "ambiguous_method"
                        if len(matches) != 1
                        else "cache_method_missing" if not cached else "matched"
                    )
                )
            )
            item["scopeStatus"] = (
                "selected_import_owner"
                if item["selectedEnemies"]
                else "not_in_selected_import_closure"
            )
            self.declarations.append(item)
            self.event("manual_policy_catalog", **item)
        self.catalog_ready = True

    def history_requested(self, row, policy, *, enemy_id, table_guid, resource):
        if not policy:
            return
        key = enemy_id, row["type"], row["method"], table_guid, resource
        if key not in self.policies:
            value = dict(
                **_identity(row),
                enemyId=enemy_id,
                tableGuid=table_guid,
                resource=resource,
                requested={
                    name: bool(policy.get(name)) for name in ("local", "formula")
                },
                actual=None,
            )
            self.policies[key] = value
            self.event("manual_policy_requested", **value)

    def history_enabled(self, row, policy, history, *, enemy_id, table_guid, resource):
        if not policy:
            return
        key = enemy_id, row["type"], row["method"], table_guid, resource
        value = self.policies[key]
        actual = dict(
            local=bool(
                policy.get("local")
                and history
                and history.complete_discovery
                and (history.candidates or history.local_pairs)
            ),
            formula=bool(history and history.formula_enabled),
        )
        value.update(
            actual=actual,
            discoveredPairs=len(history.local_pairs) if history else 0,
            privateReadSites=len(history.read_sites) if history else 0,
            completeDiscovery=bool(history and history.complete_discovery),
            escapedSites=len(history.escaped_sites) if history else 0,
        )
        self.event("manual_policy_enabled", **value)

    def graph(self, graph):
        summary = dict(enemyId=graph["enemyId"], coverage=graph.get("coverage", {}))
        self.models.append(summary)
        self.event("model_summary", **summary)
        for table in graph["tables"]:
            for node in table["nodes"]:
                category = "flow" if node["kind"] == "unknown" else "condition"
                if category == "flow":
                    reasons = {node.get("reason", "未说明原因")}
                elif node["kind"] == "condition":
                    reasons = _unknown_reasons(
                        node.get("expression")
                        or dict(kind="predicate", predicate=node.get("predicate", {}))
                    )
                else:
                    continue
                if reasons:
                    self.unknown_counts[category] += 1
                for reason in reasons:
                    self._boundary(category, reason, graph["enemyId"], table, node)
        for field in ("selectionBoundaries", "resourceEntryBoundaries"):
            for boundary in graph.get(field, []):
                self.unknown_counts[field] += 1
                table = next(
                    (
                        table
                        for table in graph["tables"]
                        if boundary.get("tableGuid") == table.get("tableGuid")
                    ),
                    boundary,
                )
                self._boundary(
                    field,
                    boundary.get("reason", boundary.get("status", "未说明原因")),
                    graph["enemyId"],
                    table,
                    boundary,
                )

    def _boundary(self, category, reason, enemy, table, node):
        proof = table.get("evidence", {})
        evidence = [
            _identity(row) for row in (proof if isinstance(proof, list) else [proof])
        ]
        primary = evidence[0] if evidence else {}
        value = dict(
            category=category,
            reason=reason,
            type=table.get("nativeType") or primary.get("type"),
            method=table.get("nativeMethod") or primary.get("method"),
            methodAddress=primary.get("address"),
            evidence=evidence,
            tableGuid=table.get("tableGuid"),
            resource=table.get("resource"),
            nativeSite=node.get("nativeSite")
            or node.get("callSite")
            or node.get("requestSite")
            or node.get("site"),
            commandType=node.get("commandType") or node.get("expectedCommandType"),
            boundaryContext={
                key: node[key]
                for key in (
                    "programCounter",
                    "nativeBoundary",
                    "staticArray",
                    "status",
                    "site",
                    "source",
                    "reference",
                    "dispatcherCount",
                    "tableMethodCount",
                )
                if key in node
            },
        )
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        item = self.unknowns.setdefault(
            key, dict(**value, occurrences=0, enemyIds=[], nodeIds=[])
        )
        item["occurrences"] += 1
        if enemy not in item["enemyIds"]:
            item["enemyIds"].append(enemy)
        if node.get("id") is not None and node["id"] not in item["nodeIds"]:
            item["nodeIds"].append(node["id"])

    def finish(self, error=None):
        success = (
            error is None or isinstance(error, SystemExit) and error.code in (None, 0)
        )
        if not success:
            self.event(
                "error",
                exceptionType=type(error).__name__,
                message=str(error),
                traceback="".join(traceback.format_exception(error)),
                stage=self.stage,
                lastTableMethod=self.last_table,
                lastNativeMethod=self.last_native,
            )
        self.event(
            "unknown_summary",
            counts=dict(self.unknown_counts),
            reasonOccurrences=dict(
                Counter(
                    {
                        category: sum(
                            row["occurrences"]
                            for row in self.unknowns.values()
                            if row["category"] == category
                        )
                        for category in {
                            row["category"] for row in self.unknowns.values()
                        }
                    }
                )
            ),
            entries=list(self.unknowns.values()),
        )
        for item in self.declarations:
            observed = [
                row
                for row in self.policies.values()
                if row["type"] == item["type"] and row["method"] in item["methods"]
            ]
            item["observedEnemies"] = sorted({row["enemyId"] for row in observed})
            item["executionStatus"] = (
                "not_in_selected_import_closure"
                if not item["selectedEnemies"]
                else (
                    "declaration_unmatched"
                    if item["identityStatus"] != "matched"
                    else (
                        "not_reached"
                        if not observed
                        else (
                            "started_not_completed"
                            if any(row["actual"] is None for row in observed)
                            else "observed"
                        )
                    )
                )
            )
        self.event(
            "finish",
            status=(
                "success"
                if success
                else "interrupted" if isinstance(error, KeyboardInterrupt) else "error"
            ),
            elapsedSeconds=round(time.monotonic() - self.started, 3),
            lastTableMethod=self.last_table,
            lastNativeMethod=self.last_native,
            models=self.models,
            manualPolicyCatalog="completed" if self.catalog_ready else "not_reached",
            manualPolicyDeclarations=self.declarations,
            manualPolicies=list(self.policies.values()),
        )
        if self.file is not None:
            try:
                self.file.close()
            except OSError as close_error:
                self._unavailable(close_error)
            self.file = None
            print("SDK 诊断日志：" + str(self.path), file=sys.stderr, flush=True)


@contextmanager
def diagnostic_run(command, work_dir, options):
    """Record a CLI run while preserving its original return/exception behavior."""
    logger = RunDiagnostics(command, work_dir, options)
    token = _ACTIVE.set(logger)
    error = None
    try:
        yield logger
    except BaseException as caught:
        error = caught
        raise
    finally:
        try:
            logger.finish(error)
        finally:
            _ACTIVE.reset(token)


def record_graph(graph):
    if (logger := active_run()) is not None:
        logger.graph(graph)
