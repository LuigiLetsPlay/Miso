"""Minimal protobuf wire-format codec.

Steam talks protobuf, but we only need a handful of messages, so instead of
shipping generated classes we encode/decode the wire format by hand.
"""
from __future__ import annotations

import struct

VARINT, I64, LEN, I32 = 0, 1, 2, 5


def _varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


class Writer:
    def __init__(self) -> None:
        self._buf = bytearray()

    def _key(self, field: int, wire: int) -> None:
        self._buf += _varint((field << 3) | wire)

    def varint(self, field: int, value: int | bool) -> "Writer":
        self._key(field, VARINT)
        self._buf += _varint(int(value))
        return self

    def fixed64(self, field: int, value: int) -> "Writer":
        self._key(field, I64)
        self._buf += struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)
        return self

    def fixed32(self, field: int, value: int) -> "Writer":
        self._key(field, I32)
        self._buf += struct.pack("<I", value & 0xFFFFFFFF)
        return self

    def bytes(self, field: int, value: bytes) -> "Writer":
        self._key(field, LEN)
        self._buf += _varint(len(value)) + value
        return self

    def string(self, field: int, value: str) -> "Writer":
        return self.bytes(field, value.encode("utf-8"))

    def build(self) -> bytes:
        return bytes(self._buf)


class Message:
    """Decoded message: field number -> list of raw values.

    Varints/fixed come back as int, length-delimited as bytes.
    """

    def __init__(self, data: bytes) -> None:
        self.fields: dict[int, list] = {}
        pos, end = 0, len(data)
        while pos < end:
            key, pos = _read_varint(data, pos)
            field, wire = key >> 3, key & 7
            if wire == VARINT:
                value, pos = _read_varint(data, pos)
            elif wire == I64:
                value = struct.unpack_from("<Q", data, pos)[0]
                pos += 8
            elif wire == LEN:
                n, pos = _read_varint(data, pos)
                value = data[pos:pos + n]
                pos += n
            elif wire == I32:
                value = struct.unpack_from("<I", data, pos)[0]
                pos += 4
            else:
                raise ValueError(f"unsupported wire type {wire}")
            self.fields.setdefault(field, []).append(value)

    def get(self, field: int, default=None):
        values = self.fields.get(field)
        return values[-1] if values else default

    def all(self, field: int) -> list:
        return self.fields.get(field, [])

    def int(self, field: int, default: int = 0) -> int:
        return self.get(field, default)

    def signed(self, field: int, default: int = 0) -> int:
        v = self.get(field, default)
        return v - (1 << 64) if v >= 1 << 63 else v

    def str(self, field: int, default: str = "") -> str:
        v = self.get(field)
        return v.decode("utf-8", "replace") if v is not None else default

    def msg(self, field: int) -> "Message":
        return Message(self.get(field, b""))

    def msgs(self, field: int) -> list["Message"]:
        return [Message(v) for v in self.all(field)]


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7
