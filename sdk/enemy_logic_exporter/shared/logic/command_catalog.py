"""Keep command implementations and narrowly recovered leaf rules in research."""

import json
from pathlib import Path
from ..native.evidence import method_rows, digest
from ..native.metadata import Il2cppMetadata
from ..workflow.semantic_recovery import _artifact
from .commands import recover_leaf, recover_writes
from .monster_rules import hooks
from .static_pools import native_initializer_pools
from ..native.pe import PE, verify_rows
import hashlib
from ..config import in_agents

def export_commands(helper_index, metadata, output, *, exe, inventory=None):
    output = Path(output).resolve()
    if not in_agents(output):
        raise ValueError("命令原生证据只允许写入 .agents")
    index_path = Path(helper_index)
    index = json.loads(index_path.read_text(encoding="utf8"))
    if digest(exe) != index["profile"]["exeSha256"]:
        raise ValueError("命令 EXE 版本冲突")
    from ..config import SUPPORTED_PROFILE

    if index["profile"] != SUPPORTED_PROFILE:
        raise ValueError("初始化地址配方尚未审核此版本")
    verify_rows(exe, method_rows(index))
    commands, leaves, initializers, schedulers = {}, [], [], []
    with Il2cppMetadata(Path(metadata)) as dump, PE(exe) as pe:
        if dump.sha256 != index["profile"]["metadataSha256"]:
            raise ValueError("命令元数据版本冲突")
        for row in method_rows(index):
            data = _artifact(index_path, index, row)
            evidence = {k: row[k] for k in ("type", "method", "address", "end")}
            record = dict(
                **evidence,
                parameters=row.get("parameters", []),
                code=data["code"].replace("\r", ""),
                semanticStatus="implementation_available_unreviewed",
            )
            record["rangeBoundaryWarnings"] = [
                b["id"]
                for b in data["controlFlow"]["blocks"]
                if not int(row["address"], 16)
                <= int(b["start"], 16)
                <= int(b["end"], 16)
                < int(row["end"], 16)
            ]
            record["fields"] = dump.fields(row["type"])
            if row["method"].startswith("onExecute"):
                leaf = (
                    recover_leaf(row, record["code"], dump)
                    if not record["rangeBoundaryWarnings"]
                    else None
                )
                if leaf:
                    record["recoveredLeaf"] = leaf
                    leaves.append(leaf)
                record["recoveredWrites"] = (
                    recover_writes(row, record["code"], dump)
                    if not record["rangeBoundaryWarnings"]
                    else []
                )
                for recover in hooks("recover_command_effects"):
                    record["recoveredWrites"].extend(recover(row, dump, pe))
                commands.setdefault(row["type"], []).append(record)
            elif row["method"].startswith(".cctor"):
                start, end = int(row["address"], 16), int(row["end"], 16)
                record["staticPools"] = native_initializer_pools(
                    pe.read(start, end - start), start, record
                )
                initializers.append(record)
            else:
                schedulers.append(record)
        inherited = {}
        unresolved = []
        if inventory:
            used = {
                t
                for c in inventory["commandFactoryTypeCatalog"].values()
                for t in c
                if t
            }
            for name in sorted(used - commands.keys()):
                chain = []
                current = name
                while current and current not in chain:
                    chain.append(current)
                    current = (dump.get(current) or {}).get("parent")
                    if current in commands:
                        inherited[name] = dict(
                            implementationType=current, parentChain=chain + [current]
                        )
                        break
                else:
                    unresolved.append(name)
        for leaf in leaves:
            leaf["enumType"], leaf["enumValues"] = dump.enum(leaf["contextFieldType"])
    output.mkdir(parents=True, exist_ok=True)
    result = dict(
        profile=index["profile"],
        commands=commands,
        leafComparisons=leaves,
        initializers=initializers,
        schedulers=schedulers,
        inheritedCommands=inherited,
        unresolvedCommands=unresolved,
        semanticReviewComplete=False,
    )
    (output / "command-catalog.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf8"
    )
    refs = {}
    (output / "implementations").mkdir(exist_ok=True)
    for name, records in commands.items():
        identity = hashlib.sha256(name.encode()).hexdigest()[:24]
        file = output / "implementations" / f"{identity}.json"
        file.write_text(
            json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf8",
        )
        refs[name] = "implementations/" + file.name
    for name, binding in inherited.items():
        refs[name] = dict(binding)
    (output / "command-implementation-refs.json").write_text(
        json.dumps(refs, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf8",
    )
    print(
        "COMMAND CATALOG",
        len(commands),
        "TYPES",
        len(leaves),
        "LEAF RULES",
        len(initializers),
        "INITIALIZERS",
        flush=True,
    )
    for leaf in leaves:
        print(
            leaf["commandType"],
            leaf["contextType"] + "." + leaf["contextField"],
            leaf["operator"],
            leaf["argumentField"] or leaf["constant"],
            flush=True,
        )
    return result
