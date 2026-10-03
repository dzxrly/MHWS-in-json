"""Version-specific constant recovery, not automatic recovery of selection semantics."""

import re


def recover(rows):
    cc = next(row for row in rows if row["method"].startswith(".cctor1081024"))
    text = cc["code"].replace("\r", "")
    pools, previous = {}, 0
    for match in re.finditer(r"FUN_143801f50\((0x[0-9a-f]+),", text):
        pairs = re.findall(
            r"(?:func_0x000143928820|mhws_c49d22bf7e7e9cbe)\s*\(.*?,.*?,\s*(0x[0-9a-f]+|\d+),\s*(0x[0-9a-f]+|\d+)\s*\)\s*;",
            text[previous : match.start()],
            re.DOTALL,
        )
        pools[match[1]] = [{"hash": int(a, 0), "weight": int(b, 0)} for a, b in pairs]
        previous = match.end()
    if len(pools) != 97 or sum(len(pool) for pool in pools.values()) != 320:
        raise ValueError(
            "Constant layout changed; review the current native initializer"
        )
    return {
        "pools": pools,
        "cctorEvidence": {
            key: cc[key] for key in ("type", "method", "address", "end", "nativeSha256")
        },
    }
