"""Explicit synthetic EF4-I2 projections (bar projection, rate projection) as supplied inputs; no acquisition.

The adapter only maps supplied values and builds the request envelope; the library computes every value. The ids below
are example values chosen by the caller, not defaults of the adapter.
"""
from typing import Any

from equity_feature_duckdb.ef4_projections import ProjectionIds, build_request
from equity_features import ef4

IDS = ProjectionIds(namespace="SYN", instrument_id="INST-1", calendar_id="CAL-1", grid_id="GRID-1", revision="r1",
                    day_session_prefix="DAY-", bar_session_id="BARS-1", target_session_id="TARGET-1")
CTX: dict[str, Any] = {
    "config_unit": {"scale": 0, "currency": "USD"},
    "batch": {"unit": {"scale": 0, "currency": "USD"}, "adjustment": "raw"},
    "config_adjustment": "raw",
    "capability": "batch",
}
# Known-at is never defaulted: every supplied slot or fact states its own known-at ("ka" token or instant).
KA = 50


def main() -> None:
    # Bar projection: an up bar, a down bar and a flat bar [open, high, low, close, volume, actual notional].
    bars = {"params": {"policy_version": "ef4-proj1", "evidence_limit": 10000}, "K": 100, "notional_column": True,
            "bars": [{"row": [10, 12, 9, 11, 100, 1050], "ka": KA}, {"row": [11, 11, 8, 9, 200, 1800], "ka": KA},
                     {"row": [9, 10, 9, 9, 50, 450], "ka": KA}]}
    features = ("projection.up_volume", "projection.up_dollar_volume_fraction")
    bar_request = build_request("bar_projection", bars, {**CTX, "features": features}, IDS)
    grid = ef4.BarGrid(bar_request.grid.instrument_id, bar_request.grid.calendar_id, bar_request.grid.grid_id,
                       bar_request.grid.revision, bar_request.grid.session, bar_request.grid.bar_ns,
                       bar_request.grid.bar_count, bar_request.grid.target_index)
    bar_result = ef4.compute_ef4_path_projections(bar_request.batches, bar_request.config, features=features,
                                                  grid=grid)
    print("bar", bar_request.config.identity, [c.values for c in bar_result.values])

    # Rate projection: 120 trades over a declared 60 s window (tape aggregate fact supplied by the tape producer).
    rate = {"params": {"policy_version": "ef4-rate1", "window_ns": 60 * 10**9, "max_endpoint_age_ns": 10 * 10**9,
                       "evidence_limit": 10000},
            "K": 100, "C": 10**12, "instrument": "INST-1", "legs": [],
            "tape": [{"kind": "count", "s": 940 * 10**9, "e": 10**12, "v": 120, "ka": KA}]}
    rate_features = ("rate.window.trade_rate",)
    rate_request = build_request("rate_projection", rate, {**CTX, "features": rate_features}, IDS)
    rate_result = ef4.compute_ef4_path_projections(rate_request.batches, rate_request.config, features=rate_features,
                                                   entity=rate_request.entity)
    print("rate", rate_request.config.identity, [c.values for c in rate_result.values])


if __name__ == "__main__":
    main()
