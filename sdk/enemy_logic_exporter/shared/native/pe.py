"""Read PE64 function ranges and IL2CPP address aliases without executing code."""

import bisect
import hashlib
import mmap
from pathlib import Path
import re
import struct


class PE:
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open("rb")
        self.data = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            pe = struct.unpack_from("<I", self.data, 0x3C)[0]
            if self.data[:2] != b"MZ" or self.data[pe : pe + 4] != b"PE\0\0":
                raise ValueError("Input is not a PE executable")
            count = struct.unpack_from("<H", self.data, pe + 6)[0]
            optsize = struct.unpack_from("<H", self.data, pe + 20)[0]
            opt = pe + 24
            if struct.unpack_from("<H", self.data, opt)[0] != 0x20B:
                raise ValueError("Only PE64 is supported")
            self.base = struct.unpack_from("<Q", self.data, opt + 24)[0]
            self.sections = [
                struct.unpack_from("<IIII", self.data, opt + optsize + i * 40 + 8)
                for i in range(count)
            ]
            rva, size = struct.unpack_from("<II", self.data, opt + 112 + 3 * 8)
            self.functions = sorted(
                (self.base + start, self.base + end)
                for start, end, _ in struct.iter_unpack(
                    "<III", self.read(self.base + rva, size)
                )
                if start and end > start
            )
            self.starts = [start for start, _ in self.functions]
            self.method_starts = []
        except Exception:
            self.close()
            raise

    def read(self, address, size):
        rva = address - self.base
        for virtual_size, virtual_address, raw_size, raw in self.sections:
            if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
                offset = rva - virtual_address
                if offset >= raw_size:
                    break
                return self.data[
                    raw + offset : raw + offset + min(size, raw_size - offset)
                ]
        return b""

    def end(self, address):
        index = bisect.bisect_right(self.starts, address) - 1
        if (
            index >= 0
            and self.functions[index][0] <= address < self.functions[index][1]
        ):
            end = self.functions[index][1]
        else:
            # Unwind-less leaf functions require manual review of this provisional bound.
            end = min(
                (
                    self.starts[index + 1]
                    if index + 1 < len(self.starts)
                    else address + 2048
                ),
                address + 2048,
            )
        following = bisect.bisect_right(self.method_starts, address)
        if following < len(self.method_starts):
            end = min(end, self.method_starts[following])
        return end

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.data.close()
        self.file.close()


def address_catalog(metadata):
    names = list(metadata._objects or metadata._offsets)
    if metadata._objects:
        addresses = {}
        for name in names:
            for method, info in metadata.get(name).get("methods", {}).items():
                address = int(info.get("function", "0"), 16)
                if address:
                    addresses.setdefault(address, []).append((name, method))
        return addresses
    starts = list(metadata._offsets.values())
    addresses = {}
    pattern = re.compile(
        rb'^ {12}"([^"\r\n]+)": \{\s+"function": "([0-9a-fA-F]+)"', re.M
    )
    for match in pattern.finditer(metadata._mapped):
        name = names[bisect.bisect_right(starts, match.start()) - 1]
        address = int(match[2], 16)
        if address:
            addresses.setdefault(address, []).append((name, match[1].decode()))
    if not addresses:
        raise ValueError(
            "Large metadata method formatting changed; update address_catalog"
        )
    return addresses


def verify_rows(exe, rows, *, require_completed=False):
    if not rows:
        raise ValueError("No native evidence rows")
    with PE(exe) as pe:
        for row in rows:
            start, end = int(row["address"], 16), int(row["end"], 16)
            size = end - start
            body = pe.read(start, size) if 0 < size <= 0x200000 else b""
            # The active profile pins the EXE; rows from older caches may
            # still carry a byte digest, which is then checked as well.
            if len(body) != size or (
                "nativeSha256" in row
                and hashlib.sha256(body).hexdigest() != row["nativeSha256"]
            ):
                raise ValueError(
                    f"Native evidence mismatch: {row['type']}.{row['method']}"
                )
            if require_completed and (not row.get("completed") or not row.get("code")):
                raise ValueError(f"Incomplete decompilation: {row['method']}")
