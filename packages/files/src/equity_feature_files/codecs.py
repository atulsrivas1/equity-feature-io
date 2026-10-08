"""Bounded normalized scalar readers; optional codecs are explicitly pinned."""
from __future__ import annotations

from collections.abc import Callable, Iterator
import csv
from importlib import import_module
from importlib.metadata import version
import io
import re
from typing import Protocol, TypeAlias, cast

from equity_feature_contracts.adapters import SourceErrorCode
from equity_feature_contracts.inputs import I64_MAX
from .model import FIELDS, FileProfile, ReadPolicy, fail, stamp, text

Row: TypeAlias = tuple[str, str, int, int, str, bool, int, int, int | None]
Check: TypeAlias = Callable[[], None]


def dependency(name: str, distribution: str, expected: str) -> object:
    module: object | None = None
    try:
        if version(distribution) == expected:
            module = import_module(name)
    except Exception:
        pass
    if module is None:
        fail(SourceErrorCode.UNSUPPORTED)
    return module


def integer(value: str) -> int:
    if len(value) > 20 or re.fullmatch(r"-?(0|[1-9][0-9]*)", value) is None:
        fail()
    result = int(value)
    stamp(result)
    return result


def csv_rows(raw: bytes, policy: ReadPolicy, check: Check) -> Iterator[Row]:
    header_end = raw.find(b"\n")
    if (len(raw) if header_end < 0 else header_end+1) > policy.max_metadata_bytes:
        fail(SourceErrorCode.LIMIT)
    reader = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    header = next(reader, None)
    if header != list(FIELDS):
        fail(SourceErrorCode.UNSUPPORTED)
    for index, values in enumerate(reader):
        check()
        if index >= policy.max_input_rows:
            fail(SourceErrorCode.LIMIT)
        if len(values) != len(FIELDS) or values[5] not in ("0", "1"):
            fail()
        yield (values[0], values[1], integer(values[2]), integer(values[3]),
               values[4], values[5] == "1", integer(values[6]), integer(values[7]),
               None if values[8] == "" else integer(values[8]))


