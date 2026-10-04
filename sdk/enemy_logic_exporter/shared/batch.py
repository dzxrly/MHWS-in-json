"""A compact research index is never a production action model."""

import json
from pathlib import Path

from .definitions import EXPECTED_ENEMY_IDS
from .evidence import pack_methods
from .manifest import method_row, discovery_types
from .metadata import Il2cppMetadata
from .native import PE, address_catalog, digest
from ..monster import iter_monsters


def export_native_index(exe, metadata_path, output, version):
    output = Path(output).resolve()
    root = Path(__file__).resolve().parents[3]
    if not output.is_relative_to(root / ".agents"):
        raise ValueError("原生研究索引只能输出到项目 .agents")
    rows, skipped = [], []
    prefixes = [module.NATIVE_OWNER for module in iter_monsters()]
    with Il2cppMetadata(metadata_path) as metadata, PE(exe) as pe:
        aliases = address_catalog(metadata)
        pe.method_starts = sorted(aliases)
        names = set().union(*(discovery_types(metadata, prefix) for prefix in prefixes))
        for name in sorted(names):
            for method, details in metadata.get(name).get("methods", {}).items():
                address = int(details.get("function", "0"), 16)
                end = pe.end(address) if address else 0
                if not 0 < end - address < 200000:
                    skipped.append(
                        dict(
                            type=name,
                            method=method,
                            reason="no native address or unreviewed bound",
                        )
                    )
                    continue
                rows.append(
                    method_row(pe, metadata, aliases, name, method, address, end)
                )
        profile = dict(
            gameVersion=version, exeSha256=digest(exe), metadataSha256=metadata.sha256
        )
    document = pack_methods(
        rows,
        profile,
        enemyIds=list(EXPECTED_ENEMY_IDS),
        skipped=skipped,
        scope="方法定位及字节身份；没有语义控制流，不参加正式图构建",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return document
