"""Immutable publication v1 contracts; supplied facts only, no storage access."""
from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
import re
from typing import Protocol

from equity_feature_contracts.inputs import I64_MIN, I64_MAX
from equity_feature_contracts.results import FeatureResult, ResultMetadata, ValueType


class SinkErrorCode(StrEnum):
    INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"
    INVALID_CONFIG = "INVALID_CONFIG"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INVALID_CONTENT = "INVALID_CONTENT"
    INVALID_SESSION = "INVALID_SESSION"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    CONFLICT = "CONFLICT"
    BUSY = "BUSY"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
    CANCELLED = "CANCELLED"
    CORRUPTION = "CORRUPTION"
    UNAVAILABLE = "UNAVAILABLE"


def label(value: str) -> None:
    if type(value) is not str or not value.strip() or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise SinkError(SinkErrorCode.INVALID_CONFIG)


def digest(value: str) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise SinkError(SinkErrorCode.INVALID_CONFIG)


def count(value: int, positive: bool = False) -> None:
    if type(value) is not int or not int(positive) <= value <= I64_MAX:
        raise SinkError(SinkErrorCode.INVALID_CONFIG)


def timestamp(value: int | None) -> None:
    if value is not None and (type(value) is not int or not I64_MIN <= value <= I64_MAX):
        raise SinkError(SinkErrorCode.INVALID_CONFIG)


class SinkError(ValueError):
    """Fixed diagnostic; caller/backend text is never formatted into messages."""
    def __init__(self, code: SinkErrorCode, idempotency_key: str | None = None, attempt_id: str | None = None) -> None:
        if type(code) is not SinkErrorCode:
            raise TypeError("typed sink error code required")
        # Validate without recursive SinkError construction.
        if idempotency_key is not None and (type(idempotency_key) is not str or re.fullmatch(r"[0-9a-f]{64}", idempotency_key) is None):
            raise ValueError("invalid error key")
        if attempt_id is not None and (type(attempt_id) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", attempt_id) is None):
            raise ValueError("invalid error attempt")
        self.code = code
        self.idempotency_key = idempotency_key
        self.attempt_id = attempt_id
        super().__init__("Publication failed: " + code.value)


@dataclass(frozen=True)
class FeatureHeader:
    feature_id: str
    algorithm_version: str
    dtype: ValueType
    unit: str
    schema_version: str

    def __post_init__(self) -> None:
        for value in (self.feature_id, self.algorithm_version, self.unit, self.schema_version):
            label(value)
        if type(self.dtype) is not ValueType:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)


@dataclass(frozen=True)
class ResultDescriptor:
    metadata: ResultMetadata
    features: tuple[FeatureHeader, ...]

    def __post_init__(self) -> None:
        if type(self.metadata) is not ResultMetadata or type(self.features) is not tuple or any(type(h) is not FeatureHeader for h in self.features):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if len({h.feature_id for h in self.features}) != len(self.features):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)


@dataclass(frozen=True)
class PublicationIdentity:
    protocol_version: str
    codec_version: str
    identity_version: str
    digest_version: str
    canonical_package_version: str
    canonical_schema_version: str
    math_policy_version: str
    destination_scope: str
    generation_id: str
    job_id: str
    partition_id: str
    result_descriptors: tuple[ResultDescriptor, ...]
    supersedes_key: str | None

    def __post_init__(self) -> None:
        for name in ("protocol_version", "codec_version", "identity_version", "digest_version", "canonical_package_version", "canonical_schema_version", "math_policy_version", "destination_scope", "generation_id", "job_id", "partition_id"):
            label(getattr(self, name))
        if type(self.result_descriptors) is not tuple or any(type(d) is not ResultDescriptor for d in self.result_descriptors):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if self.supersedes_key is not None:
            digest(self.supersedes_key)


@dataclass(frozen=True)
class PublicationEnvelope(PublicationIdentity):
    expected_content_sha256: str
    result_count: int
    cell_count: int
    evidence_count: int
    content_bytes: int
    max_results: int
    max_chunk_bytes: int
    max_total_bytes: int
    max_result_cells: int
    max_evidence_rows: int
    caller_created_at_ns: int | None

    def __post_init__(self) -> None:
        super().__post_init__()
        digest(self.expected_content_sha256)
        for value in (self.result_count, self.cell_count, self.evidence_count, self.content_bytes, self.max_result_cells, self.max_evidence_rows):
            count(value)
        for value in (self.max_results, self.max_chunk_bytes, self.max_total_bytes):
            count(value, True)
        timestamp(self.caller_created_at_ns)
        if self.result_count != len(self.result_descriptors) or self.max_chunk_bytes > self.max_total_bytes:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if self.result_count > self.max_results or self.cell_count > self.max_result_cells or self.evidence_count > self.max_evidence_rows or self.content_bytes > self.max_total_bytes:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)

    @property
    def identity(self) -> PublicationIdentity:
        return PublicationIdentity(**{f.name: getattr(self, f.name) for f in fields(PublicationIdentity)})


