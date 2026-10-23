"""Explicit supplied path-efficiency mapping: caller ids, supplied slot entries and the configuration; no acquisition.

The library computes every value (equity_features_intraday); this module only maps supplied inputs. The identifiers
below are example values chosen by the caller, not defaults of the adapter.
"""
from equity_feature_contracts import AdjustmentSpec, AvailabilitySpec, PriceUnit, SessionSpec
from equity_feature_duckdb.path_efficiency import (
    OHLCV_COLUMNS, PathEfficiencyInputs, make_path_chunks, make_path_config, make_path_context,
)
from equity_feature_duckdb.relative_rv import IntradayRunSpec

MINUTE_NS = 60 * 10**9


def main() -> None:
    open_ns, slots = 0, 3
    session = SessionSpec("EXAMPLE", "S1", open_ns, open_ns + slots * MINUTE_NS, "UTC")
    run = IntradayRunSpec("S1", open_ns, MINUTE_NS, slots)
    context = make_path_context("X", calendar_id="CAL", grid_id="GRID", revision="r1", sessions=(session,),
                                runs=(run,), anchor_index=0, target_index=slots - 1, epoch_profile="session_reset")
    close_ns = open_ns + slots * MINUTE_NS
    known = close_ns + 50 * 10**9  # knowledge cutoff K = close + 100 s; each bar known 50 s before K
    entries = [
        {"values": (10, 10, 10, 10, 5), "known_at_ns": known},
        {"values": (10, 20, 10, 20, 5), "known_at_ns": known},
        "gap",
    ]
    chunks = make_path_chunks(context, entries, input_id="bars", source_id="EXAMPLE-SRC", snapshot_id="snap1",
                              namespace="EXAMPLE", price_unit=PriceUnit(0, "USD"), adjustment=AdjustmentSpec(),
                              columns=OHLCV_COLUMNS, eligibility_policy="ef4-path-regular")
    inputs = PathEfficiencyInputs(chunks, ("supplied",))
    config = make_path_config(context, window=2, epoch_profile="session_reset",
                              availability=AvailabilitySpec(close_ns, close_ns + 100 * 10**9, close_ns + 100 * 10**9),
                              adjustment=AdjustmentSpec(), price_unit=PriceUnit(0, "USD"), evidence_limit=10000)
    print("chunks", len(inputs.batches), "rows", sum(b.row_count for b in inputs.batches), "config", config.identity)


if __name__ == "__main__":
    main()
