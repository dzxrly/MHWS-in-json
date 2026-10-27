from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePath
import re

from .action_relations import action_identity, get_action_name_hash
from .models import (
    ActionSeed,
    DirectCallHit,
    RequestSetIdentity,
    ShellEntryRecord,
    UnresolvedShellEntry,
)
from .pfb import PfbResourceCatalog
from .request_sets import RequestSetCatalog
from .scanners import AmmoItemMapCatalog
from .shells import ShellCatalog
from .collision_references import collision_evidence
from .shell_requests import (
    ResolvedShellRequest,
    ShellRequestResolution,
    reference_evidence,
    resolve_shell_requests,
)

_SHELL_FAMILY_SUFFIXES = {
    "blast",
    "bullet",
    "child",
    "const",
    "em",
    "ground",
    "hit",
    "l",
    "lv",
    "parent",
    "r",
    "scar",
    "shot",
    "slash",
    "success",
    "wall",
}
_ACTION_SEMANTIC_NOISE = {
    "action",
    "ammo",
    "attack",
    "base",
    "battle",
    "bullet",
    "c",
    "charge",
    "create",
    "do",
    "end",
    "enter",
    "exit",
    "fly",
    "idle",
    "light",
    "porter",
    "remove",
    "shell",
    "shoot",
    "shot",
    "start",
    "sub",
    "triple",
    "update",
    "wp",
}
_SHELL_SEMANTIC_NOISE = {"shell", "shoot"}
_SEMANTIC_TOKEN = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|[^A-Za-z0-9]|$)|[A-Z]?[a-z]+|[0-9]+"
)


@dataclass(slots=True)
class ShellRelationResult:
    relations: list[dict[str, object]]
    entries_with_relations: int
    unresolved: list[UnresolvedShellEntry]
    entries: int


class _ShellRelationBuilder:
    def __init__(self, request_set: RequestSetIdentity, action: ActionSeed) -> None:
        self.request_set = request_set
        self.action = action
        self._evidence: dict[str, dict[str, object]] = {}
        self._resolutions: set[str] = set()

    def add_evidence(self, item: dict[str, object]) -> None:
        self._evidence.setdefault(repr(item), item)

    def add_resolution(self, value: str) -> None:
        self._resolutions.add(value)

    def build(self) -> dict[str, object]:
        relation: dict[str, object] = {
            "scope": self.request_set.scope,
            "actionIdentity": action_identity(self.action),
            "actionOrder": self.action.guide_order,
            "actionInternalName": self.action.internal_name,
            "actionNameGuid": self.action.name_guid,
            "actionJapaneseName": self.action.japanese_name,
            "fallbackName": self.action.internal_name,
            "source": "static_action_name_hash+static_shell_prefab",
            "resolutionMethods": ["shell_list_prefab_rcol", *sorted(self._resolutions)],
            "confidence": (
                "proven"
                if "shell_rcol_action_name_hash" in self._resolutions
                else "derived"
            ),
            "conditions": [],
            "rcol": self.request_set.rcol,
            "requestSetId": self.request_set.request_set_id,
            "keyHash": self.request_set.key_hash,
            "sourceRequestSetOrdinal": self.request_set.source_request_set_ordinal,
            "evidence": [],
            "shellEvidence": sorted(self._evidence.values(), key=repr),
            "actionGuideId": self.action.guide_id,
        }
        action_hash = get_action_name_hash(self.action)
        if action_hash is not None:
            relation["actionNameHash"] = action_hash
        return relation


