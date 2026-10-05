"""The large-monster roster as data, derived from EnemyData and BTableList.

A game update that adds a monster or a variant only needs ``roster`` to be
re-run and ``new-monster`` to scaffold its entry module; no code list changes.
"""

import json
import re

from ..config import (  # noqa: F401  (ROSTER_PATH is re-exported for the CLI)
    EXCLUDED_ENEMY_IDS,
    LARGE_ENEMY_MAX_BASE,
    MONSTER_MODULE_DIR,
    ROSTER_PATH,
    SUPPORTED_PROFILE,
)

COMBAT_RESOURCE = re.compile(r"(Em\d{4}_\d{2})_BTable_Combat\.user", re.I)
ENEMY_DATA = "STM/GameDesign/Common/Enemy/EnemyData.user.3.json"


def btable_list_path(enemy_id):
    species, variant = enemy_id[2:6], enemy_id[7:9]
    return f"STM/GameDesign/Enemy/Em{species}/{variant}/BTable/Em{species}_{variant}_BTableList.user.3.json"


def build_roster(resources):
    from ..resources.reader import typed

    enemies = []
    for wrapper in resources.read(ENEMY_DATA)["_Values"]:
        enemy_id = typed(wrapper)[1]["_enemyId"].split()[-1]
        match = re.fullmatch(r"EM(\d{4})_\d{2}_\d+", enemy_id)
        if not match or int(match[1]) >= LARGE_ENEMY_MAX_BASE:
            continue
        if enemy_id in EXCLUDED_ENEMY_IDS:
            continue
        table = typed(resources.read(btable_list_path(enemy_id))["_Table_COMBAT"])[1]
        owner = COMBAT_RESOURCE.search(table.get("path", ""))
        if owner is None:
            raise ValueError("BTableList 没有可识别的 Combat 资源：" + enemy_id)
        enemies.append(
            dict(
                enemyId=enemy_id,
                nativeOwner=owner[1][:2].capitalize() + owner[1][2:],
                combatResource=table["path"],
            )
        )
    identities = [e["enemyId"] for e in enemies]
    if len(identities) != len(set(identities)):
        raise ValueError("EnemyData 中的大型怪物身份重复")
    return dict(
        schemaVersion=1,
        sourceProfile=dict(SUPPORTED_PROFILE),
        scope=f"EnemyData 中基础编号小于 {LARGE_ENEMY_MAX_BASE} 的完整 ID，排除 {', '.join(EXCLUDED_ENEMY_IDS)}",
        excludedEnemyIds=list(EXCLUDED_ENEMY_IDS),
        enemies=sorted(enemies, key=lambda e: e["enemyId"]),
    )


def load_roster(path=ROSTER_PATH):
    return json.loads(path.read_text(encoding="utf-8"))


def roster_changes(old, new):
    before = {e["enemyId"]: e for e in old["enemies"]}
    after = {e["enemyId"]: e for e in new["enemies"]}
    return dict(
        added=sorted(set(after) - set(before)),
        removed=sorted(set(before) - set(after)),
        ownerChanged=sorted(
            k for k in set(before) & set(after) if before[k] != after[k]
        ),
        missingModules=sorted(
            k for k in after if not (MONSTER_MODULE_DIR / f"{k.lower()}.py").exists()
        ),
    )


MODULE_TEMPLATE = '''"""Offline analysis entry for {enemy_id}; no inferred or placeholder graph."""

ENEMY_ID = "{enemy_id}"
NATIVE_OWNER = "{owner}"


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
'''


def scaffold_monster(enemy_id, roster=None):
    """Write monster/<id>.py for a roster entry; never overwrite a recipe."""
    roster = roster or load_roster()
    entry = next((e for e in roster["enemies"] if e["enemyId"] == enemy_id), None)
    if entry is None:
        raise ValueError("名单中没有该怪物，请先运行 roster：" + enemy_id)
    path = MONSTER_MODULE_DIR / f"{enemy_id.lower()}.py"
    if path.exists():
        raise ValueError("怪物入口已存在，不覆盖已有配方：" + path.name)
    path.write_text(
        MODULE_TEMPLATE.format(enemy_id=enemy_id, owner=entry["nativeOwner"]),
        encoding="utf-8",
    )
    return path


PUBLISHED_ROSTER_NAME = "roster.json"


def published_roster(roster=None):
    """The web side's copy: identities only, no SDK paths."""
    roster = roster or load_roster()
    return dict(
        schemaVersion=1,
        enemyIds=[e["enemyId"] for e in roster["enemies"]],
        excludedEnemyIds=list(roster["excludedEnemyIds"]),
    )
