"""Explicit synthetic EF3 robust-history, volume-pace and mean-ratio requests as supplied inputs; no acquisition."""
from equity_feature_duckdb.robust_pace import (
    Cell, availability, daily_batch, grid_batch, bars_batch, mean_ratio_config, robust_history_config, session,
    sessions_batch, volume_pace_config,
)


def main() -> None:
    # Five prior volumes and a target volume over six governed sessions (session 5 is the target).
    sessions = [session(i) for i in range(6)]
    target = sessions[5]
    volumes = [7, 3, 9, 1, 5, 6]
    series = daily_batch([("X", s, Cell("row", v, 50)) for s, v in zip(sessions, volumes)], field="volume", scale=0,
                         input_id="series")
    sessions_role = sessions_batch(sessions, input_id="sessions")
    history = robust_history_config(target, timing=availability(target.close_ns), field="volume", scale=0, window=5,
                                    min_history=5, quantile=(1, 2), evidence_limit=0)
    print("robust history", history.identity, series.row_count, sessions_role.row_count, len(history.parameters))

    # Three equal buckets; prior sessions and the target in one bars role.
    offsets = [0, 100, 200, 300]
    prior = [session(j) for j in range(5)]
    bars = bars_batch([(s, c, Cell("row", 10 + c, 50)) for s in prior + [target] for c in range(3)], offsets,
                      input_id="bars")
    pace = volume_pace_config(target, timing=availability(target.open_ns + 200), profile="bucket", window=5,
                              min_history=5, scale_pair=(1, 1))
    grid = grid_batch(offsets, target, input_id="grid")
    print("volume pace", pace.identity, bars.row_count, grid.row_count)

    mean = mean_ratio_config(target, timing=availability(target.close_ns), numerator_window=2, baseline_window=4,
                             numerator_inclusion="prior_only", baseline_inclusion="prior_only")
    print("mean ratio", mean.identity)
    # The library computes every value (equity_features.ef3); this module only maps and builds envelopes.


if __name__ == "__main__":
    main()
