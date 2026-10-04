"""One offline analysis entry per large monster, including separate variants."""

from importlib import import_module

from ..shared.models.catalog import EXPECTED_ENEMY_IDS

# EM0160_50's declared BTableList uses Em0160_00 Combat and a variant Repel.
DECLARED_COMBAT_OWNERS = {"EM0160_50_0": "Em0160_00"}


def get_monster(enemy_id):
    if enemy_id not in EXPECTED_ENEMY_IDS:
        raise ValueError(f"不支持的完整大型怪物 ID：{enemy_id}")
    module = import_module(f"{__name__}.{enemy_id.lower()}")
    expected_owner = DECLARED_COMBAT_OWNERS.get(enemy_id, "Em" + enemy_id[2:9])
    if module.ENEMY_ID != enemy_id or module.NATIVE_OWNER != expected_owner:
        raise ValueError(f"怪物模块的身份与注册名单冲突：{enemy_id}")
    return module


def iter_monsters():
    return tuple(get_monster(enemy_id) for enemy_id in EXPECTED_ENEMY_IDS)
