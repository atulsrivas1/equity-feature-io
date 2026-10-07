"""Exclusive local attempts with immutable row-BLOB receipts and atomic SQL commit."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import sys
from threading import RLock
from typing import Iterator, cast
import uuid

from equity_feature_contracts.inputs import I64_MAX
from equity_feature_contracts.results import FeatureResult
from equity_feature_io_contracts import FactoryError, FactoryErrorCode, SinkRequirements
from equity_feature_io_contracts.publication import (
    AbortOutcome, ArtifactReference, CompletionReceipt, PublicationEnvelope,
    PublicationState, PublicationStatus, SinkCapabilities, SinkError, SinkErrorCode, WriteSession,
    digest, label, timestamp,
)
from equity_feature_io_sdk.codec import (
    decode_envelope, decode_receipt, decode_result, descriptor, encode_envelope,
    encode_receipt, encode_result, idempotency_key,
)
from equity_feature_io_sdk.factories import admit_sink
from equity_feature_io_sdk.publication import envelope_requirements, verify_content, verify_receipt

from .locking import WriterLock
from .projections import admit_projection, bundle, exact, rows
from .schema import CELL_FIELDS, EVIDENCE_FIELDS, Connection, STORAGE_VERSION, connect, create, engine_error, preflight

RETENTION_NS = 7 * 86400 * 1000000000
DEFAULT_LIMITS = SinkRequirements(max_results=100, max_chunk_bytes=1048576, max_total_bytes=10485760,
                                  max_result_cells=100000, max_evidence_rows=100000)
SUFFIXES = ("result", "cells", "evidence")


def _binding(envelope: PublicationEnvelope) -> tuple[object, ...]:
    return (envelope.identity, envelope.expected_content_sha256, envelope.result_count,
            envelope.cell_count, envelope.evidence_count, envelope.content_bytes)


@dataclass(eq=False)
class _Session:
    attempt_id: str
    key: str
    envelope: PublicationEnvelope
    owner: object
    lock: WriterLock
    control: Connection
    data: Connection
    artifacts: list[ArtifactReference] = field(default_factory=list)
    keys: set[tuple[str, str, str, str]] = field(default_factory=set)
    count: int = 0
    cells: int = 0
    evidence: int = 0
    size: int = 0
    failed: bool = False
    transaction: bool = True
    state: PublicationState = PublicationState.STAGING


class DuckDBSink:
    """Caller-owned local output; serialized cooperative process handoff only.

    Connections are closed before the stable OS lease is released. No automatic
    eviction, source writes, extension discovery or whole-file digest guarantee.
    """
    def __init__(self, output_path: Path, destination_scope: str, *, limits: SinkRequirements = DEFAULT_LIMITS,
                 max_projection_bytes: int = 67108864, max_control_bytes: int = 33554432,
                 caller_committed_at_ns: int | None = None) -> None:
        if sys.platform not in ("win32", "linux"):
            raise SinkError(SinkErrorCode.UNSUPPORTED_CAPABILITY)
        if not isinstance(output_path, Path) or type(limits) is not SinkRequirements:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        label(destination_scope)
        timestamp(caller_committed_at_ns)
        if str(output_path).startswith(("\\\\", "//")) or "://" in str(output_path) or output_path.name == ":memory:":
            raise SinkError(SinkErrorCode.UNSUPPORTED_CAPABILITY)
        if not output_path.name or any(ord(c) < 32 for c in str(output_path)):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if any(type(n) is not int or not 1 <= n <= I64_MAX for n in (max_projection_bytes, max_control_bytes)):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        names = ("max_results", "max_chunk_bytes", "max_total_bytes", "max_result_cells", "max_evidence_rows")
        if any(getattr(limits, name) > getattr(DEFAULT_LIMITS, name) for name in names) or max_projection_bytes > 67108864 or max_control_bytes > 33554432:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        self._path = Path(os.path.abspath(output_path))
        self._scope = destination_scope
        self._limits = limits
        self._projection = max_projection_bytes
        self._control_bound = max_control_bytes
        self._commit_time = caller_committed_at_ns
        self._owner = object()
        self._active: _Session | None = None
        self._mutex = RLock()
        self._validate_path()
        try:
            admit_sink(self, limits)
        except FactoryError as error:
            raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION if error.code is FactoryErrorCode.INCOMPATIBLE_VERSION else SinkErrorCode.UNSUPPORTED_CAPABILITY) from None

    def capabilities(self) -> SinkCapabilities:
        return SinkCapabilities(("1",), ("efio-json1",), ("efio-key1",), ("efio-content1",),
                                ("0.0.4a4",), ("1",), ("v1",), "transactional", "serialized_writer",
                                True, True, True, RETENTION_NS, self._limits.max_results,
                                self._limits.max_chunk_bytes, self._limits.max_total_bytes,
                                self._limits.max_result_cells, self._limits.max_evidence_rows)

    def _validate_path(self) -> None:
        lock_path = self._path.with_name(self._path.name + ".efio-duckdb1.lock")
        if any(p.is_symlink() for p in (self._path, Path(str(self._path)+'.wal'), lock_path, *self._path.parents)):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if self._path.exists() and not self._path.is_file():
            raise SinkError(SinkErrorCode.INVALID_CONFIG)

    def _lease(self) -> WriterLock:
        self._validate_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        return WriterLock(self._path.with_name(self._path.name + ".efio-duckdb1.lock"))

    def _admit(self, envelope: PublicationEnvelope) -> None:
        if type(envelope) is not PublicationEnvelope or envelope.destination_scope != self._scope:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        encoded = encode_envelope(envelope)
        try:
            admit_sink(self, envelope_requirements(envelope))
        except FactoryError as error:
            raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION if error.code is FactoryErrorCode.INCOMPATIBLE_VERSION else SinkErrorCode.RESOURCE_LIMIT) from None
        if len(encoded) > self._control_bound:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)

    def _existing(self) -> None:
        # This must finish before any write connection opens on an existing file.
        connection = connect(str(self._path), read_only=True)
        try:
            preflight(connection)
        finally:
            connection.close()

    def _bootstrap(self) -> None:
        temporary = self._path.with_name(self._path.name + "." + uuid.uuid4().hex + ".bootstrap")
        connection = connect(str(temporary))
        try:
            create(connection)
        finally:
            connection.close()
        # Exclusive cooperating lease; adversarial namespace replacement is unqualified.
        if self._path.exists():
            raise SinkError(SinkErrorCode.CONFLICT)
        os.rename(temporary, self._path)

    def _reservation(self, connection: Connection, key: str) -> tuple[PublicationEnvelope, PublicationState, str] | None:
        lengths = connection.execute("SELECT octet_length(envelope),length(state),length(attempt) FROM efio_reservations WHERE pub_key=?", [key]).fetchall()
        if not lengths:
            return None
        if len(lengths) != 1 or any(type(v) is not int for v in lengths[0]) or cast(int, lengths[0][0]) > self._control_bound or cast(int, lengths[0][1]) > 16 or lengths[0][2] != 32:
            raise SinkError(SinkErrorCode.CORRUPTION)
        found = connection.execute("SELECT envelope,state,attempt FROM efio_reservations WHERE pub_key=?", [key]).fetchall()[0]
        envelope = decode_envelope(cast(bytes, found[0]))
        state = PublicationState(cast(str, found[1]))
        attempt = cast(str, found[2])
        if state not in (PublicationState.STAGING, PublicationState.ABORTED, PublicationState.COMMITTED) or re.fullmatch(r"[0-9a-f]{32}", attempt) is None or idempotency_key(envelope.identity) != key:
            raise SinkError(SinkErrorCode.CORRUPTION)
        self._admit(envelope)
        return envelope, state, attempt

    def _complete(self, connection: Connection, key: str) -> tuple[PublicationEnvelope, CompletionReceipt, str] | None:
        try:
            return self._verified_complete(connection, key)
        except SinkError as error:
            if error.code is SinkErrorCode.RESOURCE_LIMIT:
                raise
            raise SinkError(SinkErrorCode.CORRUPTION) from None
        except Exception as error:
            raise engine_error(error, SinkErrorCode.CORRUPTION) from None

    def _verified_complete(self, connection: Connection, key: str) -> tuple[PublicationEnvelope, CompletionReceipt, str] | None:
        reservation = self._reservation(connection, key)
        lengths = connection.execute("SELECT octet_length(envelope),octet_length(receipt) FROM efio_completions WHERE pub_key=?", [key]).fetchall()
        if not lengths:
            if reservation is not None and reservation[1] is PublicationState.COMMITTED:
                raise SinkError(SinkErrorCode.CORRUPTION)
            return None
        if reservation is None or reservation[1] is not PublicationState.COMMITTED or len(lengths) != 1 or any(type(v) is not int or v > self._control_bound for v in lengths[0]):
            raise SinkError(SinkErrorCode.CORRUPTION)
        found = connection.execute("SELECT envelope,receipt,attempt FROM efio_completions WHERE pub_key=?", [key]).fetchall()[0]
        envelope, receipt = decode_envelope(cast(bytes, found[0])), decode_receipt(cast(bytes, found[1]))
        attempt = cast(str, found[2])
        if _binding(envelope) != _binding(reservation[0]) or attempt != reservation[2]:
            raise SinkError(SinkErrorCode.CORRUPTION)
        verify_receipt(receipt, envelope)
        self._materialize(connection, envelope, receipt, attempt)
        return envelope, receipt, attempt

    def _materialize(self, connection: Connection, envelope: PublicationEnvelope, receipt: CompletionReceipt, attempt: str) -> tuple[FeatureResult, ...]:
        self._admit(envelope)
        verify_receipt(receipt, envelope)
        if len(receipt.artifacts) != 3 * envelope.result_count or sum(a.byte_length for a in receipt.artifacts) > self._projection:
            raise SinkError(SinkErrorCode.CORRUPTION)
        key = receipt.idempotency_key
        params = [key, attempt]
        if connection.execute("SELECT count(*) FROM efio_results WHERE pub_key=? AND attempt=?",params).fetchall() != [(envelope.result_count,)]:
            raise SinkError(SinkErrorCode.CORRUPTION)
        lengths = connection.execute("SELECT result_ordinal,octet_length(record),octet_length(cells_bundle),octet_length(evidence_bundle) FROM efio_results WHERE pub_key=? AND attempt=? ORDER BY result_ordinal", params).fetchall()
        if len(lengths) != envelope.result_count or any(row[0] != index for index, row in enumerate(lengths)):
            raise SinkError(SinkErrorCode.CORRUPTION)
        for index, row in enumerate(lengths):
            for offset, size in enumerate(row[1:]):
                reference = receipt.artifacts[index * 3 + offset]
                if type(size) is not int or size != reference.byte_length or reference.artifact_id != f"{key}/{attempt}/r{index:06d}.{SUFFIXES[offset]}":
                    raise SinkError(SinkErrorCode.CORRUPTION)
            if cast(int, row[1]) > envelope.max_chunk_bytes:
                raise SinkError(SinkErrorCode.CORRUPTION)
        # Bound repeated variable SQL payload BEFORE fetching rows or BLOBs.
        for table, fields, count in (("efio_cells", CELL_FIELDS, envelope.cell_count),
                                     ("efio_evidence", EVIDENCE_FIELDS, envelope.evidence_count)):
            sizes = [f"coalesce(octet_length(encode({name})),0)" if dtype == "VARCHAR" else
                     f"coalesce(octet_length({name}),0)" if dtype == "BLOB" else
                     f"coalesce(length({name}),0)*64+coalesce(length(array_to_string({name},'')),0)*6" if dtype == "VARCHAR[]" else "32"
                     for name, dtype in fields]
            bounded = connection.execute(f"SELECT count(*),coalesce(sum({'+'.join(sizes)}),0) FROM {table} WHERE pub_key=? AND attempt=?", params).fetchall()[0]
            if bounded[0] != count or cast(int, bounded[1]) > self._projection:
                raise SinkError(SinkErrorCode.CORRUPTION)
        reconstructed: list[FeatureResult] = []
        for index in range(envelope.result_count):
            data = connection.execute("SELECT record,cells_bundle,evidence_bundle FROM efio_results WHERE pub_key=? AND attempt=? AND result_ordinal=?", [key, attempt, index]).fetchall()[0]
            for offset, encoded in enumerate(data):
                reference = receipt.artifacts[index * 3 + offset]
                if type(encoded) is not bytes or hashlib.sha256(encoded).hexdigest() != reference.byte_sha256:
                    raise SinkError(SinkErrorCode.CORRUPTION)
            result = decode_result(cast(bytes, data[0]))
            admit_projection(result, self._projection)
            cells, evidence = rows(result, index)
            for offset, (table, projection_fields, expected, order) in enumerate((
                    ("efio_cells", CELL_FIELDS, cells, "column_ordinal,entity_ordinal"),
                    ("efio_evidence", EVIDENCE_FIELDS, evidence, "evidence_ordinal")), start=1):
                if bundle(expected, projection_fields) != data[offset]:
                    raise SinkError(SinkErrorCode.CORRUPTION)
                observed = connection.execute(f"SELECT {','.join(name for name, _ in projection_fields)} FROM {table} WHERE pub_key=? AND attempt=? AND result_ordinal=? ORDER BY {order}", [key, attempt, index]).fetchall()
                wanted = [tuple(row[name] for name, _ in projection_fields) for row in expected]
                if exact(observed) != exact(wanted):
                    raise SinkError(SinkErrorCode.CORRUPTION)
            reconstructed.append(result)
        result_tuple = tuple(reconstructed)
        verify_content(envelope, result_tuple)
        verify_receipt(receipt, envelope, result_tuple)
        return result_tuple

    def _finish(self, session: _Session, state: PublicationState) -> None:
        # Nested finally ensures both engine handles precede kernel lease release.
        try:
            session.data.close()
        finally:
            try:
                session.control.close()
            finally:
                session.state = state
                self._active = None
                session.lock.release()

    def begin(self, envelope: PublicationEnvelope) -> WriteSession | CompletionReceipt:
        with self._mutex:
            self._admit(envelope)
            key = idempotency_key(envelope.identity)
            if self._active is not None:
                if self._active.key == key and _binding(envelope) != _binding(self._active.envelope):
                    raise SinkError(SinkErrorCode.CONFLICT)
                raise SinkError(SinkErrorCode.BUSY)
            lock: WriterLock | None = None
            control: Connection | None = None
            data: Connection | None = None
            try:
                lock = self._lease()
                if self._path.exists():
                    self._existing()
                else:
                    self._bootstrap()
                control = connect(str(self._path))
                previous = self._reservation(control, key)
                if previous is not None and _binding(previous[0]) != _binding(envelope):
                    raise SinkError(SinkErrorCode.CONFLICT)
                complete = self._complete(control, key)
                if complete is not None:
                    return complete[1]
                attempt = uuid.uuid4().hex
                control.execute("INSERT INTO efio_reservations VALUES (?,?,?,?) ON CONFLICT(pub_key) DO UPDATE SET attempt=excluded.attempt,state=excluded.state,envelope=excluded.envelope",
                                [key, attempt, PublicationState.STAGING.value, encode_envelope(envelope)])
                data = connect(str(self._path))
                data.execute("BEGIN TRANSACTION")
                session = _Session(attempt, key, envelope, self._owner, lock, control, data)
                self._active = session
                lock, control, data = None, None, None
                return session
            except SinkError:
                raise
            except Exception as error:
                raise engine_error(error, SinkErrorCode.UNAVAILABLE) from None
            finally:
                try:
                    if data is not None:
                        data.close()
                finally:
                    try:
                        if control is not None:
                            control.close()
                    finally:
                        if lock is not None:
                            lock.release()

    def _owned(self, session: WriteSession, *, staging: bool = True) -> _Session:
        if type(session) is not _Session or session.owner is not self._owner:
            raise SinkError(SinkErrorCode.INVALID_SESSION)
        if staging and (self._active is not session or session.failed or session.state is not PublicationState.STAGING):
            raise SinkError(SinkErrorCode.INVALID_SESSION)
        return session

    def write(self, session: WriteSession, ordinal: int, result: FeatureResult) -> None:
        with self._mutex:
            attempt = self._owned(session)
            envelope = attempt.envelope
            if type(ordinal) is not int or ordinal != attempt.count or ordinal >= envelope.result_count:
                raise SinkError(SinkErrorCode.INVALID_CONTENT)
            encoded = encode_result(result)
            if descriptor(result) != envelope.result_descriptors[ordinal]:
                raise SinkError(SinkErrorCode.INVALID_CONTENT)
            cell_count = sum(len(c.entities) for c in result.values)
            if len(encoded) > envelope.max_chunk_bytes or attempt.size + len(encoded) > envelope.max_total_bytes or attempt.cells + cell_count > envelope.max_result_cells or attempt.evidence + len(result.evidence) > envelope.max_evidence_rows:
                raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
            keys = {(result.metadata.namespace, entity.instrument_id, entity.session_id, c.feature_id)
                    for c in result.values for entity in c.entities}
            if keys & attempt.keys:
                raise SinkError(SinkErrorCode.INVALID_CONTENT)
            remaining = self._projection - sum(a.byte_length for a in attempt.artifacts) - len(encoded)
            admit_projection(result, remaining)
            cells, evidence = rows(result, ordinal)
            blobs = (encoded, bundle(cells, CELL_FIELDS), bundle(evidence, EVIDENCE_FIELDS))
            if sum(map(len, blobs)) > remaining + len(encoded):
                raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
            try:
                attempt.data.execute("INSERT INTO efio_results VALUES (?,?,?,?,?,?)", [attempt.key, attempt.attempt_id, ordinal, *blobs])
                for table, fields, records in (("efio_cells", CELL_FIELDS, cells), ("efio_evidence", EVIDENCE_FIELDS, evidence)):
                    if records:
                        parameters = [[attempt.key, attempt.attempt_id, *(row[name] for name, _ in fields)] for row in records]
                        attempt.data.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in range(2 + len(fields)))})", parameters)
                attempt.artifacts.extend(ArtifactReference(f"{attempt.key}/{attempt.attempt_id}/r{ordinal:06d}.{suffix}", hashlib.sha256(blob).hexdigest(), len(blob))
                                         for suffix, blob in zip(SUFFIXES, blobs, strict=True))
                attempt.keys.update(keys)
                attempt.count += 1
                attempt.cells += cell_count
                attempt.evidence += len(result.evidence)
                attempt.size += len(encoded)
            except Exception as error:
                attempt.failed = True
                raise engine_error(error, SinkErrorCode.UNAVAILABLE) from None

    def commit(self, session: WriteSession) -> CompletionReceipt:
        with self._mutex:
            attempt = self._owned(session)
            e = attempt.envelope
            if attempt.count != e.result_count:
                raise SinkError(SinkErrorCode.CONFLICT)
            receipt = CompletionReceipt(e.identity, attempt.key, e.expected_content_sha256,
                                        e.result_count, e.cell_count, e.evidence_count, e.content_bytes,
                                        tuple(attempt.artifacts), self._commit_time)
            encoded = encode_receipt(receipt)
            if len(encoded) > self._control_bound:
                raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
            try:
                self._materialize(attempt.data, e, receipt, attempt.attempt_id)
                attempt.data.execute("INSERT INTO efio_completions VALUES (?,?,?,?)", [attempt.key, attempt.attempt_id, encode_envelope(e), encoded])
                attempt.data.execute("UPDATE efio_reservations SET state=? WHERE pub_key=?", [PublicationState.COMMITTED.value, attempt.key])
                attempt.data.execute("COMMIT")
                attempt.transaction = False
                # Control runs ONLY autocommit statements, hence no retained old snapshot.
                complete = self._complete(attempt.control, attempt.key)
                if complete is None:
                    raise SinkError(SinkErrorCode.COMMIT_UNKNOWN, attempt.key, attempt.attempt_id)
                self._finish(attempt, PublicationState.COMMITTED)
                return complete[1]
            except SinkError:
                raise
            except Exception:
                raise SinkError(SinkErrorCode.COMMIT_UNKNOWN, attempt.key, attempt.attempt_id) from None

    @contextmanager
    def _reader(self) -> Iterator[Connection | None]:
        if self._active is not None:
            yield self._active.control
            return
        if not self._path.exists():
            # A live bootstrap writer still owns the stable lease.
            lock = self._lease()
            try:
                if not self._path.exists():
                    yield None
                    return
            finally:
                lock.release()
        lock = self._lease()
        connection: Connection | None = None
        try:
            connection = connect(str(self._path), read_only=True)
            preflight(connection)
            yield connection
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                lock.release()

    def lookup(self, idempotency_key: str) -> PublicationStatus:
        digest(idempotency_key)
        with self._mutex:
            try:
                with self._reader() as connection:
                    if connection is None:
                        return PublicationStatus(PublicationState.ABSENT, None)
                    complete = self._complete(connection, idempotency_key)
                    if complete is None:
                        reserved = self._reservation(connection, idempotency_key)
                        return PublicationStatus(PublicationState.ABSENT if reserved is None else reserved[1], None)
                    status = PublicationStatus(PublicationState.COMMITTED, complete[1])
                if self._active is not None and self._active.key == idempotency_key:
                    self._finish(self._active, PublicationState.COMMITTED)
                return status
            except SinkError:
                raise
            except Exception as error:
                raise engine_error(error, SinkErrorCode.CORRUPTION) from None

    def read(self, receipt: CompletionReceipt) -> tuple[FeatureResult, ...]:
        verify_receipt(receipt)
        if receipt.identity.destination_scope != self._scope:
            raise SinkError(SinkErrorCode.CORRUPTION)
        with self._mutex:
            try:
                with self._reader() as connection:
                    if connection is None:
                        raise SinkError(SinkErrorCode.CORRUPTION)
                    complete = self._complete(connection, receipt.idempotency_key)
                    if complete is None or encode_receipt(complete[1]) != encode_receipt(receipt):
                        raise SinkError(SinkErrorCode.CORRUPTION)
                    return self._materialize(connection, *complete)
            except SinkError:
                raise
            except Exception as error:
                raise engine_error(error, SinkErrorCode.CORRUPTION) from None

    def abort(self, session: WriteSession) -> AbortOutcome:
        with self._mutex:
            attempt = self._owned(session, staging=False)
            status = self.lookup(attempt.key)
            if status.state is PublicationState.COMMITTED:
                return AbortOutcome(PublicationState.COMMITTED, status.receipt)
            if attempt.state is PublicationState.ABORTED and self._active is not attempt:
                with self._reader() as connection:
                    previous = None if connection is None else self._reservation(connection, attempt.key)
                    if previous is not None and previous[2] == attempt.attempt_id and previous[1] is PublicationState.ABORTED:
                        return AbortOutcome(PublicationState.ABORTED, None)
                raise SinkError(SinkErrorCode.INVALID_SESSION)
            if self._active is not attempt:
                raise SinkError(SinkErrorCode.INVALID_SESSION)
            try:
                if attempt.transaction:
                    attempt.data.execute("ROLLBACK")
                    attempt.transaction = False
                attempt.control.execute("UPDATE efio_reservations SET state=? WHERE pub_key=? AND attempt=?", [PublicationState.ABORTED.value, attempt.key, attempt.attempt_id])
                self._finish(attempt, PublicationState.ABORTED)
                return AbortOutcome(PublicationState.ABORTED, None)
            except Exception:
                return AbortOutcome(PublicationState.UNKNOWN, None)

    def close(self) -> None:
        with self._mutex:
            if self._active is not None:
                attempt = self._active
                try:
                    self.abort(attempt)
                finally:
                    if self._active is attempt:
                        attempt.failed = True
                        self._finish(attempt, PublicationState.UNKNOWN)

    def __enter__(self) -> DuckDBSink:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
