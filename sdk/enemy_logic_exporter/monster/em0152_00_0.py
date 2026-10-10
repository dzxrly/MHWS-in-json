"""Offline analysis entry for EM0152_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0152_00_0"
NATIVE_OWNER = "Em0152_00"

# Enchant checks (game 1.42.0.2) over cEm0152_00Extend EnchantTypeArmLeft
# (+0x15c) and EnchantTypeArmRight (+0x170), compared as int (NONE = -1).
# cCheckEnchantAny: left != NONE, or right != NONE. cCheckEnchantType by
# _EditEnchantPartType: ARM_LEFT left == type, ARM_RIGHT right == type,
# ARM_BOTH both == type; other part values return false.
EXTEND = "app.cEm0152_00Extend"
ENCHANT_TYPES = {"NONE": -1, "NORMAL": 0, "FULGURITE": 1, "SOIL": 2}
ENCHANT_FIELDS = {
    "ARM_LEFT": ("extend:<EnchantTypeArmLeft>k__BackingField",),
    "ARM_RIGHT": ("extend:<EnchantTypeArmRight>k__BackingField",),
}
ENCHANT_FIELDS["ARM_BOTH"] = ENCHANT_FIELDS["ARM_LEFT"] + ENCHANT_FIELDS["ARM_RIGHT"]
ENCHANT_ENUMS = {field: ENCHANT_TYPES for field in ENCHANT_FIELDS["ARM_BOTH"]}
ENCHANT_TYPE_EVIDENCE = dict(
    type="app.btable.Em0152_00BTableCommand.cCheckEnchantType",
    method="onExecute1234165",
    address="0x144d29b10",
    end="0x144d29b70",
)


def _enchant_type(argument):
    from ..shared.logic.values import scalar

    part = str(scalar(argument["_EditEnchantPartType"])).split("] ", 1)[-1]
    kind = str(scalar(argument["_EditEnchantType"])).split("] ", 1)[-1]
    if part not in ENCHANT_FIELDS or kind not in ENCHANT_TYPES:
        return None
    return dict(
        spec=(
            "all",
            *((field, "==", ENCHANT_TYPES[kind]) for field in ENCHANT_FIELDS[part]),
        ),
        extend=EXTEND,
        evidence=[ENCHANT_TYPE_EVIDENCE],
        summary=f"{part} 的 EnchantType 为 {kind}",
        enums=ENCHANT_ENUMS,
    )


FIELD_CHECKS = {
    "app.btable.Em0152_00BTableCommand.cCheckEnchantAny": dict(
        spec=(
            "any",
            (ENCHANT_FIELDS["ARM_LEFT"][0], "!=", -1),
            (ENCHANT_FIELDS["ARM_RIGHT"][0], "!=", -1),
        ),
        extend=EXTEND,
        evidence=[
            dict(
                type="app.btable.Em0152_00BTableCommand.cCheckEnchantAny",
                method="onExecute1234151",
                address="0x144745b20",
                end="0x144745b80",
            )
        ],
        summary="EnchantTypeArmLeft 或 EnchantTypeArmRight 不为 NONE",
        enums=ENCHANT_ENUMS,
    ),
    "app.btable.Em0152_00BTableCommand.cCheckEnchantType": _enchant_type,
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    return declared_condition(FIELD_CHECKS, node)


def extract(context):
    """Select this monster's declared tables, imports and native method contexts."""
    return context.extract_enemy(ENEMY_ID, NATIVE_OWNER)


def build_model(
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    *,
    requests_path=None,
    inventory_path=None,
    context=None
):
    """Extract this EM from its real slot/import closure and typed native calls."""
    from ..shared.models.native_recipe import build_monster

    return build_monster(
        ENEMY_ID,
        NATIVE_OWNER,
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        requests_path=requests_path,
        inventory_path=inventory_path,
        context=context,
    )
