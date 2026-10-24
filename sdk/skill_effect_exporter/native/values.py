"""Values the emulator computes with: bits, references, named unknowns, provenance."""

import struct
from dataclasses import dataclass


class Unsupported(Exception):
    """The emulated code needs something this model does not provide."""


@dataclass(frozen=True)
class Unk:
    name: str


@dataclass(frozen=True)
class Ptr:
    obj: "HObj"
    off: int = 0
    tag: int = 0  # high bits carried by tagged references (btr 63 clears them)

    def add(self, delta):
        return Ptr(self.obj, self.off + delta, self.tag)


@dataclass(frozen=True)
class V:
    """A register or memory value: int bits, Ptr or Unk, plus provenance."""

    val: object
    prov: frozenset = frozenset()

    @property
    def known(self):
        return not isinstance(self.val, Unk)


def unk(name, prov=frozenset()):
    return V(Unk(name), frozenset(prov))


def f32(bits):
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


def f32_bits(value):
    """Single-precision bits; a finite value beyond its range rounds to infinity."""

    try:
        return struct.unpack("<I", struct.pack("<f", value))[0]
    except OverflowError:
        return 0xFF800000 if value < 0 else 0x7F800000


def f64_bits(value):
    return struct.unpack("<Q", struct.pack("<d", value))[0]
