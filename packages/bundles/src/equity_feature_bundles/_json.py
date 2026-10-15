"""Bounded lexical admission BEFORE JSON graph allocation and numeric conversion."""
from __future__ import annotations
import json
import re
from typing import Any
from ._errors import BundleError, require


class Budget:
    def __init__(self, maximum_bytes: int = 33554432, maximum_nodes: int = 1000000) -> None:
        self.size = 0
        self.nodes = 0
        self.maximum_bytes = maximum_bytes
        self.maximum_nodes = maximum_nodes


def preflight(raw: bytes, kind: str, budget: Budget | None = None) -> None:
    """No int(), JSON loads or decoded string allocation occurs in this pass."""
    require(type(raw) is bytes)
    typed = kind == 'typed'
    require(kind in ('typed', 'manifest', 'receipt'))
    maximum = 33554432 if typed else 65536 if kind == 'manifest' else 1048576
    require(len(raw) <= maximum, 'limit_exceeded')
    require(all(c < 128 for c in raw))
    shared = budget if budget is not None else Budget(maximum, 1000000 if typed else 8192 if kind == 'manifest' else 32768)
    shared.size += len(raw)
    require(shared.size <= shared.maximum_bytes, 'limit_exceeded')
    depth_limit = 24 if typed else 8 if kind == 'manifest' else 16
    array_limit = 100000 if typed else 64 if kind == 'manifest' else 256
    raw_string_limit = 49154 if typed else 3074
    cp_limit, utf8_limit = (4096, 16384) if typed else (256, 1024)
    pos = 0
    length = len(raw)

    def node() -> None:
        shared.nodes += 1
        require(shared.nodes <= shared.maximum_nodes, 'limit_exceeded')

    def ws() -> None:
        nonlocal pos
        while pos < length and raw[pos] in b' \t\r\n':
            pos += 1

    def string() -> None:
        nonlocal pos
        start = pos
        require(pos < length and raw[pos] == 34)
        pos += 1
        cps = width = 0
        while True:
            require(pos < length)
            require(pos - start + 1 <= raw_string_limit, 'limit_exceeded')
            c = raw[pos]
            pos += 1
            if c == 34:
                return
            require(c >= 32)
            if c == 92:
                require(pos < length)
                esc = raw[pos]; pos += 1
                if esc == 117:
                    require(pos + 4 <= length)
                    digits = raw[pos:pos + 4]
                    require(all(x in b'0123456789abcdefABCDEF' for x in digits))
                    # Four hex digits have a constant bound; this is not number-token conversion.
                    c = 0
                    for digit in digits:
                        c = c * 16 + b'0123456789abcdef'.index(bytes((digit,)).lower())
                    pos += 4
                    if 0xD800 <= c <= 0xDBFF:
                        require(pos + 6 <= length and raw[pos:pos + 2] == b'\\u')
                        low = 0
                        for digit in raw[pos + 2:pos + 6]:
                            require(digit in b'0123456789abcdefABCDEF')
                            low = low * 16 + b'0123456789abcdef'.index(bytes((digit,)).lower())
                        require(0xDC00 <= low <= 0xDFFF)
                        c = 0x10000 + (c - 0xD800) * 1024 + low - 0xDC00
                        pos += 6
                    else:
                        require(not 0xDC00 <= c <= 0xDFFF)
                else:
                    require(esc in b'"\\/bfnrt')
                    c = {34:34, 92:92, 47:47, 98:8, 102:12, 110:10, 114:13, 116:9}[esc]
            if not typed:
                require(not (c < 32 or 127 <= c <= 159))
            cps += 1
            width += 1 if c < 128 else 2 if c < 2048 else 3 if c < 65536 else 4
            require(cps <= cp_limit and width <= utf8_limit, 'limit_exceeded')
            require(pos - start + 1 <= raw_string_limit, 'limit_exceeded')

    def value(depth: int) -> None:
        nonlocal pos
        ws(); node()
        require(pos < length)
        c = raw[pos]
        if c == 34:
            string(); return
        if c in (123, 91):
            require(depth < depth_limit, 'limit_exceeded')
            obj = c == 123
            pos += 1; ws()
            close = 125 if obj else 93
            if pos < length and raw[pos] == close:
                pos += 1; return
            count = 0
            while True:
                if obj:
                    node(); string(); ws()
                    require(pos < length and raw[pos] == 58); pos += 1
                value(depth + 1); count += 1
                if not obj:
                    require(count <= array_limit, 'limit_exceeded')
                ws(); require(pos < length)
                c = raw[pos]; pos += 1
                if c == close:
                    return
                require(c == 44); ws()
        for literal in (b'null', b'true', b'false'):
            if raw[pos:pos + len(literal)] == literal:
                pos += len(literal); return
        start = pos
        while pos < length and raw[pos] not in b',]} \t\r\n':
            pos += 1
            require(pos - start <= (39 if typed else 8 if kind == 'manifest' else 20), 'limit_exceeded')
        token = raw[start:pos]
        digits = token[1:] if token.startswith(b'-') else token
        require(len(digits) <= (38 if typed else 8 if kind == 'manifest' else 19), 'limit_exceeded')
        require(re.fullmatch(rb'0|-?[1-9][0-9]*', token) is not None)
        if kind == 'manifest':
            require(not token.startswith(b'-'))
            require(len(digits) < 8 or digits <= b'33554432', 'limit_exceeded')
        elif kind == 'receipt':
            require(len(digits) < 19 or digits <= (b'9223372036854775808' if token.startswith(b'-') else b'9223372036854775807'))
    value(0); ws(); require(pos == length)


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def load(raw: bytes) -> Any:
    # Callers must complete the shared lexical pass for ALL entries first.
    return json.loads(raw, object_pairs_hook=unique)


def dump(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def fields(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    require(type(value) is dict and set(value) == set(keys))
    assert isinstance(value, dict)
    return value