class _ArrowField(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def type(self) -> object: ...


class _ArrowColumn(Protocol):
    def to_pylist(self) -> list[object]: ...


class _ArrowBatch(Protocol):
    @property
    def num_rows(self) -> int: ...
    def column(self, index: int) -> _ArrowColumn: ...


class _ParquetColumn(Protocol):
    @property
    def compression(self) -> str: ...
    @property
    def total_uncompressed_size(self) -> int: ...


class _RowGroup(Protocol):
    @property
    def num_columns(self) -> int: ...
    def column(self, index: int) -> _ParquetColumn: ...


class _ParquetMetadata(Protocol):
    @property
    def num_rows(self) -> int: ...
    @property
    def num_row_groups(self) -> int: ...
    def row_group(self, index: int) -> _RowGroup: ...


class _ParquetFile(Protocol):
    @property
    def metadata(self) -> _ParquetMetadata: ...
    @property
    def schema_arrow(self) -> Iterator[_ArrowField]: ...
    def iter_batches(self, *, batch_size: int, use_threads: bool) -> Iterator[_ArrowBatch]: ...


def parquet_rows(raw: bytes, policy: ReadPolicy, check: Check) -> Iterator[Row]:
    # Check footer before invoking native metadata parsing.
    if len(raw) < 12 or raw[:4] != b"PAR1" or raw[-4:] != b"PAR1":
        fail(SourceErrorCode.UNSUPPORTED)
    footer = int.from_bytes(raw[-8:-4], "little")
    if footer > policy.max_metadata_bytes:
        fail(SourceErrorCode.LIMIT)
    if footer > len(raw) - 12:
        fail()
    module = dependency("pyarrow.parquet", "pyarrow", "20.0.0")
    constructor = cast(Callable[..., _ParquetFile], getattr(module, "ParquetFile"))
    file = constructor(io.BytesIO(raw), memory_map=False,
                       thrift_string_size_limit=policy.max_metadata_bytes,
                       thrift_container_size_limit=policy.max_metadata_bytes)
    fields = tuple(file.schema_arrow)
    expected = ("string", "string", "int64", "int64", "string", "bool", "int64", "int64", "int64")
    if tuple(v.name for v in fields) != FIELDS or tuple(str(v.type) for v in fields) != expected:
        fail(SourceErrorCode.UNSUPPORTED)
    if file.metadata.num_rows > policy.max_input_rows:
        fail(SourceErrorCode.LIMIT)
    decoded = 0
    for index in range(file.metadata.num_row_groups):
        check()
        group = file.metadata.row_group(index)
        for column in range(group.num_columns):
            item = group.column(column)
            if item.compression != "UNCOMPRESSED":
                fail(SourceErrorCode.UNSUPPORTED)
            decoded += item.total_uncompressed_size
            if decoded > policy.max_decoded_bytes:
                fail(SourceErrorCode.LIMIT)
    for batch in file.iter_batches(batch_size=policy.decode_batch_rows, use_threads=False):
        check()
        columns = tuple(batch.column(i).to_pylist() for i in range(len(FIELDS)))
        for index in range(batch.num_rows):
            yield cast(Row, tuple(column[index] for column in columns))


class _Decoder(Protocol):
    def write(self, data: bytes) -> None: ...
    def decode(self) -> list[object]: ...
    def buffer(self) -> bytes: ...


class _Metadata(Protocol):
    @property
    def version(self) -> int: ...
    @property
    def schema(self) -> str | None: ...
    @property
    def dataset(self) -> str: ...
    @property
    def ts_out(self) -> bool: ...


class _Trade(Protocol):
    @property
    def publisher_id(self) -> int: ...
    @property
    def instrument_id(self) -> int: ...
    @property
    def ts_event(self) -> int: ...
    @property
    def price(self) -> int: ...
    @property
    def size(self) -> int: ...
    @property
    def action(self) -> str: ...


def dbn_rows(raw: bytes, profile: FileProfile, policy: ReadPolicy, check: Check) -> Iterator[Row]:
    if len(raw) < 8 or raw[:4] != b"DBN\x03":
        fail(SourceErrorCode.UNSUPPORTED)
    metadata_bytes = 8 + int.from_bytes(raw[4:8], "little")
    if metadata_bytes > policy.max_metadata_bytes:
        fail(SourceErrorCode.LIMIT)
    if metadata_bytes > len(raw):
        fail()
    remaining = len(raw) - metadata_bytes
    if remaining % 48:
        fail()
    count = remaining // 48
    if count > policy.max_input_rows:
        fail(SourceErrorCode.LIMIT)
    if count != len(profile.dbn_annotations):
        fail()
    module = dependency("databento_dbn", "databento-dbn", "0.70.0")
    constructor = cast(Callable[..., _Decoder], getattr(module, "DBNDecoder"))
    decoder = constructor(upgrade_policy=getattr(getattr(module, "VersionUpgradePolicy"), "AS_IS"))
    decoder.write(raw[:metadata_bytes])
    decoded = decoder.decode()
    metadata_type = cast(type[object], getattr(module, "Metadata"))
    trade_type = cast(type[object], getattr(module, "TradeMsg"))
    if len(decoded) != 1 or not isinstance(decoded[0], metadata_type) or decoder.buffer():
        fail()
    metadata = cast(_Metadata, decoded[0])
    if metadata.version != 3 or metadata.schema != "trades" or metadata.ts_out:
        fail(SourceErrorCode.UNSUPPORTED)
    if metadata.dataset != profile.dbn_dataset:
        fail()
    identities = {(v.publisher_id, v.instrument_id): v.canonical_id for v in profile.dbn_identities}
    for index, annotation in enumerate(profile.dbn_annotations):
        check()
        offset = metadata_bytes + index * 48
        if raw[offset] != 12:
            fail(SourceErrorCode.UNSUPPORTED)
        decoder.write(raw[offset:offset+48])
        records = decoder.decode()
        if len(records) != 1 or not isinstance(records[0], trade_type) or decoder.buffer():
            fail(SourceErrorCode.UNSUPPORTED)
        trade = cast(_Trade, records[0])
        identity = identities.get((trade.publisher_id, trade.instrument_id))
        if identity is None or trade.action != "T" or trade.price == I64_MAX or trade.size == 4294967295:
            fail()
        yield (identity, annotation.session_id, trade.ts_event, index+1,
               "dbn:" + profile.sha256 + ":" + str(index+1), annotation.eligible,
               trade.price, trade.size, annotation.known_at_ns)


def decode(raw: bytes, profile: FileProfile, policy: ReadPolicy, check: Check) -> tuple[Row, ...]:
    if len(raw) > policy.max_bytes:
        fail(SourceErrorCode.LIMIT)
    rows = (csv_rows(raw, policy, check) if profile.format == "csv" else
            parquet_rows(raw, policy, check) if profile.format == "parquet" else
            dbn_rows(raw, profile, policy, check))
    result: list[Row] = []
    decoded = 0
    for row in rows:
        check()
        if len(result) >= policy.max_input_rows or len(row) != 9:
            fail(SourceErrorCode.LIMIT)
        for index in (0, 1, 4):
            text(row[index])
        for index in (2, 3, 6, 7):
            stamp(row[index])
        if type(row[5]) is not bool:
            fail()
        if row[8] is not None:
            stamp(row[8])
        decoded += sum(len(v.encode("utf-8")) if type(v) is str else 8 for v in row)
        if decoded > policy.max_decoded_bytes:
            fail(SourceErrorCode.LIMIT)
        result.append(row)
    return tuple(result)
