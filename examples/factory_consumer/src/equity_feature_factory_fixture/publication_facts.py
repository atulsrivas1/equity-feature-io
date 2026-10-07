"""Explicit synthetic supplied canonical facts, not a source/backend certificate."""
from dataclasses import replace

from equity_feature_contracts import inputs as i, results as r, specs as s


def synthetic_results() -> tuple[r.FeatureResult, ...]:
    entity = r.EntityKey("I", "S")
    base = r.ResultMetadata("synthetic", "S", s.AvailabilitySpec(10, 10, 10), "0" * 64, (), "synthetic", "1")

    def result(name: str, dtype: r.ValueType, value: r.ResultCell, *, metadata: r.ResultMetadata = base,
               expected: int | None = 1, observed: int = 1, status: r.Status = r.Status.AVAILABLE,
               reasons: tuple[r.Reason, ...] = (), evidence: tuple[r.EvidenceRow, ...] = ()) -> r.FeatureResult:
        return r.FeatureResult((r.FeatureColumn(name, "1", dtype, "synthetic-unit", (entity,), (value,)),),
                               (r.QualityRow(entity, name, status, expected, observed, reasons),), metadata, evidence)

    values: list[r.FeatureResult] = [r.FeatureResult((), (), base)]
    for name, dtype, value in (
        ("int64-min", r.ValueType.INT64, -(2**63)), ("int64-max", r.ValueType.INT64, 2**63 - 1),
        ("decimal128", r.ValueType.DECIMAL128, 10**38 - 1), ("negative-zero", r.ValueType.FLOAT64, -0.0),
        ("string", r.ValueType.STRING, "e\u0301/\u00e9\n"), ("bool", r.ValueType.BOOL, False),
    ):
        values.append(result(name, dtype, value))
    values.append(result("observed-empty", r.ValueType.INT64, 0, expected=0, observed=0))
    values.append(result("missing", r.ValueType.INT64, None, expected=None, observed=0,
                         status=r.Status.MISSING_INPUT, reasons=(r.Reason.ABSENT_INPUT,)))
    values.append(result("breadth-counts", r.ValueType.BREADTH_COUNTS, r.BreadthCounts(1, 0, 0, 2),
                         expected=2, observed=1, status=r.Status.INCOMPLETE_COVERAGE, reasons=(r.Reason.PARTIAL_UNIVERSE,)))
    values.append(result("breadth-fraction", r.ValueType.BREADTH_FRACTION, r.BreadthFraction(1, 1, 1)))
    scope = i.InputScope(0, 10, "synthetic-v1")
    intervals = (i.IntervalCoverage("interval", 0, 10, i.Coverage(1, 1, True)),)
    batch = i.BatchMetadata("synthetic", i.SourceBinding("synthetic", "snapshot1", "map1", "input1"),
                            i.Coverage(1, 1, True), i.PriceUnit(4, "USD"), scope=scope, interval_coverage=intervals)
    trade = replace(base, inputs=(r.InputBinding("trades", i.DataKind.TRADE, batch),), evidence_limit=1)
    row = r.TopKTradeRow("input1", "event1", 9, 0, 9, 10000, 5)
    values.append(result("top-k", r.ValueType.TOP_K_TRADES, r.TopKTrades(1, (row,)), metadata=trade,
                         evidence=(r.EvidenceRow(entity, "top-k", "input1", "event1", 9, 9),)))
    quote = replace(base, inputs=(r.InputBinding("quotes", i.DataKind.QUOTE, replace(batch, sampling="continuous")),), evidence_limit=1)
    values.append(result("quote-counts", r.ValueType.QUOTE_STATE_COUNTS, r.QuoteStateCounts(1, 0, 0, 0), metadata=quote))
    observation = r.QuoteObservation("input1", "event1", 9, 0, 9, 10000, 10100, "normal", 0.01, 100.0)
    values.append(result("sampled-spread", r.ValueType.SAMPLED_SPREAD,
                         r.SampledSpread("continuous", 1, 1, 0.01, 100.0, 1, (observation,)), metadata=quote,
                         evidence=(r.EvidenceRow(entity, "sampled-spread", "input1", "event1", 9, 9),)))
    values.append(result("time-spread", r.ValueType.TIME_WEIGHTED_SPREAD,
                         r.TimeWeightedSpread(r.QuoteDurations(10, 0, 0, 0, 0, 0), 0.01, 100.0, 10, "inactive"), metadata=quote))
    interval = s.IntervalSpec("interval", 0, 10)
    ohlc_quality = r.QualityRow(entity, "interval-ohlc", r.Status.AVAILABLE, 1, 1)
    values.append(result("interval-ohlc", r.ValueType.INTERVAL_OHLCV,
                         r.IntervalOHLCV((r.IntervalOHLCVRow(interval, 1.0, 2.0, 0.5, 1.5, 5, ohlc_quality),))))
    share_quality = r.QualityRow(entity, "interval-share", r.Status.AVAILABLE, 1, 1)
    values.append(result("interval-share", r.ValueType.INTERVAL_VOLUME_SHARES,
                         r.IntervalVolumeShares((r.IntervalVolumeShareRow(interval, 1.0, share_quality),))))
    # Unknown knowledge is preserved as explicitly excluded diagnostic evidence.
    values.append(result("unknown-evidence", r.ValueType.INT64, 1, metadata=trade,
                         evidence=(r.EvidenceRow(entity, "unknown-evidence", "input1", "event1", 9, None,
                                                 use="excluded", exclusion_reason=r.Reason.UNKNOWN_AVAILABILITY),)))
    return tuple(values)
