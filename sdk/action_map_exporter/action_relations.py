from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json

from .models import (
    ActionGuide,
    ActionSeed,
    Il2CppMethod,
    MotionSetHit,
    MotlistRequestSetEvent,
    MotionTarget,
    RequestSetIdentity,
    UnresolvedAction,
    UnresolvedCoordinate,
    UnresolvedNameHash,
)
from .request_sets import RequestSetCatalog, canonical_rcol_path
from .track_colliders import TrackColliderCatalog, TrackColliderRoute
from .utils import murmur3_utf16


@dataclass(slots=True)
class ActionRelationResult:
    relations: list[dict[str, object]]
    unresolved_actions: list[UnresolvedAction]
    unresolved_coordinates: list[UnresolvedCoordinate]
    actions_with_motion_sets: int
    mapped_actions: set[ActionSeed]
    ambiguous_coordinates: set[tuple[str, int]]
    missing_coordinates: set[tuple[str, int]]
    unresolved_names: list[UnresolvedNameHash]


@dataclass(frozen=True, slots=True)
class _EventGroup:
    request_set_id: int
    events: tuple[MotlistRequestSetEvent, ...]
    candidates: tuple[RequestSetIdentity, ...]
    route: TrackColliderRoute | None = None


@dataclass(frozen=True, slots=True)
class _ResolutionContext:
    action: ActionSeed
    target: MotionTarget
    hits: tuple[MotionSetHit, ...]
    event_groups: tuple[_EventGroup, ...]
    action_name_hash: int | None
    motion_anchor_rcol: str | None


@dataclass(frozen=True, slots=True)
class _ResolvedRequestSet:
    request_set: RequestSetIdentity
    method: str


class _RelationBuilder:
    def __init__(
        self, action: ActionSeed | ActionGuide, request_set: RequestSetIdentity
    ) -> None:
        self.action = action
        self.request_set = request_set
        self._evidence: dict[str, dict[str, object]] = {}
        self._resolutions: set[str] = set()
        self._sources: set[str] = set()
        self._name_candidates: tuple[int, ...] = ()
        self._inherited_classes: set[str] = set()
        self._has_own_motion_hit = False

    def add_evidence(self, item: dict[str, object]) -> None:
        self._evidence[json.dumps(item, sort_keys=True)] = item

    def add_resolution(self, value: str) -> None:
        self._resolutions.add(value)

    def add_source(self, value: str) -> None:
        self._sources.add(value)

    def add_name_candidates(self, guide_ids: tuple[int, ...]) -> None:
        self._name_candidates = guide_ids

    def build(self) -> dict[str, object]:
        action_hash = get_action_name_hash(self.action)
        name_candidate_only = self._resolutions == {"action_name_hash_candidate"}
        relation: dict[str, object] = {
            "scope": self.action.scope,
            "actionIdentity": action_identity(self.action),
            "actionGuideId": self.action.guide_id,
            "actionOrder": self.action.guide_order,
            "actionInternalName": self.action.internal_name,
            "actionNameGuid": self.action.name_guid,
            "actionJapaneseName": self.action.japanese_name,
        }
        if action_hash is not None:
            relation["actionNameHash"] = action_hash
        relation.update(
            {
                "fallbackName": self.action.internal_name,
                "source": "+".join(sorted(self._sources)),
                "resolutionMethods": sorted(self._resolutions),
                "confidence": "derived" if name_candidate_only else "proven",
                "conditions": (
                    [
                        {
                            "kind": "action_name_hash_candidates",
                            "candidateGuideIds": list(self._name_candidates),
                        }
                    ]
                    if name_candidate_only
                    else []
                ),
                "rcol": self.request_set.rcol,
                "requestSetId": self.request_set.request_set_id,
                "keyHash": self.request_set.key_hash,
                "sourceRequestSetOrdinal": self.request_set.source_request_set_ordinal,
                "evidence": sorted(
                    self._evidence.values(),
                    key=lambda item: (
                        str(item["actionClass"]),
                        str(item["functionAddress"]),
                        str(item["instructionAddress"]),
                        int(item["motionSetId"]),
                    ),
                ),
                "shellEvidence": [],
            }
        )
        inherited = self._inherited_declaring_classes()
        if inherited:
            # Base-class code may pick this motion only on some branch, so a
            # reader must be able to tell it from the class's own motion.
            relation["conditions"].append(
                {"kind": "inherited_action_method", "declaringClasses": inherited}
            )
        return relation

    def add_motion_hit(self, inherited_from: str | None) -> None:
        if inherited_from is None:
            self._has_own_motion_hit = True
        else:
            self._inherited_classes.add(inherited_from)

    def _inherited_declaring_classes(self) -> list[str]:
        """Declaring base classes when every motion hit came from them."""
        if self._has_own_motion_hit:
            return []
        return sorted(self._inherited_classes)


