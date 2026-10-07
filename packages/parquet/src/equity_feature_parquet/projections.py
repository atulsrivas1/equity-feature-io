"""Exact typed analytics projections; canonical records remain complete authority."""
from __future__ import annotations

from collections.abc import Buffer
from decimal import Decimal
import io
import os
from pathlib import Path
from typing import cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from equity_feature_contracts.results import FeatureResult, ValueType
from equity_feature_io_contracts.publication import SinkError, SinkErrorCode
from equity_feature_io_sdk.codec import canonical_json, to_wire

Row = dict[str, object]


def schemas() -> tuple[object, object]:
    """Closed storage1 schemas; no inferred Pandas/string/time conversions."""
    cells = pa.schema([
        ("result_ordinal", pa.int64()), ("column_ordinal", pa.int64()), ("entity_ordinal", pa.int64()),
        ("namespace", pa.string()), ("instrument_id", pa.string()), ("session_id", pa.string()),
        ("feature_id", pa.string()), ("algorithm_version", pa.string()), ("dtype", pa.string()),
        ("unit", pa.string()), ("schema_version", pa.string()), ("is_null", pa.bool_()),
        ("value_int64", pa.int64()), ("value_decimal128", pa.decimal128(38, 0)),
        ("value_float64", pa.float64()), ("value_bool", pa.bool_()), ("value_utf8", pa.string()),
        ("value_wire", pa.binary()), ("quality_status", pa.string()), ("quality_expected", pa.int64()),
        ("quality_observed", pa.int64()), ("quality_reasons", pa.list_(pa.field("element", pa.string()))),
    ], metadata={b"efio_storage": b"efio-parquet1", b"efio_table": b"cells"})
    evidence = pa.schema([
        ("result_ordinal", pa.int64()), ("evidence_ordinal", pa.int64()), ("feature_id", pa.string()),
        ("instrument_id", pa.string()), ("session_id", pa.string()), ("input_id", pa.string()),
        ("row_id", pa.string()), ("event_ns", pa.int64()), ("known_at_ns", pa.int64()),
        ("effective_start_ns", pa.int64()), ("effective_end_ns", pa.int64()),
        ("use", pa.string()), ("exclusion_reason", pa.string()), ("boundary", pa.string()),
    ], metadata={b"efio_storage": b"efio-parquet1", b"efio_table": b"evidence"})
    return cells, evidence


def rows(result: FeatureResult, ordinal: int) -> tuple[list[Row], list[Row]]:
    qualities = {(q.entity, q.feature_id): q for q in result.quality}
    cells: list[Row] = []
    for col_ordinal, column in enumerate(result.values):
        for entity_ordinal, (entity, value) in enumerate(zip(column.entities, column.values, strict=True)):
            q = qualities[entity, column.feature_id]
            item: Row = dict(result_ordinal=ordinal, column_ordinal=col_ordinal, entity_ordinal=entity_ordinal,
                             namespace=result.metadata.namespace, instrument_id=entity.instrument_id,
                             session_id=entity.session_id, feature_id=column.feature_id,
                             algorithm_version=column.algorithm_version, dtype=column.dtype.value,
                             unit=column.unit, schema_version=column.schema_version, is_null=value is None,
                             value_int64=None, value_decimal128=None, value_float64=None, value_bool=None,
                             value_utf8=None, value_wire=None, quality_status=q.status.value,
                             quality_expected=q.expected, quality_observed=q.observed,
                             quality_reasons=[reason.value for reason in q.reasons])
            if value is not None:
                if column.dtype is ValueType.INT64:
                    item["value_int64"] = value
                elif column.dtype is ValueType.DECIMAL128:
                    assert type(value) is int
                    item["value_decimal128"] = Decimal(value)
                elif column.dtype is ValueType.FLOAT64:
                    item["value_float64"] = value
                elif column.dtype is ValueType.BOOL:
                    item["value_bool"] = value
                elif column.dtype is ValueType.STRING:
                    item["value_utf8"] = value
                else:
                    item["value_wire"] = canonical_json(to_wire(value))
            cells.append(item)
    evidence: list[Row] = [dict(result_ordinal=ordinal, evidence_ordinal=index, feature_id=e.feature_id,
                                instrument_id=e.entity.instrument_id, session_id=e.entity.session_id,
                                input_id=e.input_id, row_id=e.row_id, event_ns=e.event_ns,
                                known_at_ns=e.known_at_ns, effective_start_ns=e.effective_start_ns,
                                effective_end_ns=e.effective_end_ns, use=e.use,
                                exclusion_reason=None if e.exclusion_reason is None else e.exclusion_reason.value,
                                boundary=e.boundary) for index, e in enumerate(result.evidence)]
    return cells, evidence


