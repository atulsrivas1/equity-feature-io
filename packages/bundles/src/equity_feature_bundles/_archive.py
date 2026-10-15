"""Strict stored ZIP language. No extraction and no ZipFile member construction."""
from __future__ import annotations
import re
import struct
import zlib
from ._errors import require

LOCAL = struct.Struct('<4s5H3I2H')
CENTRAL = struct.Struct('<4s6H3I5H2I')
END = struct.Struct('<4s4H2IH')
MAX_ARCHIVE = 35 * 1024 * 1024
FIXED = (b'configuration.json', b'manifest.json', b'receipt.json', b'result.json')
MODE = 0o100600 << 16


def safe(name: bytes) -> None:
    require(name in FIXED or re.fullmatch(rb'inputs/[0-9]{3}\.json', name) is not None, 'invalid_archive')


def read_stored(raw: bytes) -> dict[str, bytes]:
    require(type(raw) is bytes)
    require(len(raw) <= MAX_ARCHIVE, 'limit_exceeded')
    require(len(raw) >= END.size, 'invalid_archive')
    sig, disk, central_disk, n_disk, count, central_size, offset, comment = END.unpack_from(raw, len(raw) - END.size)
    require(sig == b'PK\x05\x06' and disk == central_disk == comment == 0 and n_disk == count, 'invalid_archive')
    require(4 <= count <= 68 and central_size <= 32768, 'limit_exceeded')
    require(offset + central_size + END.size == len(raw), 'invalid_archive')
    cursor = offset
    local_cursor = 0
    total = 0
    names: list[bytes] = []
    ranges: list[tuple[int, int, int]] = []
    # All directory/header sizes, names and ranges checked before ANY member copy.
    for _ in range(count):
        require(cursor + CENTRAL.size <= len(raw) - END.size, 'invalid_archive')
        values = CENTRAL.unpack_from(raw, cursor)
        (sig, made, version, flags, method, time, date, crc, compressed, size,
            name_size, extra, member_comment, member_disk, internal, external, local) = values
        require(sig == b'PK\x01\x02' and made == 788 and version == 20 and flags == method == time == 0
            and date == 33 and extra == member_comment == member_disk == internal == 0 and external == MODE
            and compressed == size and local == local_cursor, 'invalid_archive')
        require(1 <= name_size <= 18 and cursor + CENTRAL.size + name_size <= offset + central_size, 'invalid_archive')
        name = raw[cursor + CENTRAL.size:cursor + CENTRAL.size + name_size]
        safe(name)
        require(not names or name > names[-1], 'invalid_archive')
        names.append(name)
        maximum = 65536 if name == b'manifest.json' else 1048576 if name == b'receipt.json' else 33554432
        require(size <= maximum, 'limit_exceeded')
        total += size
        require(total <= 34 * 1024 * 1024, 'limit_exceeded')
        require(local + LOCAL.size + name_size <= offset, 'invalid_archive')
        header = LOCAL.unpack_from(raw, local)
        require(header == (b'PK\x03\x04', 20, 0, 0, 0, 33, crc, size, size, name_size, 0), 'invalid_archive')
        start = local + LOCAL.size + name_size
        require(raw[local + LOCAL.size:start] == name, 'invalid_archive')
        end = start + size
        require(end <= offset, 'invalid_archive')
        ranges.append((start, end, crc))
        local_cursor = end
        cursor += CENTRAL.size + name_size
    require(cursor == offset + central_size and local_cursor == offset, 'invalid_archive')
    require(all(x in names for x in FIXED), 'invalid_archive')
    result: dict[str, bytes] = {}
    for name, (start, end, crc) in zip(names, ranges, strict=True):
        data = raw[start:end]
        require(zlib.crc32(data) == crc, 'integrity_mismatch')
        result[name.decode('ascii')] = data
    return result


def write_stored(entries: dict[str, bytes]) -> bytes:
    require(4 <= len(entries) <= 68, 'limit_exceeded')
    local = bytearray()
    central = bytearray()
    total = 0
    for key in sorted(entries):
        name = key.encode('ascii'); safe(name)
        data = entries[key]
        total += len(data)
        require(total <= 34 * 1024 * 1024, 'limit_exceeded')
        crc = zlib.crc32(data)
        central.extend(CENTRAL.pack(b'PK\x01\x02', 788, 20, 0, 0, 0, 33, crc, len(data), len(data), len(name), 0, 0, 0, 0, MODE, len(local)))
        central.extend(name)
        local.extend(LOCAL.pack(b'PK\x03\x04', 20, 0, 0, 0, 33, crc, len(data), len(data), len(name), 0))
        local.extend(name); local.extend(data)
    require(len(central) <= 32768, 'limit_exceeded')
    ending = END.pack(b'PK\x05\x06', 0, 0, len(entries), len(entries), len(central), len(local), 0)
    require(len(local) + len(central) + len(ending) <= MAX_ARCHIVE, 'limit_exceeded')
    local.extend(central); local.extend(ending)
    return bytes(local)