def build_action_relations(
    actions: list[ActionSeed],
    hits_by_action: dict[ActionSeed, list[MotionSetHit]],
    request_sets: RequestSetCatalog,
    methods_by_type: dict[str, list[Il2CppMethod]],
    *,
    guides: list[ActionGuide] | None = None,
    track_colliders: TrackColliderCatalog | None = None,
) -> ActionRelationResult:
    contexts, exact_track_rcols, track_rcols = _build_resolution_contexts(
        actions, hits_by_action, request_sets, track_colliders
    )
    contexts_by_action: dict[ActionSeed, list[_ResolutionContext]] = defaultdict(list)
    for context in contexts:
        contexts_by_action[context.action].append(context)

    unresolved_actions: list[UnresolvedAction] = []
    unresolved_coordinates: dict[tuple[str, int, str], UnresolvedCoordinate] = {}
    relation_builders: dict[tuple[object, ...], _RelationBuilder] = {}
    mapped_actions: set[ActionSeed] = set()
    ambiguous_coordinates: set[tuple[str, int]] = set()
    missing_coordinates: set[tuple[str, int]] = set()
    actions_with_motion_sets = 0

    names_by_hash: dict[tuple[str, int], dict[int, ActionGuide | ActionSeed]] = (
        defaultdict(dict)
    )
    for action in guides if guides is not None else actions:
        action_hash = get_action_name_hash(action)
        if action_hash is None:
            continue
        names_by_hash[(action.scope, action_hash)][action.guide_id] = action
    unresolved_names = []
    matched_guides: set[tuple[str, int]] = set()
    defined_guides = {(action.scope, action.guide_id) for action in actions}
    for (scope, action_hash), names in sorted(names_by_hash.items()):
        candidate_ids = tuple(sorted(names))
        if len(names) != 1:
            if request_sets.find_by_key_hash(scope, action_hash):
                unresolved_names.append(
                    UnresolvedNameHash(scope, action_hash, candidate_ids)
                )
            # Class-backed actions remain named candidates, explicitly marked
            # derived. Do not invent bindings for ambiguous guide-only entries.
            eligible = [
                name
                for name in names.values()
                if (scope, name.guide_id) in defined_guides
            ]
        else:
            eligible = list(names.values())
        for action in eligible:
            for request_set in request_sets.find_by_key_hash(action.scope, action_hash):
                builder = _get_relation_builder(relation_builders, action, request_set)
                builder.add_source("static_action_name_hash")
                builder.add_resolution(
                    "direct_action_name_hash"
                    if len(names) == 1
                    else "action_name_hash_candidate"
                )
                if len(names) > 1:
                    builder.add_name_candidates(candidate_ids)
                matched_guides.add((action.scope, action.guide_id))
    mapped_actions.update(a for a in actions if (a.scope, a.guide_id) in matched_guides)

    for action in actions:
        action_methods = methods_by_type.get(action.class_name, [])
        action_contexts = contexts_by_action.get(action, [])
        if not action_methods:
            if action not in mapped_actions:
                unresolved_actions.append(
                    _unresolved(action, "type_or_method_not_in_il2cpp_dump")
                )
            continue
        if not action_contexts:
            if action not in mapped_actions:
                unresolved_actions.append(
                    _unresolved(action, "no_valid_motion_set_constant")
                )
            continue

        actions_with_motion_sets += 1
        mapped = action in mapped_actions
        for context in action_contexts:
            for event_group in context.event_groups:
                resolved = _resolve_request_set(
                    context,
                    event_group,
                    exact_track_rcols,
                    track_rcols,
                )
                if resolved is None:
                    if event_group.candidates:
                        reason = "request_set_coordinate_ambiguous"
                    elif event_group.route is not None:
                        reason = "request_set_not_in_track_collider"
                    else:
                        reason = "request_set_coordinate_not_found"
                    coordinate = (action.scope, event_group.request_set_id)
                    if event_group.candidates:
                        ambiguous_coordinates.add(coordinate)
                    else:
                        missing_coordinates.add(coordinate)
                    candidate_rcols = _distinct_ignore_case(
                        candidate.rcol for candidate in event_group.candidates
                    )
                    unresolved_coordinates[
                        (action.scope, event_group.request_set_id, reason)
                    ] = UnresolvedCoordinate(
                        scope=action.scope,
                        request_set_id=event_group.request_set_id,
                        reason=reason,
                        candidate_count=len(event_group.candidates),
                        candidate_rcols=tuple(
                            sorted(candidate_rcols, key=str.casefold)
                        ),
                    )
                    continue

                mapped = True
                mapped_actions.add(action)
                builder = _get_relation_builder(
                    relation_builders, action, resolved.request_set
                )
                builder.add_source("static_action_motion")
                builder.add_resolution(resolved.method)
                for hit in context.hits:
                    evidence: dict[str, object] = {
                        "actionClass": hit.action_class,
                        "methodName": hit.method_name,
                        "functionAddress": f"0x{hit.function_address:x}",
                        "instructionAddress": f"0x{hit.instruction_address:x}",
                        "instructionCode": hit.instruction_code,
                        "motionSetId": hit.target.motion_set_id,
                        "bankId": hit.target.bank_id,
                        "motionId": hit.target.motion_id,
                        "motlistSourcePath": hit.target.motlist_source_path,
                        "motionName": event_group.events[0].motion_name,
                        "trackName": event_group.events[0].track_name,
                        "eventCount": len(event_group.events),
                    }
                    if event_group.route is not None:
                        evidence["trackColliderOwner"] = event_group.route.owner
                    inherited = (
                        hit.action_class != action.class_name
                        and not hit.constructor_chain
                    )
                    if inherited:
                        builder.add_resolution("inherited_action_method")
                    builder.add_motion_hit(hit.action_class if inherited else None)
                    if hit.motion_group:
                        builder.add_resolution("motion_group_set")
                        evidence["motionGroup"] = dict(hit.motion_group)
                    if hit.field_evidence:
                        builder.add_resolution("constructor_motion_field")
                        evidence["fieldWrite"] = dict(hit.field_evidence)
                    if hit.constructor_chain:
                        builder.add_resolution("inherited_constructor_motion_field")
                        evidence["constructorChain"] = [
                            {
                                "callerType": cls,
                                "callerMethod": name,
                                "callerFunctionAddress": f"0x{address:x}",
                                "callInstructionAddress": f"0x{call:x}",
                            }
                            for cls, name, address, call in hit.constructor_chain
                        ]
                    builder.add_evidence(evidence)
        if not mapped:
            unresolved_actions.append(
                _unresolved(
                    action, "motion_sets_have_no_exact_action_value_request_set"
                )
            )

    relations = [builder.build() for builder in relation_builders.values()]
    relations.sort(
        key=lambda relation: (
            str(relation["scope"]),
            int(relation["actionOrder"]),
            int(relation["actionGuideId"]),
            str(relation["rcol"]).casefold(),
            int(relation["requestSetId"]),
            int(relation["keyHash"]),
            int(relation["sourceRequestSetOrdinal"]),
        )
    )
    unresolved_actions = sorted(
        set(unresolved_actions),
        key=lambda item: (
            item.scope,
            item.action_internal_name,
            item.action_class,
        ),
    )
    coordinates = sorted(
        unresolved_coordinates.values(),
        key=lambda item: (item.scope, item.request_set_id, item.reason),
    )
    return ActionRelationResult(
        relations=relations,
        unresolved_actions=unresolved_actions,
        unresolved_coordinates=coordinates,
        actions_with_motion_sets=actions_with_motion_sets,
        mapped_actions=mapped_actions,
        ambiguous_coordinates=ambiguous_coordinates,
        missing_coordinates=missing_coordinates,
        unresolved_names=unresolved_names,
    )


