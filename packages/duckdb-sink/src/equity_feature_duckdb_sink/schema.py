"""Closed SQL layout and fixed native engine configuration."""
from __future__ import annotations

from typing import Protocol, cast
import duckdb

from equity_feature_io_contracts.publication import SinkError, SinkErrorCode

STORAGE_VERSION = "efio-duckdb1"
CONFIG: dict[str, str | bool | int | float | list[str]] = dict(memory_limit="128MiB", threads="1", max_temp_directory_size="0B",
              enable_external_access="false", autoload_known_extensions="false",
              autoinstall_known_extensions="false")


class Connection(Protocol):
    def execute(self, query: str, parameters: object = ...) -> Connection: ...
    def executemany(self, query: str, parameters: object) -> Connection: ...
    def fetchall(self) -> list[tuple[object, ...]]: ...
    def close(self) -> None: ...


def connect(path: str, *, read_only: bool = False) -> Connection:
    return cast(Connection, duckdb.connect(path, read_only=read_only, config=CONFIG))


CELL_FIELDS = (
    ("result_ordinal", "BIGINT"), ("column_ordinal", "BIGINT"), ("entity_ordinal", "BIGINT"),
    ("namespace", "VARCHAR"), ("instrument_id", "VARCHAR"), ("session_id", "VARCHAR"),
    ("feature_id", "VARCHAR"), ("algorithm_version", "VARCHAR"), ("dtype", "VARCHAR"),
    ("unit", "VARCHAR"), ("schema_version", "VARCHAR"), ("is_null", "BOOLEAN"),
    ("value_int64", "BIGINT"), ("value_decimal128", "DECIMAL(38,0)"),
    ("value_float64", "DOUBLE"), ("value_bool", "BOOLEAN"), ("value_utf8", "VARCHAR"),
    ("value_wire", "BLOB"), ("quality_status", "VARCHAR"), ("quality_expected", "BIGINT"),
    ("quality_observed", "BIGINT"), ("quality_reasons", "VARCHAR[]"),
)
EVIDENCE_FIELDS = (
    ("result_ordinal", "BIGINT"), ("evidence_ordinal", "BIGINT"), ("feature_id", "VARCHAR"),
    ("instrument_id", "VARCHAR"), ("session_id", "VARCHAR"), ("input_id", "VARCHAR"),
    ("row_id", "VARCHAR"), ("event_ns", "BIGINT"), ("known_at_ns", "BIGINT"),
    ("effective_start_ns", "BIGINT"), ("effective_end_ns", "BIGINT"),
    ("use", "VARCHAR"), ("exclusion_reason", "VARCHAR"), ("boundary", "VARCHAR"),
)
PREFIX = (("pub_key", "VARCHAR"), ("attempt", "VARCHAR"))
TABLES = {
    "efio_metadata": (("id", "BIGINT"), ("storage_version", "VARCHAR")),
    "efio_reservations": PREFIX + (("state", "VARCHAR"), ("envelope", "BLOB")),
    "efio_results": PREFIX + (("result_ordinal", "BIGINT"), ("record", "BLOB"),
                              ("cells_bundle", "BLOB"), ("evidence_bundle", "BLOB")),
    "efio_cells": PREFIX + CELL_FIELDS,
    "efio_evidence": PREFIX + EVIDENCE_FIELDS,
    "efio_completions": PREFIX + (("envelope", "BLOB"), ("receipt", "BLOB")),
}
KEYS = {
    "efio_metadata": ("id",), "efio_reservations": ("pub_key",),
    "efio_results": ("pub_key", "attempt", "result_ordinal"),
    "efio_cells": ("pub_key", "attempt", "result_ordinal", "column_ordinal", "entity_ordinal"),
    "efio_evidence": ("pub_key", "attempt", "result_ordinal", "evidence_ordinal"),
    "efio_completions": ("pub_key",),
}


def create(connection: Connection) -> None:
    connection.execute("BEGIN TRANSACTION")
    for table, fields in TABLES.items():
        columns = ",".join(name + " " + dtype + (" NOT NULL" if name in KEYS[table] else "")
                           for name, dtype in fields)
        connection.execute(f"CREATE TABLE {table} ({columns}, PRIMARY KEY ({','.join(KEYS[table])}))")
    connection.execute("INSERT INTO efio_metadata VALUES (1, ?)", [STORAGE_VERSION])
    connection.execute("COMMIT")


def preflight(connection: Connection) -> None:
    names = connection.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_catalog=current_database() ORDER BY table_schema,table_name").fetchall()
    if ("main","efio_metadata") not in names:
        raise SinkError(SinkErrorCode.INVALID_CONFIG)
    if names != [("main",name) for name in sorted(TABLES)]:
        raise SinkError(SinkErrorCode.CORRUPTION)
    for table, fields in TABLES.items():
        columns = connection.execute("SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='main' AND table_name=? ORDER BY ordinal_position", [table]).fetchall()
        expected = [(name, dtype, "NO" if name in KEYS[table] else "YES") for name, dtype in fields]
        if columns != expected:
            raise SinkError(SinkErrorCode.CORRUPTION)
        primary = connection.execute("SELECT constraint_column_names FROM duckdb_constraints() WHERE schema_name='main' AND table_name=? AND constraint_type='PRIMARY KEY'", [table]).fetchall()
        if primary != [(list(KEYS[table]),)]:
            raise SinkError(SinkErrorCode.CORRUPTION)
    if connection.execute("SELECT count(*),coalesce(max(length(storage_version)),0) FROM efio_metadata").fetchall() != [(1,len(STORAGE_VERSION))]:
        raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)
    if connection.execute("SELECT id,storage_version FROM efio_metadata").fetchall() != [(1, STORAGE_VERSION)]:
        raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)


def engine_error(error: Exception, fallback: SinkErrorCode) -> SinkError:
    return SinkError(SinkErrorCode.RESOURCE_LIMIT if isinstance(error, duckdb.OutOfMemoryException) else fallback)
