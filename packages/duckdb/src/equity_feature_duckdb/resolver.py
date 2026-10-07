"""Bounded, explicit metadata resolution. Source declarations are not admission."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import NoReturn, cast

import duckdb
from equity_feature_contracts.adapters import Cancellation, SourceError, SourceErrorCode


def _fail(message: str, code: SourceErrorCode = SourceErrorCode.SCHEMA) -> NoReturn:
    raise SourceError(code, message) from None


def _text(value: object) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        _fail("Nonempty explicit metadata required")
    return value


def _count(value: object, *, positive: bool = False) -> int:
    if type(value) is not int or not (1 if positive else 0) <= value <= 2**63 - 1:
        _fail("Exact bounded integer required")
    return value


def _hash(value: object) -> str | None:
    if value is not None and (type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None):
        _fail("Lowercase SHA256 required")
    return value


def _identifier(value: object) -> str:
    text = _text(value)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text) is None:
        _fail("Static SQL identifier required")
    return text


def _absolute(value: object) -> str:
    text = _text(value)
    if not Path(text).is_absolute():
        _fail("Absolute local file path required")
    return text


def _date(value: object) -> str:
    text = _text(value)
    try:
        valid = date.fromisoformat(text).isoformat() == text
    except ValueError:
        valid = False
    if not valid:
        _fail("Exact ISO partition date required")
    return text


def _cancel(cancellation: Cancellation | None) -> None:
    if cancellation is not None:
        cancelled = cancellation.is_cancelled()
        if type(cancelled) is not bool:
            _fail("Boolean cancellation state required")
        if cancelled:
            _fail("Source resolution cancelled", SourceErrorCode.CANCELLED)


@dataclass(frozen=True)
class CatalogConfig:
    path: Path
    expected_sha256: str | None = None
    max_sessions: int = 366
    max_files: int = 4096
    max_hash_bytes: int = 1073741824

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            _fail("Explicit Path catalog required")
        _absolute(str(self.path))
        _hash(self.expected_sha256)
        for value in (self.max_sessions, self.max_files, self.max_hash_bytes):
            _count(value, positive=True)


@dataclass(frozen=True)
class SourceSelection:
    layer: str
    snapshot: str
    dataset: str
    source_schema: str
    sessions: tuple[str, ...]
    expected_schema_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.layer not in ("curated", "prepared") or self.source_schema not in ("trades", "tbbo", "ohlcv-1m", "ohlcv-1d"):
            _fail("Unsupported explicit source population", SourceErrorCode.UNSUPPORTED)
        _text(self.snapshot)
        _text(self.dataset)
        if type(self.sessions) not in (tuple, list) or not self.sessions:
            _fail("Concrete nonempty partition dates required")
        for session in self.sessions:
            _date(session)
        if len(set(self.sessions)) != len(self.sessions):
            _fail("Unique partition dates required")
        object.__setattr__(self, "sessions", tuple(self.sessions))
        _hash(self.expected_schema_sha256)


@dataclass(frozen=True)
class FilePin:
    original_path: str
    original_sha256: str | None = None
    optimized_sha256: str | None = None
    receipt_id: str | None = None

    def __post_init__(self) -> None:
        _absolute(self.original_path)
        _hash(self.original_sha256)
        _hash(self.optimized_sha256)
        if self.receipt_id is not None:
            _text(self.receipt_id)


@dataclass(frozen=True)
class ResolvedPartition:
    session: str
    original_path: str
    optimized_path: str
    original_bytes: int
    optimized_bytes: int
    declared_rows: int
    schema_sha256: str
    admission: str
    original_dataset: str
    substituted_dataset: str | None
    original_sha256: str | None
    optimized_sha256: str | None
    receipt_id: str | None

    @property
    def declared_empty(self) -> bool:
        return self.declared_rows == 0


@dataclass(frozen=True)
class ResolvedSource:
    selection: SourceSelection
    catalog_sha256: str
    view_schema: str
    view_name: str
    partitions: tuple[ResolvedPartition, ...]
    missing_sessions: tuple[str, ...]
    identity_digest: str


class _HashBudget:
    def __init__(self, maximum: int, cancellation: Cancellation | None) -> None:
        self.remaining = maximum
        self.cancellation = cancellation

    def read(self, path: Path, expected_size: int | None = None) -> str:
        _cancel(self.cancellation)
        try:
            size = path.stat().st_size
            if expected_size is not None and size != expected_size:
                _fail("Selected file size changed")
            if size > self.remaining:
                _fail("Hash byte budget exceeded", SourceErrorCode.LIMIT)
            sha = hashlib.sha256()
            observed = 0
            with path.open("rb") as file:
                while chunk := file.read(min(1048576, self.remaining + 1)):
                    _cancel(self.cancellation)
                    if len(chunk) > self.remaining:
                        _fail("Hash byte budget exceeded", SourceErrorCode.LIMIT)
                    self.remaining -= len(chunk)
                    observed += len(chunk)
                    sha.update(chunk)
            if observed != size or path.stat().st_size != size:
                _fail("File changed while hashing")
            return sha.hexdigest()
        except FileNotFoundError:
            _fail("Selected local file unavailable", SourceErrorCode.UNAVAILABLE)
        except OSError:
            _fail("Local file inspection failed", SourceErrorCode.TRANSPORT)


def _file(path: str, size: int, expected_hash: str | None, budget: _HashBudget) -> str | None:
    _cancel(budget.cancellation)
    try:
        if not Path(path).is_file():
            _fail("Selected local file unavailable", SourceErrorCode.UNAVAILABLE)
        if Path(path).stat().st_size != size:
            _fail("Selected file size changed")
    except OSError:
        _fail("Local file inspection failed", SourceErrorCode.TRANSPORT)
    if expected_hash is not None and budget.read(Path(path), size) != expected_hash:
        _fail("Selected file hash pin mismatch")
    return expected_hash


def resolve_source(config: CatalogConfig, selection: SourceSelection, *,
                   pins: tuple[FilePin, ...] = (),
                   cancellation: Cancellation | None = None) -> ResolvedSource:
    """Resolve exactly one declared route; never query canonical market rows."""
    return _resolve_source(config, selection, pins=pins, cancellation=cancellation)


def _resolve_source(config: CatalogConfig, selection: SourceSelection, *,
                    pins: tuple[FilePin, ...] = (),
                    cancellation: Cancellation | None = None,
                    budget: _HashBudget | None = None) -> ResolvedSource:
    if type(config) is not CatalogConfig or type(selection) is not SourceSelection:
        _fail("Typed catalog configuration and selection required")
    if len(selection.sessions) > config.max_sessions:
        _fail("Partition date bound exceeded", SourceErrorCode.LIMIT)
    if type(pins) not in (tuple, list) or any(type(pin) is not FilePin for pin in pins):
        _fail("Concrete typed file pins required")
    if len(pins) > config.max_files:
        _fail("File pin bound exceeded", SourceErrorCode.LIMIT)
    by_path = {pin.original_path: pin for pin in pins}
    if len(by_path) != len(pins):
        _fail("Duplicate file pins")
    budget = budget if budget is not None else _HashBudget(config.max_hash_bytes, cancellation)
    before = budget.read(config.path)
    if config.expected_sha256 is not None and before != config.expected_sha256:
        _fail("Catalog hash pin mismatch")
    params = [selection.layer, selection.snapshot, selection.dataset, selection.source_schema]
    try:
        with duckdb.connect(str(config.path), read_only=True,
                            config={"threads": 1, "memory_limit": "256MB"}) as connection:
            _cancel(cancellation)
            database_row = connection.execute("SELECT current_database()").fetchone()
            if database_row is None:
                _fail("Catalog database identity unavailable")
            database = _text(database_row[0]).replace('"', '""')
            prefix = '"' + database + '".catalog.'
            routes = connection.execute(
                f"SELECT view_schema, view_name FROM {prefix}datasets "
                "WHERE layer=? AND snapshot=? AND dataset=? AND source_schema=? LIMIT 2", params,
            ).fetchall()
            if not routes:
                _fail("Selected source population unavailable", SourceErrorCode.UNAVAILABLE)
            if len(routes) != 1:
                _fail("Ambiguous source population")
            view_schema, view_name = (_identifier(value) for value in routes[0])
            _cancel(cancellation)
            placeholders = ",".join("?" for _ in selection.sessions)
            rows = cast(list[tuple[object, ...]], connection.execute(
                "SELECT session_date, path, bytes, rows, provenance, original_dataset, "
                "substituted_dataset, column_signature, optimized_path, optimized_bytes, view_schema, view_name "
                f"FROM {prefix}files WHERE layer=? AND snapshot=? AND dataset=? AND source_schema=? "
                f"AND session_date IN ({placeholders}) "
                "ORDER BY session_date,path LIMIT ?",
                [*params, *selection.sessions, config.max_files + 1],
            ).fetchall())
    except duckdb.Error:
        _fail("Catalog query or schema inspection failed", SourceErrorCode.SCHEMA)
    if len(rows) > config.max_files:
        _fail("Selected file bound exceeded", SourceErrorCode.LIMIT)
    partitions: list[ResolvedPartition] = []
    selected_paths: set[str] = set()
    optimized_paths: set[str] = set()
    signatures: set[str] = set()
    for row in rows:
        _cancel(cancellation)
        session = _date(row[0].isoformat() if type(row[0]) is date else row[0])
        original, optimized = _absolute(row[1]), _absolute(row[8])
        original_bytes, optimized_bytes, count = _count(row[2]), _count(row[9]), _count(row[3])
        if (_identifier(row[10]), _identifier(row[11])) != (view_schema, view_name):
            _fail("Selected file route conflicts with dataset")
        if original in selected_paths or optimized in optimized_paths:
            _fail("Duplicate selected file identity")
        selected_paths.add(original)
        optimized_paths.add(optimized)
        signature = hashlib.sha256(_text(row[7]).encode("utf-8")).hexdigest()
        signatures.add(signature)
        if len(signatures) > 1 or (selection.expected_schema_sha256 is not None and signature != selection.expected_schema_sha256):
            _fail("Conflicting or stale schema signature")
        pin = by_path.get(original, FilePin(original))
        partitions.append(ResolvedPartition(
            session, original, optimized, original_bytes, optimized_bytes, count, signature,
            _text(row[4]), _text(row[5]), None if row[6] is None else _text(row[6]),
            _file(original, original_bytes, pin.original_sha256, budget),
            _file(optimized, optimized_bytes, pin.optimized_sha256, budget), pin.receipt_id,
        ))
    if by_path.keys() - selected_paths:
        _fail("File pin outside selected population")
    after = budget.read(config.path)
    if before != after:
        _fail("Catalog changed during resolution")
    present = {p.session for p in partitions}
    missing = tuple(sorted(set(selection.sessions) - present))
    identity = dict(selection=asdict(selection), catalog_sha256=before,
                    view_schema=view_schema, view_name=view_name,
                    partitions=[asdict(p) for p in partitions], missing_sessions=missing)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ResolvedSource(selection, before, view_schema, view_name, tuple(partitions), missing, digest)
