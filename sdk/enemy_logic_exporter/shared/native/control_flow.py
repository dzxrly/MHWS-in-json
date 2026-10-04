"""Export structured Ghidra evidence without claiming it is reviewed semantics."""

from collections import defaultdict


def varnode(value):
    if value is None:
        return None
    address = value.getAddress()
    return dict(
        space=str(address.getAddressSpace().getName()),
        offset=hex(int(value.getOffset())),
        size=int(value.getSize()),
        constant=bool(value.isConstant()),
    )


def high_function_evidence(high_function):
    blocks, calls = [], []
    for block in high_function.getBasicBlocks():
        operations = []
        iterator = block.getIterator()
        while iterator.hasNext():
            operation = iterator.next()
            inputs = [
                varnode(operation.getInput(i)) for i in range(operation.getNumInputs())
            ]
            row = dict(
                address=hex(int(operation.getSeqnum().getTarget().getOffset())),
                order=int(operation.getSeqnum().getTime()),
                opcode=str(operation.getMnemonic()),
                output=varnode(operation.getOutput()),
                inputs=inputs,
            )
            operations.append(row)
            if row["opcode"] in ("CALL", "CALLIND"):
                calls.append(
                    dict(
                        site=row["address"],
                        direct=row["opcode"] == "CALL",
                        target=inputs[0],
                        arguments=inputs[1:],
                    )
                )
        blocks.append(
            dict(
                id=str(block.getIndex()),
                start=hex(int(block.getStart().getOffset())),
                end=hex(int(block.getStop().getOffset())),
                successors=[
                    str(block.getOut(i).getIndex()) for i in range(block.getOutSize())
                ],
                operations=operations,
            )
        )
    return dict(
        format="ghidra_high_pcode",
        blocks=blocks,
        calls=calls,
        status="unreviewed_native_control_flow",
    )


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