def action_identity(action: ActionSeed | ActionGuide) -> str:
    """Unguided classes all carry guide ID -1, so only the class tells them apart."""
    if isinstance(action, ActionSeed) and not action.guided:
        return f"class:{action.scope}:{action.class_name}"
    return f"guide:{action.scope}:{action.guide_id}"


def get_action_name_hash(action: ActionSeed | ActionGuide) -> int | None:
    return murmur3_utf16(action.japanese_name) if action.japanese_name.strip() else None


def _get_relation_builder(
    builders: dict[tuple[object, ...], _RelationBuilder],
    action: ActionSeed | ActionGuide,
    request_set: RequestSetIdentity,
) -> _RelationBuilder:
    key = (
        action_identity(action),
        request_set.rcol,
        request_set.request_set_id,
        request_set.key_hash,
        request_set.source_request_set_ordinal,
    )
    if key not in builders:
        builders[key] = _RelationBuilder(action, request_set)
    return builders[key]


def _build_resolution_contexts(
    actions: list[ActionSeed],
    hits_by_action: dict[ActionSeed, list[MotionSetHit]],
    request_sets: RequestSetCatalog,
    track_colliders: TrackColliderCatalog | None = None,
) -> tuple[
    list[_ResolutionContext],
    dict[tuple[str, str, str], dict[str, str]],
    dict[tuple[str, str], dict[str, str]],
]:
    contexts: list[_ResolutionContext] = []
    exact_track_rcols: dict[tuple[str, str, str], dict[str, str]] = {}
    track_rcols: dict[tuple[str, str], dict[str, str]] = {}
    for action in actions:
        action_hash = get_action_name_hash(action)
        hit_groups: dict[int, list[MotionSetHit]] = {}
        for hit in hits_by_action[action]:
            hit_groups.setdefault(hit.target.motion_set_id, []).append(hit)
        for hits in hit_groups.values():
            target = hits[0].target
            grouped_events: dict[tuple[int, str], list[MotlistRequestSetEvent]] = {}
            for event in target.events:
                grouped_events.setdefault(
                    (event.request_set_id, event.track_name), []
                ).append(event)
            event_groups = tuple(
                _event_group(
                    action.scope,
                    request_set_id,
                    tuple(events),
                    request_sets,
                    (
                        None
                        if track_colliders is None
                        else track_colliders.route(action.scope, track_name)
                    ),
                )
                for (request_set_id, track_name), events in grouped_events.items()
            )
            anchor_rcols = (
                []
                if action_hash is None
                else _distinct_ignore_case(
                    candidate.rcol
                    for group in event_groups
                    for candidate in group.candidates
                    if candidate.key_hash == action_hash
                )
            )
            contexts.append(
                _ResolutionContext(
                    action=action,
                    target=target,
                    hits=tuple(hits),
                    event_groups=event_groups,
                    action_name_hash=action_hash,
                    motion_anchor_rcol=(
                        anchor_rcols[0] if len(anchor_rcols) == 1 else None
                    ),
                )
            )

            if action_hash is None:
                continue
            for event_group in event_groups:
                matching_rcols = _distinct_ignore_case(
                    candidate.rcol
                    for candidate in event_group.candidates
                    if candidate.key_hash == action_hash
                )
                if len(matching_rcols) != 1:
                    continue
                for event in event_group.events:
                    _add_rcol(
                        exact_track_rcols,
                        (action.scope, event.main_track_name, event.track_name),
                        matching_rcols[0],
                    )
                    _add_rcol(
                        track_rcols,
                        (action.scope, event.track_name),
                        matching_rcols[0],
                    )
    return contexts, exact_track_rcols, track_rcols