def build_shell_relations(
    shells: ShellCatalog,
    prefabs: PfbResourceCatalog,
    request_sets: RequestSetCatalog,
    ammo_item_map: AmmoItemMapCatalog,
    actions: list[ActionSeed],
    handling_calls_by_action: dict[ActionSeed, list[DirectCallHit]],
    *,
    resolution: ShellRequestResolution | None = None,
) -> ShellRelationResult:
    resolution = resolution or resolve_shell_requests(shells, prefabs, request_sets)
    resolved = resolution.resolved
    direct_actions, action_resolutions = _match_shell_actions(
        resolved, shells, ammo_item_map, actions, handling_calls_by_action
    )

    builders: dict[tuple[object, ...], _ShellRelationBuilder] = {}
    for item in resolved:
        entry_key = _entry_key(item.entry)
        action = direct_actions.get(entry_key)
        if action is None:
            continue
        relation_key = (action_identity(action), *item.request_set.target_key)
        if relation_key not in builders:
            builders[relation_key] = _ShellRelationBuilder(item.request_set, action)
        builder = builders[relation_key]
        name_resolution = action_resolutions[entry_key]
        action_calls = _shell_call_evidence(
            item.entry, handling_calls_by_action.get(action, [])
        )
        builder.add_evidence(
            {
                **reference_evidence(
                    item.entry, item.prefab_chain, item.rcol_resource_path
                ),
                "shellNameHash": item.entry.shell_name_hash,
                "ammoTypeName": item.entry.ammo_type_name,
                "prefabPath": item.entry.prefab_path,
                "prefabArchivePath": item.prefab_chain[0].archive_path,
                "mainParamPath": item.entry.main_param_path,
                "collisionId": item.collision_id,
                "rcolResourcePath": item.rcol_resource_path,
                "nameResolution": name_resolution,
                "actionCalls": action_calls,
                **collision_evidence(item.entry, item.collision_id),
            }
        )
        builder.add_resolution(name_resolution)

    return ShellRelationResult(
        relations=[builder.build() for builder in builders.values()],
        entries_with_relations=len(direct_actions),
        unresolved=sorted(
            resolution.unresolved,
            key=lambda item: (
                item.source_scope,
                item.entry_index,
                item.collision_id,
            ),
        ),
        entries=len(shells.entries),
    )


def _match_shell_actions(
    resolved: list[ResolvedShellRequest],
    shells: ShellCatalog,
    ammo_item_map: AmmoItemMapCatalog,
    actions: list[ActionSeed],
    handling_calls_by_action: dict[ActionSeed, list[DirectCallHit]],
) -> tuple[dict[tuple[str, int], ActionSeed], dict[tuple[str, int], str]]:
    entries = _distinct_entries(item.entry for item in resolved)
    # Ammo labels belong to resourceRelations and must not become pseudo actions.
    ammo_entries = {
        _entry_key(entry)
        for entry in entries
        if (core_type := shells.get_core_ammo_type_name(entry.fixed_name)) is not None
        and ammo_item_map.find(core_type) is not None
    }
    actions_by_hash: dict[tuple[str, int], list[ActionSeed]] = defaultdict(list)
    seen_actions_by_hash: dict[tuple[str, int], set[str]] = defaultdict(set)
    for action in actions:
        action_hash = get_action_name_hash(action)
        if action_hash is None:
            continue
        hash_key = (action.scope, action_hash)
        identity = action_identity(action)
        if identity not in seen_actions_by_hash[hash_key]:
            seen_actions_by_hash[hash_key].add(identity)
            actions_by_hash[hash_key].append(action)
    for values in actions_by_hash.values():
        values.sort(key=lambda action: (action.guide_order, action.guide_id))

    direct_actions: dict[tuple[str, int], ActionSeed] = {}
    action_resolutions: dict[tuple[str, int], str] = {}
    resolved_groups: dict[tuple[str, int], list[ResolvedShellRequest]] = defaultdict(
        list
    )
    for item in resolved:
        resolved_groups[_entry_key(item.entry)].append(item)
    for key, group in resolved_groups.items():
        if key in ammo_entries:
            continue
        matches: list[ActionSeed] = []
        seen: set[str] = set()
        for item in group:
            for action in actions_by_hash.get(
                (item.entry.source_scope, item.request_set.key_hash), []
            ):
                identity = action_identity(action)
                if identity not in seen:
                    seen.add(identity)
                    matches.append(action)
        if len(matches) == 1:
            direct_actions[key] = matches[0]
            action_resolutions[key] = "shell_rcol_action_name_hash"

    anchored_actions = [
        (entry, direct_actions.get(_entry_key(entry)))
        for entry in entries
        if direct_actions.get(_entry_key(entry)) is not None
        and entry.fixed_name.strip()
    ]
    for entry in entries:
        key = _entry_key(entry)
        if key in ammo_entries or key in direct_actions:
            continue
        folded = entry.fixed_name.casefold()
        prefix_matches = sorted(
            (
                anchor
                for anchor in anchored_actions
                if anchor[0].source_scope == entry.source_scope
                and (
                    folded == anchor[0].fixed_name.casefold()
                    or folded.startswith(anchor[0].fixed_name.casefold() + "_")
                )
            ),
            key=lambda anchor: -len(anchor[0].fixed_name),
        )
        if not prefix_matches:
            continue
        longest = len(prefix_matches[0][0].fixed_name)
        matching_actions: list[ActionSeed] = []
        seen: set[str] = set()
        for anchor_entry, action in prefix_matches:
            assert action is not None
            identity = action_identity(action)
            if len(anchor_entry.fixed_name) == longest and identity not in seen:
                seen.add(identity)
                matching_actions.append(action)
        if len(matching_actions) == 1:
            direct_actions[key] = matching_actions[0]
            action_resolutions[key] = "learned_shell_action_family"

    for entry in entries:
        key = _entry_key(entry)
        if key in ammo_entries or key in direct_actions:
            continue
        action = _find_static_shell_family_action(
            entry, actions, handling_calls_by_action
        )
        if action is None:
            continue
        direct_actions[key] = action
        has_handling_call = any(
            _is_shell_handling_call_for_family(entry, hit)
            for hit in handling_calls_by_action.get(action, [])
        )
        action_resolutions[key] = (
            "action_handling_shell_family"
            if has_handling_call
            else "action_class_shell_family"
        )

    return direct_actions, action_resolutions


