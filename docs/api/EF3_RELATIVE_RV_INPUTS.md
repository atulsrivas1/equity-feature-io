# EF3 supplied relative-statistics, daily log-volatility and realized-variance inputs

This source candidate maps SUPPLIED bars into the frozen EF3 contract (core `docs/ef3/RELATIVE_RV_CONTRACT_PROPOSAL.md`,
Amendment 1; policies `ef3-rel1`, `ef3-dlv1`, `ef3-rv1`). It contains no return, beta, correlation, logarithm,
variance, volatility or annualization mathematics, no default window, period, benchmark or factor, no acquisition and
no scale, currency or basis normalization. Adapter and package versions are unchanged.

```python
from equity_feature_duckdb.relative_rv import (
    DailyGrid, IntradayContextSpec, IntradayRunSpec, daily_sessions, daily_grid, availability_for,
    close_batch, intraday_batch, make_intraday_context, synthetic_intraday_session,
    relative_config, log_volatility_config, realized_variance_config,
    RELATIVE_FEATURES, LOG_VOL_FEATURE, RV_FEATURES,
)
```

- `daily_sessions(count)` and `daily_grid(sessions, target_index, instrument_id="X")` build the LOCAL governed daily grid
  (one whole session per governed slot, `[open, close)` bounds, slot coverage `slot:<index>`, target slot). Its
  `to_json()` and `digest` are byte-identical to the library `DailyGrid`; the producer configs bind it by SHA-256.
- `close_batch(instrument_id, grid, slots, *, input_id, scale, namespace="SYN")` converts one compact close-only role
  (`instrument_id`, `session_id`, `start_ns`, `end_ns`, `close`, `known_at_ns`) into a canonical BAR batch. Slot states:
  `priced` (row, coverage 1/1 complete), `absent` (no row, no coverage), `gap` (declared incomplete coverage 1/0, no row),
  `unknown` (`known_at` null), `future` (`known_at` as given), `null` (row with null close).
- `make_intraday_context(instrument_id, sessions=, runs=, anchor_index=, target_index=, mode="reset")` and
  `synthetic_intraday_session(count)` build the R17 context codec locally (`IntradayContextSpec`, `IntradayRunSpec`).
- `intraday_batch(context, slots, *, input_id, scale)` converts one regular-session OHLCV chunk: `priced` (open, high,
  low and close equal to the close, volume 100), `null` (volume, OHLC and close null), `empty` (no row, coverage 0/0
  complete: a proven empty slot, never forward-filled), `gap`, `absent`, `unknown`, `future`.
- `relative_config`, `log_volatility_config`, `realized_variance_config` build the three envelopes with the caller's
  explicit values passed through unvalidated (refusals belong to the library decoder). `annualization_factor` is present
  exactly when `intraday.realized_volatility` is selected (the caller passes `None` otherwise).
- The compact notation omits the close of an `unknown` slot. The adapter supplies the placeholder `UNSUPPLIED_CLOSE = 1`
  so that the row stays admissible; such a slot is never READY, so the value never reaches an output, return or
  evidence row. This is the one value the contract does not state.

Each `ConfigSpec` carries the same parameter names as the library envelope (`ef3.relative_stats`,
`ef3.daily_log_volatility`, `ef3.intraday_realized_variance`) and binds the grid by `grid_schema` and `grid_sha256`
(daily) or the R17 context chunks (intraday). Admission of every row (grid membership, cutoff, order, duplicates,
units, adjustment, instrument identity) and every refusal is performed by the library, except canonical BAR validation
that the shared `validate_batch` already performs when the batch is built (positive price-bearing OHLC, volume
non-negative, duplicate interval identity).

Example: [examples/ef3_relative_rv.py](../../examples/ef3_relative_rv.py). Source checkpoint and remaining gates:
[EF3_RELATIVE_RV_IO.md](../EF3_RELATIVE_RV_IO.md).
