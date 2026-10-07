"""Runnable installed public source -> calculation -> sink tutorial."""
import argparse
import json

from equity_feature_contracts.adapters import HistoricalAdapter, validate_delivery
from equity_feature_contracts.inputs import PriceUnit
from equity_feature_contracts.results import EntityKey, FeatureResult
from equity_feature_contracts.specs import AvailabilitySpec, ConfigSpec, Parameter, SessionSpec, WindowSpec
from equity_feature_io_contracts import CompletionReceipt, ResultSink
from equity_feature_io_sdk import (
    SinkRegistry, SourceRegistry, admit_sink, admit_source, encode_result, prepare_publication, publish,
)
from . import ExampleSource, ExampleSink, SourceFactory, SinkFactory, example_request
from .sink import LIMITS


class NoCredentials:
    def get(self, name: str) -> str | None:
        raise AssertionError("these synthetic components must not request credentials")


class Continue:
    def is_cancelled(self) -> bool:
        return False


def calculate(source: HistoricalAdapter) -> FeatureResult:
    # The calculation dependency is explicit at demonstration time, not extension import time.
    from equity_features.session import compute_bars
    request = example_request()
    deliveries = tuple(source.iter_batches(request, Continue()))
    validate_delivery(request, source.capabilities(), deliveries)
    batch = deliveries[0].batch
    assert batch is not None
    config = ConfigSpec("synthetic-bars", "v1", (Parameter("eligibility_policy", "example-v1"),),
                        SessionSpec("demo", "S", 100, 200, "caller-supplied"),
                        WindowSpec(1, "S", ("P", "S")), AvailabilitySpec(200, 210, 210),
                        price_unit=PriceUnit(0, "USD"))
    return compute_bars(batch, config, entity=EntityKey("A", "S"))


def run_example(*, factory: bool = False) -> tuple[FeatureResult, CompletionReceipt, tuple[FeatureResult, ...]]:
    request = example_request()
    limits = LIMITS
    source: HistoricalAdapter
    sink: ResultSink
    if factory:
        sources: SourceRegistry[ExampleSource] = SourceRegistry()
        sinks: SinkRegistry[ExampleSink] = SinkRegistry()
        sources.register("example.bars", SourceFactory())
        sinks.register("example.memory", SinkFactory())
        source = sources.resolve("example.bars", {"namespace": "demo"}, NoCredentials(), request)
        sink = sinks.resolve("example.memory", {"destination_scope": "synthetic-conformance"}, NoCredentials(), limits)
    else:
        source = admit_source(ExampleSource(), request)
        sink = admit_sink(ExampleSink(), limits)
    result = calculate(source)
    envelope = prepare_publication((result,), destination_scope="synthetic-conformance", generation_id="generation1",
                                   job_id="example1", partition_id="A-S", limits=limits)
    receipt = publish(sink, envelope, (result,))
    readback = sink.read(receipt)
    assert tuple(map(encode_result, readback)) == (encode_result(result),)
    return result, receipt, readback


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("direct", "factory", "both"), default="both")
    args = parser.parse_args()
    records = []
    for factory in ((False, True) if args.mode == "both" else (args.mode == "factory",)):
        result, receipt, _ = run_example(factory=factory)
        values = {column.feature_id: column.values[0] for column in result.values}
        assert values["session.bar.volume"] == 500
        assert values["session.bar.notional"] == 51200
        assert values["session.bar.close_weighted_price"] == 102.6
        assert values["session.price.overnight_gap"] is None
        records.append({"mode": "factory" if factory else "direct", "values": values,
                        "content_sha256": receipt.content_sha256, "committed": True,
                        "in_memory_instance_only": True})
    print(json.dumps(records, sort_keys=True))


if __name__ == "__main__":
    main()
