"""Bounded logical preparation, receipt checks and conservative sink lifecycle."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from typing import Protocol

from equity_feature_contracts.results import FeatureResult
from equity_feature_io_contracts import FactoryError, SinkRequirements
from equity_feature_io_contracts.publication import (
    AbortOutcome, CompletionReceipt, PublicationEnvelope, PublicationIdentity, PublicationState, PublicationStatus,
    ResultSink, SinkError, SinkErrorCode, WriteSession,
)
from .codec import content_digest, descriptor, encode_result, idempotency_key
from .factories import admit_sink

_VERSIONS = ("1", "efio-json1", "efio-key1", "efio-content1", "0.0.4a4", "1", "v1")
_VERSION_FIELDS = ("protocol_version", "codec_version", "identity_version", "digest_version", "canonical_package_version", "canonical_schema_version", "math_policy_version")


class Cancellation(Protocol):
    def is_cancelled(self) -> bool: ...


def _versions(identity: PublicationIdentity) -> None:
    if tuple(getattr(identity, key) for key in _VERSION_FIELDS) != _VERSIONS:
        raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)
    if any(d.metadata.schema_version != identity.canonical_schema_version or
           d.metadata.math_policy_version != identity.math_policy_version or
           any(h.schema_version != identity.canonical_schema_version for h in d.features)
           for d in identity.result_descriptors):
        raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)


def _inventory(results: tuple[FeatureResult, ...], limits: SinkRequirements) -> tuple[int, int, int]:
    if type(results) is not tuple:
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    if len(results) > limits.max_results:
        raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
    cells = evidence = size = 0
    keys: set[tuple[str, str, str, str]] = set()
    for result in results:
        data = encode_result(result)
        if len(data) > limits.max_chunk_bytes:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        cells += sum(len(c.entities) for c in result.values)
        evidence += len(result.evidence)
        size += len(data)
        if cells > limits.max_result_cells or evidence > limits.max_evidence_rows or size > limits.max_total_bytes:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        for column in result.values:
            for entity in column.entities:
                key = (result.metadata.namespace, entity.instrument_id, entity.session_id, column.feature_id)
                if key in keys:
                    raise SinkError(SinkErrorCode.INVALID_CONTENT)
                keys.add(key)
    return cells, evidence, size


def prepare_publication(results: tuple[FeatureResult, ...], *, destination_scope: str,
                        generation_id: str, job_id: str, partition_id: str,
                        limits: SinkRequirements, supersedes_key: str | None = None,
                        caller_created_at_ns: int | None = None) -> PublicationEnvelope:
    """One complete FeatureResult per write; no fragmented rows or lazy content."""
    # Frozen wire envelopes carry limits, not requested storage guarantees.
    # Such requirements must be supplied explicitly to publish, never silently lost.
    if limits.visibility is not None or limits.writer_mode is not None or limits.reservation_retention_ns != 1:
        raise SinkError(SinkErrorCode.UNSUPPORTED_CAPABILITY)
    cells, evidence, size = _inventory(results, limits)
    identity = PublicationIdentity(**{f: getattr(limits, f) for f in _VERSION_FIELDS},
                                   destination_scope=destination_scope, generation_id=generation_id,
                                   job_id=job_id, partition_id=partition_id,
                                   result_descriptors=tuple(descriptor(r) for r in results), supersedes_key=supersedes_key)
    _versions(identity)
    for result in results:
        if result.metadata.schema_version != identity.canonical_schema_version or result.metadata.math_policy_version != identity.math_policy_version:
            raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)
    return PublicationEnvelope(**{f.name: getattr(identity, f.name) for f in fields(PublicationIdentity)},
                               expected_content_sha256=content_digest(results), result_count=len(results),
                               cell_count=cells, evidence_count=evidence, content_bytes=size,
                               max_results=limits.max_results, max_chunk_bytes=limits.max_chunk_bytes,
                               max_total_bytes=limits.max_total_bytes, max_result_cells=limits.max_result_cells,
                               max_evidence_rows=limits.max_evidence_rows, caller_created_at_ns=caller_created_at_ns)


def envelope_requirements(envelope: PublicationEnvelope) -> SinkRequirements:
    return SinkRequirements(**{f: getattr(envelope, f) for f in _VERSION_FIELDS},
                            max_results=envelope.max_results, max_chunk_bytes=envelope.max_chunk_bytes,
                            max_total_bytes=envelope.max_total_bytes, max_result_cells=envelope.max_result_cells,
                            max_evidence_rows=envelope.max_evidence_rows)


def verify_content(envelope: PublicationEnvelope, results: tuple[FeatureResult, ...]) -> None:
    if type(envelope) is not PublicationEnvelope:
        raise SinkError(SinkErrorCode.INVALID_CONFIG)
    _versions(envelope.identity)
    cells, evidence, size = _inventory(results, envelope_requirements(envelope))
    if tuple(descriptor(r) for r in results) != envelope.result_descriptors or (len(results), cells, evidence, size, content_digest(results)) != (envelope.result_count, envelope.cell_count, envelope.evidence_count, envelope.content_bytes, envelope.expected_content_sha256):
        raise SinkError(SinkErrorCode.CONFLICT)


def verify_receipt(receipt: CompletionReceipt, envelope: PublicationEnvelope | None = None,
                   results: tuple[FeatureResult, ...] | None = None) -> None:
    try:
        if type(receipt) is not CompletionReceipt:
            raise SinkError(SinkErrorCode.CORRUPTION)
        _versions(receipt.identity)
        if receipt.idempotency_key != idempotency_key(receipt.identity):
            raise SinkError(SinkErrorCode.CORRUPTION)
        if envelope is not None:
            if receipt.identity != envelope.identity or (receipt.content_sha256, receipt.result_count, receipt.cell_count, receipt.evidence_count, receipt.content_bytes) != (envelope.expected_content_sha256, envelope.result_count, envelope.cell_count, envelope.evidence_count, envelope.content_bytes):
                raise SinkError(SinkErrorCode.CORRUPTION)
        if results is not None:
            # Construct bounded checks from the actual receipt, without trusting a supplied digest.
            limit = SinkRequirements(max_results=max(1, receipt.result_count),
                                     max_chunk_bytes=max(1, receipt.content_bytes), max_total_bytes=max(1, receipt.content_bytes),
                                     max_result_cells=receipt.cell_count, max_evidence_rows=receipt.evidence_count)
            cells, evidence, size = _inventory(results, limit)
            if tuple(descriptor(r) for r in results) != receipt.identity.result_descriptors or (len(results), cells, evidence, size, content_digest(results)) != (receipt.result_count, receipt.cell_count, receipt.evidence_count, receipt.content_bytes, receipt.content_sha256):
                raise SinkError(SinkErrorCode.CORRUPTION)
    except Exception:
        raise SinkError(SinkErrorCode.CORRUPTION) from None


def _call(operation: Callable[[], CompletionReceipt], code: SinkErrorCode) -> CompletionReceipt:
    try:
        return operation()
    except SinkError as error:
        raise SinkError(error.code, error.idempotency_key, error.attempt_id) from None
    except Exception:
        raise SinkError(code) from None


def _confirmed(sink: ResultSink, envelope: PublicationEnvelope,
               results: tuple[FeatureResult, ...]) -> CompletionReceipt:
    # A failed/unknown lookup never establishes absence or rollback.
    try:
        status = sink.lookup(idempotency_key(envelope.identity))
    except Exception:
        raise SinkError(SinkErrorCode.COMMIT_UNKNOWN) from None
    if type(status) is not PublicationStatus or status.state is not PublicationState.COMMITTED or status.receipt is None:
        raise SinkError(SinkErrorCode.COMMIT_UNKNOWN)
    verify_receipt(status.receipt, envelope, results)
    return status.receipt


def _abort(sink: ResultSink, session: WriteSession, envelope: PublicationEnvelope,
           results: tuple[FeatureResult, ...]) -> CompletionReceipt | None:
    try:
        outcome = sink.abort(session)
    except Exception:
        raise SinkError(SinkErrorCode.COMMIT_UNKNOWN) from None
    if type(outcome) is not AbortOutcome:
        raise SinkError(SinkErrorCode.COMMIT_UNKNOWN)
    if outcome.state is PublicationState.COMMITTED and outcome.receipt is not None:
        verify_receipt(outcome.receipt, envelope, results)
        return outcome.receipt
    if outcome.state is PublicationState.ABORTED:
        return None
    return _confirmed(sink, envelope, results)


def publish(sink: ResultSink, envelope: PublicationEnvelope, results: tuple[FeatureResult, ...],
            *, requirements: SinkRequirements | None = None,
            cancellation: Cancellation | None = None) -> CompletionReceipt:
    """Publication only; no worker claims, schedules, catalogs or assumed exactly-once."""
    verify_content(envelope, results)
    if requirements is not None:
        if type(requirements) is not SinkRequirements:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if tuple(getattr(requirements, field) for field in _VERSION_FIELDS) != _VERSIONS:
            raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)
        _inventory(results, requirements)
    try:
        admit_sink(sink, envelope_requirements(envelope))
        if requirements is not None:
            admit_sink(sink, requirements)
    except FactoryError:
        raise SinkError(SinkErrorCode.UNSUPPORTED_CAPABILITY) from None
    try:
        started = sink.begin(envelope)
    except SinkError as error:
        raise SinkError(error.code, error.idempotency_key, error.attempt_id) from None
    except Exception:
        raise SinkError(SinkErrorCode.UNAVAILABLE) from None
    if isinstance(started, CompletionReceipt):
        verify_receipt(started, envelope, results)
        return started
    session = started
    try:
        for ordinal, result in enumerate(results):
            if cancellation is not None and cancellation.is_cancelled():
                raise SinkError(SinkErrorCode.CANCELLED)
            sink.write(session, ordinal, result)
        if cancellation is not None and cancellation.is_cancelled():
            raise SinkError(SinkErrorCode.CANCELLED)
    except Exception as error:
        accepted = _abort(sink, session, envelope, results)
        if accepted is not None:
            return accepted
        code = error.code if isinstance(error, SinkError) else SinkErrorCode.RETRYABLE_FAILURE
        raise SinkError(code) from None
    try:
        receipt = _call(lambda: sink.commit(session), SinkErrorCode.COMMIT_UNKNOWN)
    except SinkError as error:
        if error.code is SinkErrorCode.COMMIT_UNKNOWN:
            return _confirmed(sink, envelope, results)
        accepted = _abort(sink, session, envelope, results)
        if accepted is not None:
            return accepted
        raise SinkError(error.code) from None
    verify_receipt(receipt, envelope, results)
    return receipt
