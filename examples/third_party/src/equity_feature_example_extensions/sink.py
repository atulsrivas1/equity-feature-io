"""Independent public ResultSink implementation, bounded logical data in one instance."""
from dataclasses import dataclass
import hashlib

from equity_feature_contracts.results import FeatureResult
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_contracts.publication import (
    AbortOutcome, ArtifactReference, CompletionReceipt, PublicationEnvelope, PublicationState,
    PublicationStatus, SinkCapabilities, SinkError, SinkErrorCode, WriteSession, digest,
)
from equity_feature_io_sdk import (
    content_digest, decode_result, descriptor, encode_envelope, encode_result,
    idempotency_key, verify_content, verify_receipt,
)

LIMITS = SinkRequirements(max_results=100, max_chunk_bytes=1048576, max_total_bytes=10485760,
                          max_result_cells=100000, max_evidence_rows=100000)


@dataclass(frozen=True)
class _Session:
    key: str
    attempt_id: str


@dataclass
class _Record:
    envelope: PublicationEnvelope
    session: _Session
    state: PublicationState
    data: list[bytes]
    receipt: CompletionReceipt | None = None


class ExampleSink:
    """Single caller/thread, one Python instance; no persistence or process recovery."""
    def __init__(self, destination_scope: str = "synthetic-conformance") -> None:
        if destination_scope != "synthetic-conformance":
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        self._records: dict[str, _Record] = {}
        self._attempt = 0

    def capabilities(self) -> SinkCapabilities:
        return SinkCapabilities(("1",), ("efio-json1",), ("efio-key1",), ("efio-content1",),
                                ("0.0.4a4",), ("1",), ("v1",), "transactional", "single_writer",
                                True, True, True, 1, 100, 1048576, 10485760, 100000, 100000)

    def begin(self, envelope: PublicationEnvelope) -> _Session | CompletionReceipt:
        if type(envelope) is not PublicationEnvelope:
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        # Public codec rejects unknown wire/schema/math versions before reservation.
        encode_envelope(envelope)
        if envelope.destination_scope != "synthetic-conformance":
            raise SinkError(SinkErrorCode.INVALID_CONFIG)
        caps = self.capabilities()
        if (envelope.result_count > min(envelope.max_results, caps.max_results)
            or envelope.content_bytes > min(envelope.max_total_bytes, caps.max_total_bytes)
            or envelope.cell_count > min(envelope.max_result_cells, caps.max_result_cells)
            or envelope.evidence_count > min(envelope.max_evidence_rows, caps.max_evidence_rows)):
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        key = idempotency_key(envelope.identity)
        old = self._records.get(key)
        if old is not None:
            previous = old.envelope
            if (previous.expected_content_sha256, previous.result_count, previous.content_bytes,
                previous.cell_count, previous.evidence_count) != (
                envelope.expected_content_sha256, envelope.result_count, envelope.content_bytes,
                envelope.cell_count, envelope.evidence_count):
                raise SinkError(SinkErrorCode.CONFLICT)
            if old.state is PublicationState.COMMITTED:
                assert old.receipt is not None
                if any(len(data) > min(envelope.max_chunk_bytes, caps.max_chunk_bytes) for data in old.data):
                    raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
                self.read(old.receipt)
                return old.receipt
            if old.state is PublicationState.STAGING:
                raise SinkError(SinkErrorCode.BUSY)
        self._attempt += 1
        session = _Session(key, str(self._attempt))
        self._records[key] = _Record(envelope, session, PublicationState.STAGING, [])
        return session

    def _owned(self, session: WriteSession, staging: bool = True) -> _Record:
        if type(session) is not _Session:
            raise SinkError(SinkErrorCode.INVALID_SESSION)
        assert isinstance(session, _Session)
        record = self._records.get(session.key)
        if record is None or record.session is not session or (staging and record.state is not PublicationState.STAGING):
            raise SinkError(SinkErrorCode.INVALID_SESSION)
        return record

    def write(self, session: WriteSession, ordinal: int, result: FeatureResult) -> None:
        record = self._owned(session)
        envelope = record.envelope
        if type(ordinal) is not int or ordinal != len(record.data) or ordinal >= envelope.result_count:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        data = encode_result(result)
        if descriptor(result) != envelope.result_descriptors[ordinal]:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        if (len(data) > min(envelope.max_chunk_bytes, LIMITS.max_chunk_bytes)
            or sum(map(len, record.data)) + len(data) > min(envelope.max_total_bytes, LIMITS.max_total_bytes)):
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        results = tuple(decode_result(previous) for previous in record.data) + (result,)
        if (sum(len(c.entities) for r in results for c in r.values) > min(envelope.max_result_cells, LIMITS.max_result_cells)
            or sum(len(r.evidence) for r in results) > min(envelope.max_evidence_rows, LIMITS.max_evidence_rows)):
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
        keys = [(r.metadata.namespace, e.instrument_id, e.session_id, c.feature_id)
                for r in results for c in r.values for e in c.entities]
        if len(keys) != len(set(keys)):
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        record.data.append(data)

    def commit(self, session: WriteSession) -> CompletionReceipt:
        record = self._owned(session)
        results = tuple(decode_result(data) for data in record.data)
        verify_content(record.envelope, results)
        envelope = record.envelope
        artifacts = tuple(ArtifactReference(f"{session.attempt_id}/result-{n}", hashlib.sha256(data).hexdigest(), len(data))
                          for n, data in enumerate(record.data))
        receipt = CompletionReceipt(envelope.identity, idempotency_key(envelope.identity), content_digest(results),
                                    envelope.result_count, envelope.cell_count, envelope.evidence_count,
                                    envelope.content_bytes, artifacts, None)
        verify_receipt(receipt, envelope, results)
        record.receipt = receipt
        record.state = PublicationState.COMMITTED
        return receipt

    def abort(self, session: WriteSession) -> AbortOutcome:
        record = self._owned(session, staging=False)
        if record.state is PublicationState.COMMITTED:
            assert record.receipt is not None
            self.read(record.receipt)
            return AbortOutcome(PublicationState.COMMITTED, record.receipt)
        record.data.clear()
        record.state = PublicationState.ABORTED
        return AbortOutcome(PublicationState.ABORTED, None)

    def lookup(self, idempotency_key: str) -> PublicationStatus:
        digest(idempotency_key)
        record = self._records.get(idempotency_key)
        if record is None:
            return PublicationStatus(PublicationState.ABSENT, None)
        if record.state is PublicationState.COMMITTED:
            assert record.receipt is not None
            self.read(record.receipt)
        return PublicationStatus(record.state, record.receipt)

    def read(self, receipt: CompletionReceipt) -> tuple[FeatureResult, ...]:
        if type(receipt) is not CompletionReceipt:
            raise SinkError(SinkErrorCode.CORRUPTION)
        record = self._records.get(receipt.idempotency_key)
        if record is None or record.state is not PublicationState.COMMITTED:
            raise SinkError(SinkErrorCode.UNAVAILABLE)
        try:
            if record.receipt != receipt or len(record.data) != len(receipt.artifacts):
                raise SinkError(SinkErrorCode.CORRUPTION)
            for reference, data in zip(receipt.artifacts, record.data, strict=True):
                if reference.byte_length != len(data) or reference.byte_sha256 != hashlib.sha256(data).hexdigest():
                    raise SinkError(SinkErrorCode.CORRUPTION)
            results = tuple(decode_result(data) for data in record.data)
            verify_receipt(receipt, record.envelope, results)
            return results
        except Exception:
            raise SinkError(SinkErrorCode.CORRUPTION) from None
