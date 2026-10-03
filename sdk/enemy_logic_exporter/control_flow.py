"""Export structured Ghidra evidence without claiming it is reviewed semantics."""


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
