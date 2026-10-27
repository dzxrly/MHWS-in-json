"""Read PE64 function ranges and IL2CPP address aliases without executing code."""

import bisect
import hashlib
import mmap
from pathlib import Path
import re
import struct

SECTION_WRITABLE = 0x80000000
SECTION_EXECUTABLE = 0x20000000
# These directories jointly locate the reviewed constants section in the
# supplied MHWS memory dumps. Section names are randomized between builds.
# Ordinary mutable sections never inherit this exception. The formula reader
# independently rejects addresses at/after its reviewed runtime-data boundary.
CONSTANT_DATA_DIRECTORIES = (9, 10, 13)  # TLS, load config, delay imports


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
            # Section characteristics, for telling constants from writable data.
            self.section_flags = [
                struct.unpack_from("<I", self.data, opt + optsize + i * 40 + 36)[0]
                for i in range(count)
            ]
            self.section_names = [
                self.data[opt + optsize + i * 40 : opt + optsize + i * 40 + 8].rstrip(
                    b"\0"
                )
                for i in range(count)
            ]
            directory_sections = []
            directory_count = struct.unpack_from("<I", self.data, opt + 108)[0]
            for directory in CONSTANT_DATA_DIRECTORIES:
                if directory >= directory_count or 112 + (directory + 1) * 8 > optsize:
                    directory_sections.append(None)
                    continue
                rva, size = struct.unpack_from(
                    "<II", self.data, opt + 112 + directory * 8
                )
                matches = [
                    index
                    for index, (virtual_size, start, raw_size, _) in enumerate(
                        self.sections
                    )
                    if rva
                    and size
                    and start <= rva
                    and rva + size <= start + min(virtual_size, raw_size)
                ]
                directory_sections.append(matches[0] if len(matches) == 1 else None)
            self.constant_sections = set()
            if len(set(directory_sections)) == 1 and directory_sections[0] is not None:
                index = directory_sections[0]
                if not self.section_flags[index] & SECTION_EXECUTABLE:
                    self.constant_sections.add(index)
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
            self._leaf_end_cache = {}
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

    def contains(self, address):
        """True when address lies in a section's virtual range.

        Includes the zero-filled tail past a section's raw data, where read()
        returns no bytes.
        """
        rva = address - self.base
        return any(
            virtual_address <= rva < virtual_address + max(virtual_size, raw_size)
            for virtual_size, virtual_address, raw_size, _ in self.sections
        )

    def read_only(self, address, size):
        """True when [address, address+size) lies in one constant section."""
        rva = address - self.base
        for index, ((virtual_size, virtual_address, _, _), flags) in enumerate(
            zip(self.sections, self.section_flags)
        ):
            if virtual_address <= rva and rva + size <= virtual_address + virtual_size:
                return not flags & SECTION_WRITABLE or index in self.constant_sections
        return False

    def end(self, address):
        index = bisect.bisect_right(self.starts, address) - 1
        has_unwind = (
            index >= 0
            and self.functions[index][0] <= address < self.functions[index][1]
        )
        if has_unwind:
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
        if not has_unwind:
            key = (address, end)
            if key not in self._leaf_end_cache:
                self._leaf_end_cache[key] = self._closed_leaf_end(address, end)
            end = self._leaf_end_cache[key] or end
        return end

    def _closed_leaf_end(self, start, limit):
        """Close all direct paths; unresolved indirect flow keeps the old bound.

        Only unwind-less entry points use this. An explicit evidence row still
        keeps its own original range even when its method ends sooner.
        """
        from capstone import (
            Cs,
            CS_ARCH_X86,
            CS_MODE_64,
            CS_GRP_JUMP,
            CS_GRP_RET,
            CS_OP_IMM,
        )

        decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        decoder.detail = True
        pending, visited, owners = [start], set(), {}
        end = start
        while pending:
            address = pending.pop()
            if address in visited:
                continue
            if not start <= address < limit or address in owners:
                return None
            instruction = next(
                decoder.disasm(
                    self.read(address, min(15, limit - address)), address, 1
                ),
                None,
            )
            if instruction is None:
                return None
            following = address + instruction.size
            if any(byte in owners for byte in range(address, following)):
                return None
            owners.update((byte, address) for byte in range(address, following))
            visited.add(address)
            end = max(end, following)
            if instruction.group(CS_GRP_RET) or instruction.mnemonic in ("int3", "ud2"):
                continue
            if instruction.group(CS_GRP_JUMP):
                if (
                    not instruction.operands
                    or instruction.operands[0].type != CS_OP_IMM
                ):
                    return None
                target = instruction.operands[0].imm
                if start <= target < limit:
                    pending.append(target)
                elif instruction.mnemonic != "jmp":
                    # A conditional edge outside the provisional range needs review.
                    return None
                if instruction.mnemonic == "jmp":
                    continue
            pending.append(following)
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
    # Newer REFramework dumps write "flags" before "function".
    pattern = re.compile(
        rb'^ {12}"([^"\r\n]+)": \{\s+(?:"flags": "[^"\r\n]*",\s+)?"function": "([0-9a-fA-F]+)"',
        re.M,
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
            # Rows that carry a digest of the analysed bytes are checked too.
            if len(body) != size or (
                "nativeSha256" in row
                and hashlib.sha256(body).hexdigest() != row["nativeSha256"]
            ):
                raise ValueError(
                    f"Native evidence mismatch: {row['type']}.{row['method']}"
                )
            if require_completed and (not row.get("completed") or not row.get("code")):
                raise ValueError(f"Incomplete decompilation: {row['method']}")
