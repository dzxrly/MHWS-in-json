"""Dispatch to condition kinds and hooks owned by individual monster modules.

Shared code holds no monster constants. A module in ``monster/`` may declare:

- ``RULE_KINDS``: ``{kind: dict(compile=..., evaluate=...)}`` for its own
  verified commands. ``compile(compiler, predicate, values)`` returns the
  player expression; ``evaluate(rule, bound, context, state)`` returns the
  truth over the bound Extend state (see predicates.py).
- ``RULE_SPECS``: curation tuples in the RULE_SPECS format of config.py.
- ``recover_command_effects(row, metadata, pe)``: reviewed native writes.
- ``recover_boolean_command_effect(row, metadata, pe)``: a reviewed
  condition and the field writes on its true return path.
- ``recover_target_command_effect(bound, evidence)``: reviewed target writes,
  native return guards and explicit exception boundaries for a bound command.
- ``verify_native_recipes(pe, metadata)``: check a module's native recipes
  against the current methods, bytes, fields and resource-independent constants.
- ``table_history_policy(row)``: opt a reviewed native table into local
  expansion of multiple private intervals at their actual read instructions.
- ``prepare_player_graph(graph, registry)``: checks before the player view.
- ``recover_condition(node, enemy_id, resources)``: reviewed conditions of
  its own commands (not the common prefix); may add ``sceneInput`` or
  ``inputEnums`` ({input key: {enum name: value}}) for the player view.
"""

from functools import lru_cache


@lru_cache(maxsize=1)
def _modules():
    from ...monster import iter_monsters

    return iter_monsters()


@lru_cache(maxsize=1)
def rule_kinds():
    found = {}
    for module in _modules():
        for kind, handler in getattr(module, "RULE_KINDS", {}).items():
            if kind in found:
                raise ValueError(f"专用判断类型被多个怪物模块登记：{kind}")
            found[kind] = handler
    return found


def rule_kind(kind):
    return rule_kinds().get(kind)


def rule_specs():
    return tuple(
        spec for module in _modules() for spec in getattr(module, "RULE_SPECS", ())
    )


def hooks(name):
    return [getattr(module, name) for module in _modules() if hasattr(module, name)]


def target_command_effect(bound, evidence):
    from .target_command_effects import reviewed_target_command_effect

    found = [
        result
        for recover in (
            reviewed_target_command_effect,
            *hooks("recover_target_command_effect"),
        )
        if (result := recover(bound, evidence)) is not None
    ]
    if len(found) > 1:
        raise ValueError("目标更新命令被多个配方登记：" + bound["commandType"])
    return found[0] if found else None
