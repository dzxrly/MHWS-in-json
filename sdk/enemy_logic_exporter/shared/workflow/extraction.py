"""Dispatch real inventory/method scopes and model compilation through each EM."""

from collections import defaultdict
from ...monster import get_monster, iter_monsters
from ..models.builder import build_chain
from ..models.validation import validate_graph


class ExtractionContext:
    def __init__(self, inventory, rows):
        self.profile = inventory["profile"]
        self.monsters = {item["enemyId"]: item for item in inventory["monsters"]}
        if len(self.monsters) != len(inventory["monsters"]):
            raise ValueError("资源发现中出现重复怪物身份")
        self.resources = {item["resource"]: item for item in inventory["resources"]}
        self.methods = defaultdict(list)
        for row in rows:
            self.methods[row["type"]].append(row)

    def extract_enemy(self, enemy_id, native_owner):
        monster = self.monsters[enemy_id]
        closure = monster["tableImportClosure"]
        combat = monster["slots"]["COMBAT"]
        if combat not in closure:
            raise ValueError(f"{enemy_id} 的 Combat 未进入实际导入闭包")
        expected = f"app.{native_owner}_"
        if not self.resources[combat]["exportType"].startswith(expected):
            raise ValueError(f"{enemy_id} 的 Combat 资源归属不匹配")
        methods = [
            row
            for source in closure
            for row in self.methods[self.resources[source]["exportType"]]
        ]
        return dict(
            enemyId=enemy_id,
            extractorModule=get_monster(enemy_id).__name__,
            nativeOwner=native_owner,
            profile=self.profile,
            combatResource=combat,
            slots=monster["slots"],
            resources=closure,
            nativeMethods=methods,
            wholeBattleRecovered=False,
            semanticReviewComplete=False,
        )


class ModelContext:
    def __init__(
        self,
        natives,
        model_path,
        *,
        rules_path=None,
        metadata_path=None,
        model=None,
        resources=None,
    ):
        self.natives = natives
        self.model_path = model_path
        self.rules_path = rules_path
        self.metadata_path = metadata_path
        self.model = model
        self.resources = resources

    def extract_enemy(self, enemy_id, native_owner):
        graph = build_chain(
            self.natives,
            self.model_path,
            rules_path=self.rules_path,
            metadata_path=self.metadata_path,
            model=self.model,
            resources=self.resources,
        )
        if graph["enemyId"] != enemy_id:
            raise ValueError("怪物模块与输入模型身份不匹配，不能复用其他怪物的逻辑")
        graph["artifactKind"] = "extracted_battle_graph"
        graph["extractorModule"] = get_monster(enemy_id).__name__
        graph.setdefault("enemyName", enemy_id)
        graph.setdefault("logicStatus", "recovered_with_boundaries")
        validate_graph(graph)
        return graph


def extract_inventory(inventory, rows):
    context = ExtractionContext(inventory, rows)
    if set(context.monsters) != {module.ENEMY_ID for module in iter_monsters()}:
        raise ValueError("发现的怪物范围与独立分析模块不匹配")
    return [module.extract(context) for module in iter_monsters()]


def extract_model(
    enemy_id,
    natives,
    model_path=None,
    *,
    rules_path=None,
    metadata_path=None,
    model=None,
    resources=None,
):
    return get_monster(enemy_id).extract(
        ModelContext(
            natives,
            model_path,
            rules_path=rules_path,
            metadata_path=metadata_path,
            model=model,
            resources=resources,
        )
    )
