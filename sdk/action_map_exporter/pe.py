from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import BinaryIO


@dataclass(frozen=True, slots=True)
class _SectionRange:
    name: str
    virtual_address: int
    virtual_span: int
    raw_address: int
    raw_size: int


class PeImage:
    """Minimal, read-only PE image mapper used by the static scanners."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._stream: BinaryIO = self.path.open("rb")
        try:
            self.image_base, self._sections = self._read_headers()
        except Exception:
            self._stream.close()
            raise

    def __enter__(self) -> "PeImage":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._stream.close()

    def read_function_bytes(self, virtual_address: int, requested_length: int) -> bytes:
        if requested_length <= 0:
            return b""
        rva = (
            virtual_address - self.image_base
            if virtual_address >= self.image_base
            else virtual_address
        )
        if not 0 <= rva <= 0xFFFFFFFF:
            return b""
        section = next(
            (
                item
                for item in self._sections
                if item.virtual_address
                <= rva
                < item.virtual_address + item.virtual_span
            ),
            None,
        )
        if section is None:
            return b""
        section_offset = rva - section.virtual_address
        if section_offset >= section.raw_size:
            return b""
        length = min(requested_length, section.raw_size - section_offset)
        self._stream.seek(section.raw_address + section_offset)
        data = self._stream.read(length)
        if len(data) != length:
            raise EOFError(
                f"PE 段读取不完整: {self.path} "
                f"(expected={length}, actual={len(data)})"
            )
        return data

    def _read_headers(self) -> tuple[int, tuple[_SectionRange, ...]]:
        self._stream.seek(0)
        dos = self._stream.read(64)
        if len(dos) < 64 or dos[:2] != b"MZ":
            raise ValueError(f"不是有效的 PE 文件: {self.path}")
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        self._stream.seek(pe_offset)
        signature_and_coff = self._stream.read(24)
        if len(signature_and_coff) != 24 or signature_and_coff[:4] != b"PE\x00\x00":
            raise ValueError(f"PE 签名无效: {self.path}")
        number_of_sections = struct.unpack_from("<H", signature_and_coff, 6)[0]
        optional_size = struct.unpack_from("<H", signature_and_coff, 20)[0]
        optional = self._stream.read(optional_size)
        if len(optional) != optional_size or optional_size < 32:
            raise ValueError(f"PE optional header 缺失或损坏: {self.path}")
        magic = struct.unpack_from("<H", optional, 0)[0]
        if magic == 0x20B:
            image_base = struct.unpack_from("<Q", optional, 24)[0]
        elif magic == 0x10B:
            image_base = struct.unpack_from("<I", optional, 28)[0]
        else:
            raise ValueError(f"不支持的 PE optional header 0x{magic:x}: {self.path}")

        sections: list[_SectionRange] = []
        for _ in range(number_of_sections):
            header = self._stream.read(40)
            if len(header) != 40:
                raise ValueError(f"PE section table 不完整: {self.path}")
            name = header[:8].split(b"\x00", 1)[0].decode("ascii", errors="replace")
            virtual_size, virtual_address, raw_size, raw_address = struct.unpack_from(
                "<IIII", header, 8
            )
            sections.append(
                _SectionRange(
                    name=name,
                    virtual_address=virtual_address,
                    virtual_span=max(virtual_size, raw_size),
                    raw_address=raw_address,
                    raw_size=raw_size,
                )
            )
        return image_base, tuple(sections)