def _payload_bytes(value: object) -> int:
    if type(value) is str:
        return len(value.encode("utf-8")) + 4
    if type(value) is bytes:
        return len(value) + 4
    if isinstance(value, Decimal):
        return 16
    if type(value) is list:
        return 4 + sum(_payload_bytes(item) for item in value)
    return 8


class _BoundedWriter(io.RawIOBase):
    def __init__(self, path: Path, limit: int) -> None:
        super().__init__()
        self._file = path.open("xb")
        self._limit = limit
        self.exceeded = False

    def writable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._file.tell()

    def write(self, data: Buffer) -> int:
        if self.tell() + memoryview(data).nbytes > self._limit:
            self.exceeded = True
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        return self._file.write(data)

    def close(self) -> None:
        if not self.closed:
            try:
                self._file.flush()
                os.fsync(self._file.fileno())
            finally:
                self._file.close()
                super().close()


def _allocation_bytes(data: list[Row]) -> int:
    # Conservative nullable fixed-width/offset/validity allowance per field,
    # plus all repeated variable payloads (including list children).
    return sum(32 * len(row) + sum(_payload_bytes(value) for value in row.values()) for row in data)


def write_projection(path: Path, data: list[Row], schema: object, physical_limit: int) -> None:
    # Repeated namespace/header strings can expand a small logical result dramatically.
    # Admit the actual repeated payload before Arrow buffers and limit every physical write.
    payload = _allocation_bytes(data)
    if payload > physical_limit:
        raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
    table = pa.Table.from_pylist(data, schema=schema)
    if table.nbytes > physical_limit:
        raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
    output = _BoundedWriter(path, physical_limit)
    try:
        pq.write_table(table, output, version="2.6", compression="NONE", use_dictionary=False,
                       write_statistics=False, row_group_size=4096, write_batch_size=1024,
                       data_page_size=65536, store_schema=True)
    except Exception:
        if output.exceeded:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT) from None
        raise
    finally:
        output.close()


def _exact(value: object) -> object:
    if type(value) is float:
        return ("float", value.hex())
    if isinstance(value, Decimal):
        return ("decimal", str(value))
    if type(value) is list:
        return tuple(_exact(v) for v in value)
    if type(value) is dict:
        return tuple((k, _exact(v)) for k, v in sorted(value.items()))
    return (type(value).__name__, value)


def verify_projection(path: Path, expected: list[Row], schema: object, physical_limit: int) -> None:
    if _allocation_bytes(expected) > physical_limit:
        raise SinkError(SinkErrorCode.CORRUPTION)
    file = pq.ParquetFile(path, memory_map=False, pre_buffer=False,
                          thrift_string_size_limit=1048576, thrift_container_size_limit=1048576)
    try:
        if not file.schema_arrow.equals(schema, check_metadata=True) or file.metadata.num_rows != len(expected):
            raise SinkError(SinkErrorCode.CORRUPTION)
        # Only the qualified writer format is admitted. Small compressed or
        # dictionary payloads can otherwise allocate huge buffers before parity
        # rejects them. Footer rows alone do not bound variable-width buffers.
        metadata = file.metadata
        if metadata.num_row_groups > max(1, (len(expected) + 4095) // 4096):
            raise SinkError(SinkErrorCode.CORRUPTION)
        uncompressed = 0
        row_offset = 0
        for group_index in range(metadata.num_row_groups):
            group = metadata.row_group(group_index)
            if group.num_rows > 4096:
                raise SinkError(SinkErrorCode.CORRUPTION)
            for column_index in range(group.num_columns):
                column = group.column(column_index)
                if (column.compression != "UNCOMPRESSED"
                        or not set(column.encodings) <= {"PLAIN", "RLE"}
                        or column.total_uncompressed_size < 0):
                    raise SinkError(SinkErrorCode.CORRUPTION)
                group_rows = expected[row_offset:row_offset + group.num_rows]
                if column.path_in_schema == "quality_reasons.list.element":
                    expected_values = sum(max(1, len(cast(list[object], row["quality_reasons"]))) for row in group_rows)
                else:
                    expected_values = group.num_rows
                if column.num_values != expected_values:
                    raise SinkError(SinkErrorCode.CORRUPTION)
                uncompressed += column.total_uncompressed_size
                if uncompressed > physical_limit:
                    raise SinkError(SinkErrorCode.CORRUPTION)
            row_offset += group.num_rows
        observed = cast(list[Row], file.read(use_threads=False).to_pylist())
        if _exact(observed) != _exact(expected):
            raise SinkError(SinkErrorCode.CORRUPTION)
    finally:
        file.close()
