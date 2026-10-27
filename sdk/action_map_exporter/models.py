from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ActionGuide:
    scope: str
    guide_id: int
    guide_order: int
    internal_name: str
    name_guid: str
    japanese_name: str


@dataclass(frozen=True, slots=True)
class ActionSeed:
    scope: str
    class_name: str
    guide_id: int
    guide_order: int
    internal_name: str
    name_guid: str
    japanese_name: str
    source_files: tuple[str, ...]
    # False when _ActionGuideID has no ActionGuide entry (usually the -1 sentinel).
    guided: bool = True


@dataclass(frozen=True, slots=True)
class MotbankEntryRecord:
    scope: str
    bank_id: int
    bank_type: int
    motlist_path: str
    source_path: str


@dataclass(frozen=True, slots=True)
class MotlistRequestSetEvent:
    motion_id: int
    motion_name: str
    request_set_id: int
    clip_source: str
    clip_index: int
    main_track_name: str
    track_index: int
    track_name: str
    start_frame: float
    end_frame: float | None


@dataclass(frozen=True, slots=True)
class MotlistIndexDocument:
    source_path: str
    motlist_name: str
    events_by_motion: dict[int, tuple[MotlistRequestSetEvent, ...]]


@dataclass(frozen=True, slots=True)
class MotionTarget:
    scope: str
    motion_set_id: int
    bank_id: int
    motion_id: int
    motlist_source_path: str
    motlist_name: str
    events: tuple[MotlistRequestSetEvent, ...]


@dataclass(frozen=True, slots=True)
class Il2CppMethod:
    type_name: str
    method_name: str
    function_address: int


@dataclass(frozen=True, slots=True)
class MotionSetHit:
    action_class: str
    method_name: str
    function_address: int
    instruction_address: int
    instruction_code: str
    immediate_operand: int
    target: MotionTarget
    field_evidence: tuple[tuple[str, str | int], ...] = ()
    constructor_chain: tuple[tuple[str, str, int, int], ...] = ()
    motion_group: tuple[tuple[str, str | int], ...] = ()


@dataclass(frozen=True, slots=True)
class DirectCallHit:
    caller_type: str
    caller_method: str
    caller_function_address: int
    call_instruction_address: int
    callee: Il2CppMethod


@dataclass(frozen=True, slots=True)
class RequestSetIdentity:
    scope: str
    rcol: str
    request_set_id: int
    key_hash: int
    source_request_set_ordinal: int
    user_data_type: str = ""
    resource_paths: tuple[str, ...] = ()
    attack_payload_hash: str = ""
    shape_types: tuple[str, ...] = ()

    @property
    def target_key(self) -> tuple[str, str, int, int, int]:
        """Exact target identity, independent of display metadata and path casing."""
        return (
            self.scope,
            self.rcol.casefold(),
            self.request_set_id,
            self.key_hash,
            self.source_request_set_ordinal,
        )


@dataclass(frozen=True, slots=True)
class ShellCollisionReference:
    collision_id: int
    role: Literal["primary", "sub_collision", "additional_collision"]
    source_field: str
    source_path: str
    list_index: int | None = None
    enabled_by_default: bool | None = None


@dataclass(frozen=True, slots=True)
class ShellEntryRecord:
    source_scope: str
    shell_list_path: str
    entry_index: int
    target_scope: str
    fixed_id: int
    fixed_name: str
    shell_name_hash: int
    ammo_type_name: str
    prefab_path: str
    main_param_path: str
    collision_ids: tuple[int, ...]
    collision_references: tuple[ShellCollisionReference, ...] = ()
    ammo_level: int | None = None
    # Scalar fields of the main param's player mini params
    # (app.cShellminiParamPl*), as (class, field, value).
    mini_param_fields: tuple[tuple[str, str, object], ...] = ()

    def mini_param(self, class_name: str, field_name: str) -> object | None:
        return next(
            (
                value
                for owner, name, value in self.mini_param_fields
                if owner == class_name and name == field_name
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class AmmoNameRecord:
    item_id: str
    item_value: int
    order: int
    name_guid: str
    japanese_name: str
    japanese_name_hash: int


@dataclass(frozen=True, slots=True)
class PfbResourceDocument:
    prefab_path: str
    archive_path: str
    resources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmmoItemMapEvidence:
    action_class: str
    method_name: str
    function_address: str
    call_address: str
    call_target: str
    shell_type_value: int
    shell_type_name: str
    item_value: int
    item_id: str


@dataclass(frozen=True, slots=True)
class UnresolvedAction:
    scope: str
    action_class: str
    action_guide_id: int
    action_internal_name: str
    reason: str


@dataclass(frozen=True, slots=True)
class UnresolvedCoordinate:
    scope: str
    request_set_id: int
    reason: str
    candidate_count: int
    candidate_rcols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnresolvedNameHash:
    scope: str
    key_hash: int
    guide_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class UnresolvedShellEntry:
    source_scope: str
    entry_index: int
    fixed_name: str
    prefab_path: str
    collision_id: int
    reason: str
    candidate_count: int
    rcol_resources: tuple[str, ...]