def _resolve_request_set(
    context: _ResolutionContext,
    event_group: _EventGroup,
    exact_track_rcols: dict[tuple[str, str, str], dict[str, str]],
    track_rcols: dict[tuple[str, str], dict[str, str]],
) -> _ResolvedRequestSet | None:
    if len(event_group.candidates) == 1:
        return _ResolvedRequestSet(
            event_group.candidates[0],
            (
                "single_coordinate"
                if event_group.route is None
                else "track_owner_collider"
            ),
        )
    if not event_group.candidates:
        return None
    if context.action_name_hash is not None:
        matches = [
            candidate
            for candidate in event_group.candidates
            if candidate.key_hash == context.action_name_hash
        ]
        if len(matches) == 1:
            return _ResolvedRequestSet(matches[0], "action_name_hash")
    if context.motion_anchor_rcol is not None:
        candidate = _unique_candidate_in_rcol(
            event_group.candidates, context.motion_anchor_rcol
        )
        if candidate is not None:
            return _ResolvedRequestSet(candidate, "motion_name_hash_anchor_rcol")

    exact_rcol = _unique_learned_rcol(
        exact_track_rcols.get(
            (context.action.scope, event.main_track_name, event.track_name)
        )
        for event in event_group.events
    )
    if exact_rcol is not None:
        candidate = _unique_candidate_in_rcol(event_group.candidates, exact_rcol)
        if candidate is not None:
            return _ResolvedRequestSet(candidate, "learned_main_track_rcol")

    track_rcol = _unique_learned_rcol(
        track_rcols.get((context.action.scope, event.track_name))
        for event in event_group.events
    )
    if track_rcol is not None:
        candidate = _unique_candidate_in_rcol(event_group.candidates, track_rcol)
        if candidate is not None:
            return _ResolvedRequestSet(candidate, "learned_track_rcol")
    return None