def unresolved_shell_to_dict(item: UnresolvedShellEntry) -> dict[str, object]:
    return {
        "sourceScope": item.source_scope,
        "entryIndex": item.entry_index,
        "fixedName": item.fixed_name,
        "prefabPath": item.prefab_path,
        "collisionId": item.collision_id,
        "reason": item.reason,
        "candidateCount": item.candidate_count,
        "rcolResources": list(item.rcol_resources),
    }


def _find_static_shell_family_action(
    entry: ShellEntryRecord,
    actions: list[ActionSeed],
    handling_calls_by_action: dict[ActionSeed, list[DirectCallHit]],
) -> ActionSeed | None:
    family_tokens = _shell_family_tokens(entry.fixed_name)
    if not family_tokens or not any(len(token) >= 4 for token in family_tokens):
        return None
    candidates = sorted(
        (
            action
            for action in actions
            if action.scope == entry.source_scope
            and action.guide_id != -1
            and action.name_guid.strip()
            and action.japanese_name.strip()
            and _tokens_match(family_tokens, _action_semantic_tokens(action))
        ),
        key=lambda action: (
            action.guide_order,
            action.guide_id,
            action.class_name,
        ),
    )
    if not candidates:
        return None
    direct_call_candidates = [
        action
        for action in candidates
        if any(
            _is_shell_handling_call_for_family(entry, hit)
            for hit in handling_calls_by_action.get(action, [])
        )
    ]
    if direct_call_candidates:
        candidates = direct_call_candidates
    firing_candidates = [action for action in candidates if _is_firing_action(action)]
    if firing_candidates:
        candidates = firing_candidates
    minimum_extra = min(
        sum(
            not any(_equivalent_token(expected, token) for expected in family_tokens)
            for token in _action_class_semantic_tokens(action)
        )
        for action in candidates
    )
    candidates = [
        action
        for action in candidates
        if sum(
            not any(_equivalent_token(expected, token) for expected in family_tokens)
            for token in _action_class_semantic_tokens(action)
        )
        == minimum_extra
    ]
    display_names = {action.japanese_name.strip() for action in candidates}
    return candidates[0] if len(display_names) == 1 else None


