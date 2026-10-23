"""Explicit synthetic EF3 relative-statistics, log-volatility and realized-variance requests as supplied inputs; no acquisition."""
from equity_feature_duckdb.relative_rv import (
    availability_for, close_batch, daily_grid, daily_sessions, intraday_batch, log_volatility_config,
    make_intraday_context, realized_variance_config, relative_config, synthetic_intraday_session,
)


def main() -> None:
    # Two daily closes per role over four governed sessions (slot 2 has unknown availability, slot 3 is a gap).
    sessions = daily_sessions(4)
    grid = daily_grid(sessions, target_index=3)
    instrument = [{"state": "priced", "c": 100, "known_at": 50}, {"state": "priced", "c": 101, "known_at": 50},
                  {"state": "unknown"}, {"state": "gap"}]
    benchmark = [{"state": "priced", "c": 200, "known_at": 50}, {"state": "priced", "c": 202, "known_at": 50},
                 {"state": "priced", "c": 201, "known_at": 50}, {"state": "priced", "c": 205, "known_at": 50}]
    inst_batch = close_batch("X", grid, instrument, input_id="inst", scale=2)
    bench_batch = close_batch("B", grid, benchmark, input_id="bench", scale=2)
    rel = relative_config(grid, benchmark_id="B", window=3, min_pairs=2, availability=availability_for(sessions),
                          scale=2)
    print("relative", rel.identity, inst_batch.row_count, bench_batch.row_count, len(rel.parameters))
    vol = log_volatility_config(grid, period=2, annualization_factor=252, availability=availability_for(sessions),
                                scale=2)
    print("log volatility", vol.identity, close_batch("X", grid, benchmark, input_id="daily", scale=2).row_count)
    session, runs = synthetic_intraday_session(3)
    context = make_intraday_context("X", sessions=session, runs=runs, anchor_index=0, target_index=2)
    bars = intraday_batch(context, [{"state": "priced", "c": 10000}, {"state": "priced", "c": 10050},
                                    {"state": "priced", "c": 10020}], input_id="bars", scale=2)
    rv = realized_variance_config(context, annualization_factor=None, availability=availability_for(session),
                                  scale=2)
    print("realized variance", rv.identity, bars.row_count)
    # The library computes every value (equity_features.ef3 and equity_features_intraday); this module only maps.


if __name__ == "__main__":
    main()
