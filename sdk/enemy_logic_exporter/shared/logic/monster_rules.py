"""Dispatch to condition kinds and hooks owned by individual monster modules.

Shared code holds no monster constants. A module in ``monster/`` may declare:

- ``RULE_KINDS``: ``{kind: dict(compile=..., evaluate=...)}`` for its own
  verified commands. ``compile(compiler, predicate, values)`` returns the
  player expression; ``evaluate(rule, bound, context, state)`` returns the
  truth over the bound Extend state (see predicates.py).
- ``RULE_SPECS``: curation tuples in the RULE_SPECS format of config.py.
- ``recover_command_effects(row, metadata, pe)``: reviewed native writes.
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
