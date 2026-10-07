"""One explicitly identified synthetic historical batch; no external acquisition."""
from collections.abc import Iterator

from equity_feature_contracts.adapters import (
    AcquisitionRequest, AdapterBatch, AdapterCapabilities, Cancellation,
    SourceError, SourceErrorCode, require_adapter_capability,
)
from equity_feature_contracts.inputs import (
    BatchMetadata, CanonicalBatch, Column, Coverage, DataKind, InputScope, PriceUnit, SourceBinding,
)
from equity_feature_contracts.specs import AvailabilitySpec


def example_request() -> AcquisitionRequest:
    return AcquisitionRequest("req1", DataKind.BAR, "demo", ("A",), ("S",), 100, 200,
                              "snapshot1", PriceUnit(0, "USD"), AvailabilitySpec(200, 210, 210),
                              max_batch_rows=2, max_rows=2, max_batches=1, selection="completed_intervals")


class ExampleSource:
    """Caller-owned source supporting only example_request(), without a live method."""
    def __init__(self, namespace: str = "demo") -> None:
        if namespace != "demo":
            raise SourceError(SourceErrorCode.UNSUPPORTED, "unsupported synthetic namespace")

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities((DataKind.BAR,), ("demo",), (PriceUnit(0, "USD"),),
                                   historical=True, live=False, max_batch_rows=2)

    def iter_batches(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        require_adapter_capability(self.capabilities(), request)
        if request != example_request():
            raise SourceError(SourceErrorCode.UNSUPPORTED, "unsupported synthetic request")
        if cancellation.is_cancelled():
            return
        source = SourceBinding("synthetic", "snapshot1", "map1", "bars1")
        coverage = Coverage(2, 2, True)
        facts = (
            Column("instrument_id", ("A", "A")), Column("session_id", ("S", "S")),
            Column("start_ns", (100, 150)), Column("end_ns", (150, 200)),
            Column("known_at_ns", (150, 210)), Column("open", (100, 102)),
            Column("high", (103, 104)), Column("low", (99, 101)), Column("close", (102, 103)),
            Column("volume", (200, 300)), Column("actual_notional", (20300, 30900)),
        )
        batch = CanonicalBatch(DataKind.BAR, facts, BatchMetadata("demo", source, coverage,
                               PriceUnit(0, "USD"), scope=InputScope(100, 200, "example-v1")))
        yield AdapterBatch("req1", 0, True, source, coverage, coverage, batch)
