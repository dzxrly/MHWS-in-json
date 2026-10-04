"""Bind native block evidence to action sites without rendering HTML."""

from collections import defaultdict


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
