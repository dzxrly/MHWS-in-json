"""Resource facts for every large-enemy ID, without inventing native control flow."""

from collections import defaultdict
from pathlib import Path
import re

from config import NATIVES_DIR, SUPPORT_FILES
from src.shared.source.user3 import load_user3_table

from .resources import typed

CATALOG_TYPE = "enemy_battle_resource_catalog"


def enemies(natives=NATIVES_DIR, text_db=None):
    rows = load_user3_table(Path(natives) / SUPPORT_FILES["enemy"])
    result = []
    seen = set()
    for row in rows:
        enemy_id = row.get("enemyId", "")
        match = re.fullmatch(r"EM(\d{4})_(\d{2})_\d+", enemy_id)
        if not match or int(match[1]) >= 1000:
            continue
        if enemy_id in seen:
            raise ValueError(f"EnemyData 怪物标识重复：{enemy_id}")
        seen.add(enemy_id)
        result.append(
            dict(
                enemyId=enemy_id,
                enemyName=(text_db.get(row.get("EnemyName", "")) if text_db else "")
                or enemy_id,
                objectKind="training" if match[1] == "0165" else "large_monster",
                directory=f"STM/GameDesign/Enemy/Em{match[1]}/{match[2]}/BTable",
            )
        )
    if not result:
        raise ValueError("EnemyData 中没有大型怪物标识")
    return tuple(sorted(result, key=lambda item: item["enemyId"]))


def bundle_names(natives=NATIVES_DIR, model_ids=()):
    names = ["enemy_battle_logic/index.json"]
    for enemy in enemies(natives):
        names.append(f'enemy_battle_logic/{enemy["enemyId"]}.json')
        if enemy["enemyId"] in model_ids:
            names.append(f'enemy_battle_logic/{enemy["enemyId"]}.html')
    return tuple(names)


def resource_catalog(enemy, resources, registry):
    tables = []
    diagnostics = []
    action_definitions = {}
    resources.accessed.clear()
    prefix = enemy["directory"].casefold() + "/"
    paths = sorted(
        path for key, path in resources.paths.items() if key.startswith(prefix)
    )
    for path in paths:
        relative = path.relative_to(resources.root).as_posix()
        body = resources.read(relative)
        if "_CommandArgArray" not in body:
            continue
        try:
            factories = resources.factories(body)
        except (KeyError, ValueError, FileNotFoundError) as error:
            factories = []
            diagnostics.append(dict(source=relative, reason=str(error)))
        commands = defaultdict(set)
        for factory in factories:
            if factory.get("_OrderType"):
                commands[factory.get("_ArgumentType")].add(factory["_OrderType"])
        arguments = []
        for slot, wrapper in enumerate(body["_CommandArgArray"]):
            argument_type, argument = typed(wrapper)
            command_types = sorted(commands[argument_type])
            record = dict(
                slot=slot,
                argumentType=argument_type,
                commandTypes=command_types,
                argument=argument,
            )
            if len(command_types) == 1:
                record["predicate"] = registry.bind(
                    command_types[0], argument_type, argument
                )
            if argument_type == "app.btable.EmCommonCommand.cSelectActionArg":
                try:
                    action = resources.action(body, argument)
                    definition_id = (
                        action["parameterAsset"] + "#" + action["parameterBodyPointer"]
                    )
                    action_definitions[definition_id] = dict(
                        parameterType=action["parameterType"],
                        parameters=action["parameters"],
                    )
                    record["action"] = {
                        key: value
                        for key, value in action.items()
                        if key not in ("parameters", "parameterInfo")
                    }
                    record["action"]["definitionRef"] = definition_id
                except (KeyError, ValueError, FileNotFoundError) as error:
                    record["actionBinding"] = dict(
                        status="unresolved", reason=str(error)
                    )
            arguments.append(record)
        tables.append(
            dict(
                source=relative,
                tableGuid=body.get("_ThisGuid"),
                exportType=body.get("_ExportBTableType"),
                tableDefinitions=body.get("_Tables", []),
                imports=body.get("_ImportBTableList", []),
                arguments=arguments,
                controlFlowStatus="not_recovered",
            )
        )
    return dict(
        scope="BTable 资源及参数清单；参数槽位和表定义不代表执行顺序、选招概率或已恢复的控制流。",
        tableCount=len(tables),
        argumentCount=sum(len(table["arguments"]) for table in tables),
        actionBindings=sum(
            "action" in arg for table in tables for arg in table["arguments"]
        ),
        verifiedPredicates=sum(
            arg.get("predicate", {}).get("status") == "verified"
            for table in tables
            for arg in table["arguments"]
        ),
        tables=tables,
        actionDefinitions=action_definitions,
        diagnostics=diagnostics,
        sourceHashes={
            source: resources.hashes[source] for source in sorted(resources.accessed)
        },
    )
