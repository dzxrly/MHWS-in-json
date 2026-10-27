from __future__ import annotations

from dataclasses import dataclass

from iced_x86 import Code, Decoder, FlowControl, Mnemonic, OpKind, Register, RegisterExt

from .action_relations import _RelationBuilder
from .models import ActionSeed, Il2CppMethod
from .pe import PeImage
from .request_sets import RequestSetCatalog, canonical_rcol_path
from .track_colliders import WEAPON_TRACK, TrackColliderCatalog

# app.Weapon.activateExternalAttackCollision(UInt32 requestSetId) activates the
# ID on the weapon's own ColliderSwitcher, i.e. the same weapon-prefab RCOLs as
# an AttackCollision_PlWp track.
EXTERNAL_COLLISION_TYPE = "app.Weapon"
EXTERNAL_COLLISION_METHOD = "activateExternalAttackCollision"

_IMMEDIATES = {OpKind.IMMEDIATE32, OpKind.IMMEDIATE8TO32, OpKind.IMMEDIATE32TO64}


@dataclass(frozen=True, slots=True)
class ExternalCollisionHit:
    method: Il2CppMethod
    call_address: int
    request_set_id: int


def find_external_collision_method(
    methods: dict[str, list[Il2CppMethod]],
) -> Il2CppMethod | None:
    candidates = [
        method
        for method in methods.get(EXTERNAL_COLLISION_TYPE, [])
        if method.method_name.startswith(EXTERNAL_COLLISION_METHOD)
    ]
    return candidates[0] if len(candidates) == 1 else None


def scan_external_collisions(
    image: PeImage,
    method: Il2CppMethod,
    target: Il2CppMethod,
    length: int,
) -> list[ExternalCollisionHit]:
    """Calls to the target whose third argument (r8d) is a literal."""
    code = image.read_function_bytes(method.function_address, length)
    hits: list[ExternalCollisionHit] = []
    r8_value: int | None = None
    for instruction in Decoder(64, code, ip=method.function_address):
        if instruction.code == Code.INVALID:
            break
        flow = instruction.flow_control
        if flow == FlowControl.CALL:
            if (
                instruction.near_branch_target == target.function_address
                and r8_value is not None
            ):
                hits.append(ExternalCollisionHit(method, instruction.ip, r8_value))
            r8_value = None  # r8 is volatile across calls
            continue
        if flow != FlowControl.NEXT:
            r8_value = None  # keep the literal within straight-line code
            continue
        if (
            instruction.op_count >= 1
            and instruction.op0_kind == OpKind.REGISTER
            and RegisterExt.full_register(instruction.op0_register) == Register.R8
            and instruction.mnemonic not in {Mnemonic.CMP, Mnemonic.TEST}
        ):
            r8_value = (
                instruction.immediate(1)
                if instruction.mnemonic == Mnemonic.MOV
                and instruction.op_count == 2
                and instruction.op1_kind in _IMMEDIATES
                else None
            )
    return hits


def build_external_collision_relations(
    sources: list[tuple[ActionSeed, list[ExternalCollisionHit]]],
    request_sets: RequestSetCatalog,
    track_colliders: TrackColliderCatalog,
) -> list[dict[str, object]]:
    builders: dict[tuple[object, ...], _RelationBuilder] = {}
    for owner, hits in sources:
        route = track_colliders.route(owner.scope, WEAPON_TRACK)
        if route is None:
            continue
        allowed = set(route.rcols)
        for hit in hits:
            candidates = [
                candidate
                for candidate in request_sets.find(owner.scope, hit.request_set_id)
                if canonical_rcol_path(candidate.rcol) in allowed
            ]
            if len(candidates) != 1:
                continue
            request_set = candidates[0]
            key = (owner.scope, owner.class_name, request_set.target_key)
            builder = builders.get(key)
            if builder is None:
                builder = builders[key] = _RelationBuilder(owner, request_set)
            builder.add_source("static_external_attack_collision")
            builder.add_resolution("weapon_external_collision_literal")
            builder.add_evidence(
                {
                    "actionClass": hit.method.type_name,
                    "methodName": hit.method.method_name,
                    "functionAddress": f"0x{hit.method.function_address:x}",
                    "instructionAddress": f"0x{hit.call_address:x}",
                    "motionSetId": -1,
                    "callee": f"{EXTERNAL_COLLISION_TYPE}.{EXTERNAL_COLLISION_METHOD}",
                    "trackColliderOwner": route.owner,
                }
            )
    relations = []
    for builder in builders.values():
        relation = builder.build()
        relation["conditions"] = [
            {
                "kind": "external_attack_collision",
                "caller": sorted(
                    {
                        f"{item['actionClass']}.{item['methodName']}"
                        for item in relation["evidence"]
                    }
                ),
            }
        ]
        relations.append(relation)
    return relations


def handling_owner(scope: str, type_name: str) -> ActionSeed:
    """Pseudo action for a weapon handling class (no ActionGuide entry)."""
    return ActionSeed(
        scope=scope,
        class_name=type_name,
        guide_id=-1,
        guide_order=2**31 - 1,
        internal_name=type_name.rsplit(".", 1)[-1],
        name_guid="",
        japanese_name="",
        source_files=(),
        guided=False,
    )
