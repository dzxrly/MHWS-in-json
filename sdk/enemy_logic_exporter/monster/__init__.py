"""One offline analysis entry per large monster, including separate variants."""

from importlib import import_module

from ..shared.models.catalog import EXPECTED_ENEMY_IDS, NATIVE_OWNERS


def get_monster(enemy_id):
    if enemy_id not in EXPECTED_ENEMY_IDS:
        raise ValueError(f"不支持的完整大型怪物 ID：{enemy_id}（名单见 data/roster.v1.json）")
    try:
        module = import_module(f"{__name__}.{enemy_id.lower()}")
    except ModuleNotFoundError as error:
        raise ValueError(
            f"名单中的 {enemy_id} 还没有入口模块，请运行 new-monster --enemy {enemy_id}"
        ) from error
    # The owner is the declared Combat resource's owner, e.g. EM0160_50 reuses
    # Em0160_00 Combat; the roster records it from the actual BTableList.
    if module.ENEMY_ID != enemy_id or module.NATIVE_OWNER != NATIVE_OWNERS[enemy_id]:
        raise ValueError(f"怪物模块的身份与注册名单冲突：{enemy_id}")
    return module


def iter_monsters():
    return tuple(get_monster(enemy_id) for enemy_id in EXPECTED_ENEMY_IDS)