def _event_group(
    scope: str,
    request_set_id: int,
    events: tuple[MotlistRequestSetEvent, ...],
    request_sets: RequestSetCatalog,
    route: TrackColliderRoute | None,
) -> _EventGroup:
    candidates = tuple(request_sets.find(scope, request_set_id))
    if route is not None:
        allowed = set(route.rcols)
        candidates = tuple(
            candidate
            for candidate in candidates
            if canonical_rcol_path(candidate.rcol) in allowed
        )
    return _EventGroup(request_set_id, events, candidates, route)


def _unique_candidate_in_rcol(
    candidates: tuple[RequestSetIdentity, ...],
    rcol: str,
) -> RequestSetIdentity | None:
    matches = [
        candidate
        for candidate in candidates
        if candidate.rcol.casefold() == rcol.casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    named = [candidate for candidate in matches if candidate.key_hash != 0]
    return named[0] if len(named) == 1 else None


def _unique_learned_rcol(values: object) -> str | None:
    unique: dict[str, str] = {}
    for value in values:  # type: ignore[union-attr]
        if value is None or len(value) != 1:
            continue
        rcol = next(iter(value.values()))
        unique.setdefault(rcol.casefold(), rcol)
    return next(iter(unique.values())) if len(unique) == 1 else None


def _add_rcol(
    values: dict[object, dict[str, str]],
    key: object,
    rcol: str,
) -> None:
    values.setdefault(key, {}).setdefault(rcol.casefold(), rcol)


def _distinct_ignore_case(values: object) -> list[str]:
    distinct: dict[str, str] = {}
    for value in values:  # type: ignore[union-attr]
        distinct.setdefault(value.casefold(), value)
    return list(distinct.values())


def _unresolved(action: ActionSeed, reason: str) -> UnresolvedAction:
    return UnresolvedAction(
        scope=action.scope,
        action_class=action.class_name,
        action_guide_id=action.guide_id,
        action_internal_name=action.internal_name,
        reason=reason,
    )


def unresolved_action_to_dict(item: UnresolvedAction) -> dict[str, object]:
    return {
        "scope": item.scope,
        "actionClass": item.action_class,
        "actionGuideId": item.action_guide_id,
        "actionInternalName": item.action_internal_name,
        "reason": item.reason,
    }


def unresolved_coordinate_to_dict(item: UnresolvedCoordinate) -> dict[str, object]:
    return {
        "scope": item.scope,
        "requestSetId": item.request_set_id,
        "reason": item.reason,
        "candidateCount": item.candidate_count,
        "candidateRcols": list(item.candidate_rcols),
    }
