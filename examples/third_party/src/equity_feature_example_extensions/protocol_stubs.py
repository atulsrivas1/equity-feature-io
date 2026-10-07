"""Copyable public method signatures; replace each NotImplementedError locally."""
from collections.abc import Iterator
from equity_feature_contracts.adapters import AcquisitionRequest, AdapterBatch, AdapterCapabilities, Cancellation
from equity_feature_contracts.results import FeatureResult
from equity_feature_io_contracts import (
    AbortOutcome, CompletionReceipt, PublicationEnvelope, PublicationStatus, SinkCapabilities, WriteSession,
)


class SourceStub:
    def capabilities(self) -> AdapterCapabilities:
        raise NotImplementedError

    def iter_batches(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        raise NotImplementedError


class SinkStub:
    def capabilities(self) -> SinkCapabilities:
        raise NotImplementedError

    def begin(self, envelope: PublicationEnvelope) -> WriteSession | CompletionReceipt:
        raise NotImplementedError

    def write(self, session: WriteSession, ordinal: int, result: FeatureResult) -> None:
        raise NotImplementedError

    def commit(self, session: WriteSession) -> CompletionReceipt:
        raise NotImplementedError

    def abort(self, session: WriteSession) -> AbortOutcome:
        raise NotImplementedError

    def lookup(self, idempotency_key: str) -> PublicationStatus:
        raise NotImplementedError

    def read(self, receipt: CompletionReceipt) -> tuple[FeatureResult, ...]:
        raise NotImplementedError