def _is_firing_action(action: ActionSeed) -> bool:
    class_tokens = _semantic_tokens(action.class_name.rsplit(".", 1)[-1])
    if class_tokens & {"charge", "end", "idle", "start"}:
        return False
    return bool(class_tokens & {"attack", "create", "shoot", "shot"})


def _is_shell_handling_call_for_family(
    entry: ShellEntryRecord,
    hit: DirectCallHit,
) -> bool:
    family_tokens = _shell_family_tokens(entry.fixed_name)
    if not family_tokens:
        return False
    callee_tokens = _semantic_tokens(hit.callee.method_name) - _SHELL_SEMANTIC_NOISE
    if _tokens_match(family_tokens, callee_tokens):
        return True
    folded = hit.callee.method_name.casefold()
    return folded.startswith("shootshell") or folded.startswith("shootenery")


def _shell_call_evidence(
    entry: ShellEntryRecord,
    calls: list[DirectCallHit],
) -> list[dict[str, object]]:
    distinct: dict[tuple[object, ...], dict[str, object]] = {}
    for hit in calls:
        if not _is_shell_handling_call_for_family(entry, hit):
            continue
        item: dict[str, object] = {
            "actionClass": hit.caller_type,
            "actionMethod": hit.caller_method,
            "actionFunctionAddress": f"0x{hit.caller_function_address:x}",
            "callInstructionAddress": f"0x{hit.call_instruction_address:x}",
            "calleeType": hit.callee.type_name,
            "calleeMethod": hit.callee.method_name,
            "calleeFunctionAddress": f"0x{hit.callee.function_address:x}",
        }
        distinct[tuple(item.values())] = item
    return sorted(
        distinct.values(),
        key=lambda item: (
            str(item["actionFunctionAddress"]),
            str(item["callInstructionAddress"]),
        ),
    )


def _shell_family_tokens(fixed_name: str) -> set[str]:
    return {
        token
        for token in _semantic_tokens(fixed_name)
        if token not in _SHELL_FAMILY_SUFFIXES and not token.isdigit()
    }


def _action_semantic_tokens(action: ActionSeed) -> set[str]:
    return {
        token
        for token in _semantic_tokens(
            action.class_name.rsplit(".", 1)[-1], action.internal_name
        )
        if token not in _ACTION_SEMANTIC_NOISE and not token.isdigit()
    }


def _action_class_semantic_tokens(action: ActionSeed) -> set[str]:
    return {
        token
        for token in _semantic_tokens(action.class_name.rsplit(".", 1)[-1])
        if token not in _ACTION_SEMANTIC_NOISE and not token.isdigit()
    }


def _semantic_tokens(*values: str) -> set[str]:
    return {
        match.group(0).lower()
        for value in values
        for match in _SEMANTIC_TOKEN.finditer(value)
    }


def _tokens_match(required: set[str], available: set[str]) -> bool:
    return all(
        any(_equivalent_token(expected, actual) for actual in available)
        for expected in required
    )


def _equivalent_token(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) < 5 or len(right) < 5 or abs(len(left) - len(right)) > 1:
        return False
    return _damerau_levenshtein_at_most_one(left, right)


def _damerau_levenshtein_at_most_one(left: str, right: str) -> bool:
    if len(left) == len(right):
        mismatches: list[int] = []
        for index, (left_char, right_char) in enumerate(zip(left, right)):
            if left_char != right_char:
                mismatches.append(index)
            if len(mismatches) > 2:
                return False
        return len(mismatches) <= 1 or (
            len(mismatches) == 2
            and mismatches[1] == mismatches[0] + 1
            and left[mismatches[0]] == right[mismatches[1]]
            and left[mismatches[1]] == right[mismatches[0]]
        )
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = 0
    long_index = 0
    edits = 0
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        edits += 1
        if edits > 1:
            return False
        long_index += 1
    return True


def _entry_key(entry: ShellEntryRecord) -> tuple[str, int]:
    return entry.source_scope, entry.entry_index


def _distinct_entries(values: object) -> list[ShellEntryRecord]:
    output: list[ShellEntryRecord] = []
    seen: set[tuple[str, int]] = set()
    for value in values:  # type: ignore[union-attr]
        key = _entry_key(value)
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output
