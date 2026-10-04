"""Render actual native basic-block flow for every discovered BTable context.

This is an offline research view. It is never a formal semantic action model.
"""

from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil

from .evidence import evidence_key, method_rows


def compact_flow(data, row, events, action_catalog, aliases):
    blocks = data["controlFlow"]["blocks"]
    ids = {b["id"] for b in blocks}
    if len(ids) != len(blocks) or any(
        target not in ids for block in blocks for target in block["successors"]
    ):
        raise ValueError("原生基本块身份重复或后继指向缺失块")
    compact, attached = [], set()
    locations = defaultdict(list)
    for event in events:
        site = int(event["address"], 16)
        exact = [
            b
            for b in blocks
            if any(int(o["address"], 16) == site for o in b["operations"])
        ]
        candidates = exact or [
            b for b in blocks if int(b["start"], 16) <= site <= int(b["end"], 16)
        ]
        if len(candidates) == 1:
            locations[candidates[0]["id"]].append(event)
            attached.add(event["address"])
    for block in blocks:
        calls = []
        for operation in block["operations"]:
            if operation["opcode"] not in {"CALL", "CALLIND"}:
                continue
            target = operation["inputs"][0]
            direct = operation["opcode"] == "CALL"
            address = target["offset"] if direct else ""
            calls.append(
                dict(
                    site=operation["address"],
                    direct=direct,
                    address=address,
                    targets=aliases.get(address, []),
                )
            )
        compact.append(
            dict(
                id=block["id"],
                start=block["start"],
                end=block["end"],
                successors=block["successors"],
                calls=calls,
                actions=[
                    dict(
                        site=e["address"],
                        argumentIndex=e["argumentIndex"],
                        commandIndex=e["commandIndex"],
                        **action_catalog[e["actionRef"]],
                    )
                    for e in locations[block["id"]]
                ],
                terminalOperations=[
                    o["opcode"]
                    for o in block["operations"]
                    if o["opcode"] in {"RETURN", "BRANCH", "CBRANCH", "BRANCHIND"}
                ],
            )
        )
    return dict(
        **{
            k: row[k]
            for k in (
                "type",
                "method",
                "address",
                "end",
                "nativeSha256",
                "addressAliases",
            )
        },
        blocks=compact,
        code=data["code"].replace("\r", ""),
        entryBlock=next(
            (b["id"] for b in blocks if b["start"] == row["address"]), None
        ),
        unplacedActionSites=[
            e["address"] for e in events if e["address"] not in attached
        ],
        rangeBoundaryWarnings=[
            b["id"]
            for b in blocks
            if not int(row["address"], 16) <= int(b["start"], 16) < int(row["end"], 16)
        ],
        status="unreviewed_native_control_flow",
    )


def export_native_views(native_index, inventory, requests, output):
    output = Path(output).resolve()
    root = Path(__file__).resolve().parents[2]
    if not output.is_relative_to(root / ".agents"):
        raise ValueError("原生控制流研究页面只允许输出到 .agents")
    index_path = Path(native_index)
    index = json.loads(index_path.read_text(encoding="utf8"))
    if (
        index["profile"] != inventory["profile"]
        or index["profile"] != requests["profile"]
    ):
        raise ValueError("原生流程图的索引、资源、请求来源不一致")
    rows = method_rows(index)
    by_type = {r["exportType"]: r for r in inventory["resources"]}
    selected = [r for r in rows if r["type"] in by_type]
    resource_ids = {
        p: hashlib.sha256(p.encode()).hexdigest()[:24]
        for p in (r["resource"] for r in inventory["resources"])
    }
    aliases = defaultdict(list)
    grouped = defaultdict(list)
    for row in selected:
        source = by_type[row["type"]]["resource"]
        identity = resource_ids[source]
        grouped[source].append(row)
        aliases[row["address"]].append(
            dict(resourceId=identity, type=row["type"], method=row["method"])
        )
    events = defaultdict(list)
    for event in requests["actionRequestBindings"]:
        events[(event["type"], event["method"])].append(event)
    output.mkdir(parents=True, exist_ok=True)
    (output / "tables").mkdir(exist_ok=True)
    shutil.copyfile(
        root / "src/processed_data/enemy_battle_logic/vendor/elkjs/elk.bundled.js",
        output / "elk.bundled.js",
    )
    shutil.copyfile(
        root / "src/processed_data/enemy_battle_logic/vendor/elkjs/LICENSE.md",
        output / "ELK-LICENSE.md",
    )
    (output / "native-viewer.js").write_text(
        Path(__file__).with_name("native_viewer.js").read_text(encoding="utf8"),
        encoding="utf8",
    )
    catalog = []
    counts = dict(
        methodContexts=0,
        basicBlockContexts=0,
        successorEdges=0,
        actionSiteAnnotations=0,
        unplacedActionSites=0,
        rangeBoundaryWarningContexts=0,
    )
    # Read one compressed body at a time. Contexts sharing a body remain separate.
    for resource in inventory["resources"]:
        source = resource["resource"]
        methods = []
        for row in grouped[source]:
            artifact = index["nativeBodyArtifacts"][evidence_key(row)]
            path = index_path.parent / artifact["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError("原生流程图证据摘要不匹配")
            with gzip.open(path, "rt", encoding="utf8") as stream:
                data = json.load(stream)
            if not data["completed"]:
                raise ValueError("原生流程图缺少完成的证据")
            flow = compact_flow(
                data,
                row,
                events[(row["type"], row["method"])],
                requests["actionCatalog"],
                aliases,
            )
            methods.append(flow)
            counts["methodContexts"] += 1
            counts["basicBlockContexts"] += len(flow["blocks"])
            counts["successorEdges"] += sum(
                len(b["successors"]) for b in flow["blocks"]
            )
            counts["actionSiteAnnotations"] += sum(
                len(b["actions"]) for b in flow["blocks"]
            )
            counts["unplacedActionSites"] += len(flow["unplacedActionSites"])
            counts["rangeBoundaryWarningContexts"] += bool(
                flow["rangeBoundaryWarnings"]
            )
        identity = resource_ids[source]
        content = (
            json.dumps(
                dict(resource=resource, methods=methods),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            .replace("<", "\\u003c")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )
        (output / "tables" / (identity + ".js")).write_text(
            "window.NATIVE_TABLES[" + json.dumps(identity) + "]=" + content + ";\n",
            encoding="utf8",
        )
        catalog.append(
            dict(
                id=identity,
                resource=source,
                type=resource["exportType"],
                methodContexts=len(methods),
            )
        )
    meta = dict(
        profile=index["profile"],
        monsters=inventory["monsters"],
        resources=catalog,
        counts=counts,
    )
    template = Path(__file__).with_name("native_viewer.html").read_text(encoding="utf8")
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )
    (output / "index.html").write_text(
        template.replace("__DATA__", payload), encoding="utf8"
    )
    receipt = dict(
        monsters=len(meta["monsters"]),
        resources=len(catalog),
        **counts,
        semanticReviewCompleted=False,
        totalBytes=sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
        largestFileBytes=max(
            p.stat().st_size for p in output.rglob("*") if p.is_file()
        ),
    )
    (output / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print("NATIVE FLOW VIEWS", json.dumps(receipt), flush=True)
    return receipt
