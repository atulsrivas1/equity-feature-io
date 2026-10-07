"""Cooperative local manifest-last publication of complete canonical results."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import cast
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
from .projections import rows, schemas, verify_projection, write_projection

STORAGE_VERSION = "efio-parquet1"
RETENTION_NS = 7 * 86400 * 1000000000
DEFAULT_LIMITS = SinkRequirements(max_results=100, max_chunk_bytes=1048576, max_total_bytes=10485760,
                                  max_result_cells=100000, max_evidence_rows=100000)
_SUFFIXES = ("result.json", "cells.parquet", "evidence.parquet")


def _json(value: dict[str, str]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, value in items:
        if key in data:
            raise ValueError("duplicate field")
        data[key] = value
    return data


def _sync_file(path: Path) -> None:
    with path.open("rb+") as file:
        file.flush()
        os.fsync(file.fileno())


def _sync_dir(path: Path) -> None:
    # Windows lacks this directory-fsync path; no power-loss guarantee is inferred.
    if sys.platform == "linux":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


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
    artifacts: list[ArtifactReference] = field(default_factory=list)
    keys: set[tuple[str, str, str, str]] = field(default_factory=set)
    count: int = 0
    cells: int = 0
    evidence: int = 0
    size: int = 0
    failed: bool = False
    state: PublicationState = PublicationState.STAGING


class ParquetSink:
    """Serialized cooperating local writers; complete-manifest reader admission.

    Root is caller-owned. Backend never evicts tombstones, committed results or old
    partial attempts. Explicit close/abort is required for an abandoned live writer.
    """
    def __init__(self, root: Path, destination_scope: str, *, limits: SinkRequirements = DEFAULT_LIMITS,
                 max_physical_bytes: int = 67108864, max_control_bytes: int = 33554432,
                 caller_committed_at_ns: int | None = None) -> None:
        if sys.platform not in ("win32", "linux"):
            raise SinkError(SinkErrorCode.UNSUPPORTED_CAPABILITY)
        if not isinstance(root, Path) or type(limits) is not SinkRequirements:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        label(destination_scope)
        timestamp(caller_committed_at_ns)
        if any(type(n) is not int or not 1 <= n <= I64_MAX for n in (max_physical_bytes, max_control_bytes)):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if str(root).startswith(("\\\\", "//")):
            raise SinkError(SinkErrorCode.UNSUPPORTED_CAPABILITY)
        names = ("max_results", "max_chunk_bytes", "max_total_bytes", "max_result_cells", "max_evidence_rows")
        if any(getattr(limits, name) > getattr(DEFAULT_LIMITS, name) for name in names) or max_physical_bytes > 67108864 or max_control_bytes > 33554432:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        self._root = Path(os.path.abspath(root))
        self._scope = destination_scope
        self._limits = limits
        self._physical = max_physical_bytes
        self._control = max_control_bytes
        self._commit_time = caller_committed_at_ns
        self._owner = object()
        self._active: _Session | None = None
        try:
            admit_sink(self, limits)
        except FactoryError as error:
            code = SinkErrorCode.INCOMPATIBLE_VERSION if error.code is FactoryErrorCode.INCOMPATIBLE_VERSION else SinkErrorCode.UNSUPPORTED_CAPABILITY
            raise SinkError(code) from None

    def capabilities(self) -> SinkCapabilities:
        return SinkCapabilities(("1",), ("efio-json1",), ("efio-key1",), ("efio-content1",),
                                ("0.0.4a4",), ("1",), ("v1",), "manifest_last", "serialized_writer",
                                True, True, True, RETENTION_NS, self._limits.max_results,
                                self._limits.max_chunk_bytes, self._limits.max_total_bytes,
                                self._limits.max_result_cells, self._limits.max_evidence_rows)

    def _path(self, *parts: str) -> Path:
        path = self._root / ("." + STORAGE_VERSION)
        candidates = [self._root, path]
        for part in parts:
            if not part or part in (".", "..") or any(c in part for c in ("/", "\\", ":")):
                raise SinkError(SinkErrorCode.CORRUPTION)
            path /= part
            candidates.append(path)
        if any(p.is_symlink() for p in candidates):
            raise SinkError(SinkErrorCode.CORRUPTION)
        return path

    def _bytes(self, path: Path, bound: int, *, missing: SinkErrorCode = SinkErrorCode.CORRUPTION) -> bytes:
        if not path.is_file() or path.is_symlink():
            raise SinkError(missing)
        if path.stat().st_size > bound:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        with path.open("rb") as file:
            data = file.read(bound + 1)
        if len(data) > bound:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        return data

    def _control_read(self, path: Path, names: set[str]) -> dict[str, str]:
        try:
            data = self._bytes(path, self._control)
            value = json.loads(data.decode("ascii"), object_pairs_hook=_pairs)
            if type(value) is not dict or set(value) != names or any(type(v) is not str for v in value.values()):
                raise SinkError(SinkErrorCode.CORRUPTION)
            result = cast(dict[str, str], value)
            if _json(result) != data or result["schema"] != STORAGE_VERSION or re.fullmatch(r"[0-9a-f]{32}", result["attempt_id"]) is None:
                raise SinkError(SinkErrorCode.CORRUPTION)
            return result
        except SinkError:
            raise
        except Exception:
            raise SinkError(SinkErrorCode.CORRUPTION) from None

    def _control_write(self, path: Path, data: dict[str, str]) -> None:
        encoded = _json(data)
        if len(encoded) > self._control:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        temporary = self._path(path.parent.name, path.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("xb") as file:
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        _sync_dir(path.parent)

    def _reservation(self, key: str) -> tuple[PublicationEnvelope, PublicationState, str] | None:
        path = self._path(key, "reservation.json")
        if not path.exists():
            if self._path(key, "complete.json").exists():
                raise SinkError(SinkErrorCode.CORRUPTION)
            return None
        value = self._control_read(path, {"schema", "attempt_id", "envelope", "state"})
        try:
            envelope = decode_envelope(value["envelope"].encode("ascii"))
            state = PublicationState(value["state"])
            if state not in (PublicationState.STAGING, PublicationState.ABORTED) or idempotency_key(envelope.identity) != key or envelope.destination_scope != self._scope:
                raise SinkError(SinkErrorCode.CORRUPTION)
            return envelope, state, value["attempt_id"]
        except Exception:
            raise SinkError(SinkErrorCode.CORRUPTION) from None

    def _admit(self, envelope: PublicationEnvelope) -> None:
        if type(envelope) is not PublicationEnvelope or envelope.destination_scope != self._scope:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        encode_envelope(envelope)  # Exact versions/descriptor schemas before any storage access.
        try:
            admit_sink(self, envelope_requirements(envelope))
        except FactoryError as error:
            code = SinkErrorCode.INCOMPATIBLE_VERSION if error.code is FactoryErrorCode.INCOMPATIBLE_VERSION else SinkErrorCode.RESOURCE_LIMIT
            raise SinkError(code) from None
        if len(encode_envelope(envelope)) > self._control:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)

    def _complete(self, key: str) -> tuple[PublicationEnvelope, CompletionReceipt, str] | None:
        reservation = self._reservation(key)
        path = self._path(key, "complete.json")
        if not path.exists():
            return None
        value = self._control_read(path, {"schema", "attempt_id", "envelope", "receipt"})
        try:
            envelope = decode_envelope(value["envelope"].encode("ascii"))
            receipt = decode_receipt(value["receipt"].encode("ascii"))
            if reservation is None or _binding(reservation[0]) != _binding(envelope) or reservation[2] != value["attempt_id"] or idempotency_key(envelope.identity) != key:
                raise SinkError(SinkErrorCode.CORRUPTION)
            verify_receipt(receipt, envelope)
            self._materialize(envelope, receipt, value["attempt_id"])
            return envelope, receipt, value["attempt_id"]
        except SinkError as error:
            if error.code is SinkErrorCode.RESOURCE_LIMIT:
                raise
            raise SinkError(SinkErrorCode.CORRUPTION) from None
        except Exception:
            raise SinkError(SinkErrorCode.CORRUPTION) from None

    def _materialize(self, envelope: PublicationEnvelope, receipt: CompletionReceipt, attempt: str) -> tuple[FeatureResult, ...]:
        if len(receipt.artifacts) != 3 * envelope.result_count or sum(a.byte_length for a in receipt.artifacts) > self._physical:
            raise SinkError(SinkErrorCode.CORRUPTION)
        self._admit(envelope)
        reconstructed: list[FeatureResult] = []
        cell_schema, evidence_schema = schemas()
        for index in range(envelope.result_count):
            paths: list[Path] = []
            data: list[bytes] = []
            for offset, suffix in enumerate(_SUFFIXES):
                reference = receipt.artifacts[index * 3 + offset]
                filename = f"r{index:06d}.{suffix}"
                if reference.artifact_id != f"{receipt.idempotency_key}/{attempt}/{filename}":
                    raise SinkError(SinkErrorCode.CORRUPTION)
                path = self._path(receipt.idempotency_key, attempt, filename)
                if not path.is_file() or path.stat().st_size != reference.byte_length:
                    raise SinkError(SinkErrorCode.CORRUPTION)
                encoded = self._bytes(path, min(self._physical, reference.byte_length))
                if len(encoded) != reference.byte_length or hashlib.sha256(encoded).hexdigest() != reference.byte_sha256:
                    raise SinkError(SinkErrorCode.CORRUPTION)
                paths.append(path)
                data.append(encoded)
            if len(data[0]) > envelope.max_chunk_bytes:
                raise SinkError(SinkErrorCode.CORRUPTION)
            result = decode_result(data[0])
            expected_cells, expected_evidence = rows(result, index)
            verify_projection(paths[1], expected_cells, cell_schema, self._physical)
            verify_projection(paths[2], expected_evidence, evidence_schema, self._physical)
            reconstructed.append(result)
        result_tuple = tuple(reconstructed)
        verify_content(envelope, result_tuple)
        verify_receipt(receipt, envelope, result_tuple)
        return result_tuple

    def _finish(self, session: _Session, state: PublicationState) -> None:
        session.state = state
        self._active = None
        session.lock.release()

    def begin(self, envelope: PublicationEnvelope) -> WriteSession | CompletionReceipt:
        lock: WriterLock | None = None
        try:
            self._admit(envelope)
            key = idempotency_key(envelope.identity)
            previous = self._reservation(key)
            if previous is not None and _binding(previous[0]) != _binding(envelope):
                raise SinkError(SinkErrorCode.CONFLICT)
            complete = self._complete(key)
            if complete is not None:
                verify_content(envelope, self._materialize(*complete))
                if self._active is not None and self._active.key == key:
                    self._finish(self._active, PublicationState.COMMITTED)
                return complete[1]
            if self._active is not None:
                raise SinkError(SinkErrorCode.BUSY)
            self._path().mkdir(parents=True, exist_ok=True)
            lock = WriterLock(self._path("writer.lock"))
            # Re-read after exclusive acquisition: another process may have just committed.
            previous = self._reservation(key)
            if previous is not None and _binding(previous[0]) != _binding(envelope):
                raise SinkError(SinkErrorCode.CONFLICT)
            complete = self._complete(key)
            if complete is not None:
                verify_content(envelope, self._materialize(*complete))
                return complete[1]
            attempt = uuid.uuid4().hex
            self._path(key).mkdir(exist_ok=True)
            self._path(key, attempt).mkdir()
            self._control_write(self._path(key, "reservation.json"), dict(schema=STORAGE_VERSION, attempt_id=attempt,
                                state=PublicationState.STAGING.value, envelope=encode_envelope(envelope).decode("ascii")))
            session = _Session(attempt, key, envelope, self._owner, lock)
            self._active = session
            lock = None
            return session
        except SinkError:
            raise
        except Exception:
            raise SinkError(SinkErrorCode.UNAVAILABLE) from None
        finally:
            if lock is not None:
                lock.release()

    def _owned(self, session: WriteSession, *, staging: bool = True) -> _Session:
        if type(session) is not _Session or session.owner is not self._owner:
            raise SinkError(SinkErrorCode.INVALID_SESSION)
        if staging and (self._active is not session or session.state is not PublicationState.STAGING or session.failed):
            raise SinkError(SinkErrorCode.INVALID_SESSION)
        return session

    def write(self, session: WriteSession, ordinal: int, result: FeatureResult) -> None:
        attempt = self._owned(session)
        envelope = attempt.envelope
        if type(ordinal) is not int or ordinal != attempt.count or ordinal >= envelope.result_count:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        data = encode_result(result)
        if descriptor(result) != envelope.result_descriptors[ordinal]:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        cells = sum(len(c.entities) for c in result.values)
        if len(data) > envelope.max_chunk_bytes or attempt.size + len(data) > envelope.max_total_bytes or attempt.cells + cells > envelope.max_result_cells or attempt.evidence + len(result.evidence) > envelope.max_evidence_rows:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        keys = {(result.metadata.namespace, entity.instrument_id, entity.session_id, c.feature_id)
                for c in result.values for entity in c.entities}
        if keys & attempt.keys:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        try:
            paths = [self._path(attempt.key, attempt.attempt_id, f"r{ordinal:06d}.{suffix}") for suffix in _SUFFIXES]
            used = sum(a.byte_length for a in attempt.artifacts)
            if used + len(data) > self._physical:
                raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
            with paths[0].open("xb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            cell_rows, evidence_rows = rows(result, ordinal)
            cell_schema, evidence_schema = schemas()
            for path, values, schema in zip(paths[1:], (cell_rows, evidence_rows), (cell_schema, evidence_schema), strict=True):
                remaining = self._physical - used - sum(p.stat().st_size for p in paths if p.exists())
                write_projection(path, values, schema, remaining)
                _sync_file(path)
            references: list[ArtifactReference] = []
            for path in paths:
                encoded = self._bytes(path, self._physical)
                references.append(ArtifactReference(f"{attempt.key}/{attempt.attempt_id}/{path.name}", hashlib.sha256(encoded).hexdigest(), len(encoded)))
            if sum(a.byte_length for a in attempt.artifacts + references) > self._physical:
                raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
            _sync_dir(paths[0].parent)
            attempt.artifacts.extend(references)
            attempt.keys.update(keys)
            attempt.count += 1
            attempt.cells += cells
            attempt.evidence += len(result.evidence)
            attempt.size += len(data)
        except SinkError:
            attempt.failed = True
            raise
        except Exception:
            attempt.failed = True
            raise SinkError(SinkErrorCode.UNAVAILABLE) from None

    def commit(self, session: WriteSession) -> CompletionReceipt:
        attempt = self._owned(session)
        envelope = attempt.envelope
        if attempt.count != envelope.result_count:
            raise SinkError(SinkErrorCode.CONFLICT)
        receipt = CompletionReceipt(envelope.identity, attempt.key, envelope.expected_content_sha256,
                                    envelope.result_count, envelope.cell_count, envelope.evidence_count,
                                    envelope.content_bytes, tuple(attempt.artifacts), self._commit_time)
        try:
            self._materialize(envelope, receipt, attempt.attempt_id)
            self._control_write(self._path(attempt.key, "complete.json"), dict(schema=STORAGE_VERSION,
                                attempt_id=attempt.attempt_id, envelope=encode_envelope(envelope).decode("ascii"),
                                receipt=encode_receipt(receipt).decode("ascii")))
            self._finish(attempt, PublicationState.COMMITTED)
            return receipt
        except SinkError:
            raise
        except Exception:
            raise SinkError(SinkErrorCode.COMMIT_UNKNOWN, attempt.key, attempt.attempt_id) from None

    def abort(self, session: WriteSession) -> AbortOutcome:
        attempt = self._owned(session, staging=False)
        try:
            complete = self._complete(attempt.key)
            if complete is not None:
                if self._active is attempt:
                    self._finish(attempt, PublicationState.COMMITTED)
                return AbortOutcome(PublicationState.COMMITTED, complete[1])
            previous = self._reservation(attempt.key)
            if previous is None or previous[2] != attempt.attempt_id:
                raise SinkError(SinkErrorCode.INVALID_SESSION)
            if attempt.state is PublicationState.ABORTED and previous[1] is PublicationState.ABORTED:
                return AbortOutcome(PublicationState.ABORTED, None)
            if self._active is not attempt:
                raise SinkError(SinkErrorCode.INVALID_SESSION)
            self._control_write(self._path(attempt.key, "reservation.json"), dict(schema=STORAGE_VERSION,
                                attempt_id=attempt.attempt_id, state=PublicationState.ABORTED.value,
                                envelope=encode_envelope(attempt.envelope).decode("ascii")))
            self._finish(attempt, PublicationState.ABORTED)
            return AbortOutcome(PublicationState.ABORTED, None)
        except SinkError:
            raise
        except Exception:
            return AbortOutcome(PublicationState.UNKNOWN, None)

    def lookup(self, idempotency_key: str) -> PublicationStatus:
        digest(idempotency_key)
        try:
            complete = self._complete(idempotency_key)
            if complete is not None:
                if self._active is not None and self._active.key == idempotency_key:
                    self._finish(self._active, PublicationState.COMMITTED)
                return PublicationStatus(PublicationState.COMMITTED, complete[1])
            reservation = self._reservation(idempotency_key)
            return PublicationStatus(PublicationState.ABSENT if reservation is None else reservation[1], None)
        except SinkError:
            raise
        except Exception:
            raise SinkError(SinkErrorCode.UNAVAILABLE) from None

    def read(self, receipt: CompletionReceipt) -> tuple[FeatureResult, ...]:
        verify_receipt(receipt)
        if receipt.identity.destination_scope != self._scope:
            raise SinkError(SinkErrorCode.CORRUPTION)
        try:
            complete = self._complete(receipt.idempotency_key)
            if complete is None or encode_receipt(receipt) != encode_receipt(complete[1]):
                raise SinkError(SinkErrorCode.CORRUPTION)
            return self._materialize(*complete)
        except SinkError as error:
            if error.code is SinkErrorCode.RESOURCE_LIMIT:
                raise
            raise SinkError(SinkErrorCode.CORRUPTION) from None
        except Exception:
            raise SinkError(SinkErrorCode.CORRUPTION) from None

    def close(self) -> None:
        if self._active is not None:
            attempt = self._active
            try:
                self.abort(attempt)
            finally:
                if self._active is attempt:
                    self._active = None
                    attempt.failed = True
                    attempt.lock.release()

    def __enter__(self) -> ParquetSink:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