@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    byte_sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        label(self.artifact_id)
        # Destination-relative opaque names; never absolute paths or credentialed URIs.
        if self.artifact_id.startswith(("/", "\\")) or ":" in self.artifact_id or "\\" in self.artifact_id or any(p in ("", ".", "..") for p in self.artifact_id.split("/")):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        digest(self.byte_sha256)
        count(self.byte_length)


@dataclass(frozen=True)
class CompletionReceipt:
    identity: PublicationIdentity
    idempotency_key: str
    content_sha256: str
    result_count: int
    cell_count: int
    evidence_count: int
    content_bytes: int
    artifacts: tuple[ArtifactReference, ...]
    caller_committed_at_ns: int | None

    def __post_init__(self) -> None:
        if type(self.identity) is not PublicationIdentity:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        digest(self.idempotency_key)
        digest(self.content_sha256)
        for value in (self.result_count, self.cell_count, self.evidence_count, self.content_bytes):
            count(value)
        timestamp(self.caller_committed_at_ns)
        if self.result_count != len(self.identity.result_descriptors) or type(self.artifacts) is not tuple or any(type(a) is not ArtifactReference for a in self.artifacts):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if len({a.artifact_id for a in self.artifacts}) != len(self.artifacts):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)


class PublicationState(StrEnum):
    ABSENT = "ABSENT"
    STAGING = "STAGING"
    ABORTED = "ABORTED"
    COMMITTED = "COMMITTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PublicationStatus:
    state: PublicationState
    receipt: CompletionReceipt | None

    def __post_init__(self) -> None:
        if type(self.state) is not PublicationState or (self.state is PublicationState.COMMITTED) != (type(self.receipt) is CompletionReceipt):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if self.state is not PublicationState.COMMITTED and self.receipt is not None:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)


@dataclass(frozen=True)
class AbortOutcome(PublicationStatus):
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.state not in (PublicationState.ABORTED, PublicationState.COMMITTED, PublicationState.UNKNOWN):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)


@dataclass(frozen=True)
class SinkCapabilities:
    protocol_versions: tuple[str, ...]
    codec_versions: tuple[str, ...]
    identity_versions: tuple[str, ...]
    digest_versions: tuple[str, ...]
    canonical_package_versions: tuple[str, ...]
    canonical_schema_versions: tuple[str, ...]
    math_policy_versions: tuple[str, ...]
    visibility: str
    writer_mode: str
    supports_lookup: bool
    supports_abort: bool
    supports_read: bool
    reservation_retention_ns: int
    max_results: int
    max_chunk_bytes: int
    max_total_bytes: int
    max_result_cells: int
    max_evidence_rows: int

    def __post_init__(self) -> None:
        for versions in (self.protocol_versions, self.codec_versions, self.identity_versions, self.digest_versions, self.canonical_package_versions, self.canonical_schema_versions, self.math_policy_versions):
            if type(versions) is not tuple or not versions or any(type(v) is not str for v in versions) or len(set(versions)) != len(versions):
                raise SinkError(SinkErrorCode.INVALID_CONFIG)
            for version in versions:
                label(version)
        if type(self.visibility) is not str or type(self.writer_mode) is not str or self.visibility not in ("manifest_last", "transactional") or self.writer_mode not in ("single_writer", "serialized_writer", "conflict_safe_multi_writer"):
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        if any(type(v) is not bool or not v for v in (self.supports_lookup, self.supports_abort, self.supports_read)):
            raise SinkError(SinkErrorCode.UNSUPPORTED_CAPABILITY)
        for value in (self.reservation_retention_ns, self.max_results, self.max_chunk_bytes, self.max_total_bytes):
            count(value, True)
        count(self.max_result_cells)
        count(self.max_evidence_rows)
        if self.max_chunk_bytes > self.max_total_bytes:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)


class WriteSession(Protocol):
    """Locally trusted handle; no portable serialized session is supported."""
    @property
    def attempt_id(self) -> str: ...


class ResultSink(Protocol):
    def capabilities(self) -> SinkCapabilities: ...
    def begin(self, envelope: PublicationEnvelope) -> WriteSession | CompletionReceipt: ...
    def write(self, session: WriteSession, ordinal: int, result: FeatureResult) -> None: ...
    def commit(self, session: WriteSession) -> CompletionReceipt: ...
    def abort(self, session: WriteSession) -> AbortOutcome: ...
    def lookup(self, idempotency_key: str) -> PublicationStatus: ...
    def read(self, receipt: CompletionReceipt) -> tuple[FeatureResult, ...]: ...
