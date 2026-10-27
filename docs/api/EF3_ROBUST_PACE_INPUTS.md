# EF3 supplied robust-history, volume-pace and mean-ratio inputs

This source candidate maps SUPPLIED rows into the frozen EF3 contract (core `docs/ef3/ROBUST_PACE_CONTRACT_PROPOSAL.md`;
policies `ef3-robust1`, `ef3-pace1`, `ef3-mean1`). It contains no median, MAD, quantile, rank, ratio, z-score or mean
mathematics, no default window, minimum history, quantile, scale or inclusion, no acquisition and no scale or currency
normalization. Adapter and package versions are unchanged.

```python
from equity_feature_duckdb.robust_pace import (
    Cell, Session, availability, bars_batch, daily_batch, grid_batch, mean_ratio_config, parse_bucket, parse_cell,
    population_batch, price_unit, robust_history_config, session, sessions_batch, volume_pace_config,
)
```

- `session(index, close=300, excluded=False, exclusion_known_at=None, bounds_known_at=None)` builds one governed session: id `str(index)`,
  open `index * 1000`, close `open + close` (nanoseconds, UTC). `Session` is the frozen record.
- `sessions_batch(sessions, input_id=...)` builds the `sessions` role: one `ef3.session.bounds` fact per session and an
  `ef3.session.excluded` fact where a session is excluded. Reference identities use the closed `x1:` encoding (`reference`).
- `population_batch(members, target, input_id=..., known_at=None, namespace=..., population_id=...)` builds the `population` role (`ef3.population.member`, target session).
- `grid_batch(offsets, target, input_id=..., known_at=None, namespace=...)` builds the `grid` role (`ef3.bucket.edge`, offsets from the actual open).
- `daily_batch(entries, field=..., scale=..., input_id=...)` builds the DAILY roles (`series`, `cohort_values`) from
  `(instrument_id, session, Cell)` entries. `field` is `volume` (int64 shares) or a price (`open`, `high`, `low`, `close`
  coefficients at `scale`). Gap cells declare incomplete coverage (`session:<id>` or `member:<id>`); absent cells add nothing.
- `bars_batch(entries, offsets, input_id=...)` builds the `bars` role: one BAR row per session per bucket
  (`bucket:<session>:<index>` for gaps). `parse_bucket` reads a bucket cell, where None is a row with a null volume.
- `robust_history_config`, `volume_pace_config`, `mean_ratio_config` build the three envelopes with the caller's values
  passed through (refusals belong to the library builders and decoders). The quantile pair is present exactly with
  `robust.quantile`, `min_population` exactly with a cohort output, and the scale pair exactly with `pace.robust_z`.
  `grid_version` is the fixed label `ef3-grid1`.
- No `known_at` is defaulted. Each fact carries the `known_at` supplied for it (bounds on `Session.bounds_known_at`, members
  and offsets as `(name, known_at)` / `(offset, known_at)` pairs or a bare value with the explicit `known_at` argument,
  rows on `Cell.known_at`). Absent means null, which the library reports as `unknown_availability` (core amendment E-A2);
  a value that is not null or a non-negative integer is a typed `INVALID_SCHEMA` refusal. `namespace` and `population_id`
  are explicit parameters whose defaults (`SYN`, `SYN-POP`) are documented demo values.
- `Cell(state, value, known_at, excluded, exclusion_known_at)` is the supplied slot form. `parse_cell(token, known_at=...)`
  takes the explicit `known_at` of tokens that state none and reads the contract's
  compact notation (integer priced row, `"null"`, `"absent"`, `"gap"`, `None`, `["x", v]`, `["xu"]`, `["xf"]`, `["f", v]`,
  `["u", v]`, `["p", v, known_at]`). This is notation for the contract fixtures only, not a wire format.

Every `ConfigSpec` equals the library builder (`build_robust_history_config`, `build_pace_config`,
`build_mean_ratio_config`) called with the same explicit parameters. Admission of every row, every reference fact, every
exclusion, unit, basis, namespace and identity, and every refusal is performed by the library and the shared validators.

Example: [examples/ef3_robust_pace.py](../../examples/ef3_robust_pace.py). Source checkpoint and remaining gates:
[EF3_ROBUST_PACE_IO.md](../EF3_ROBUST_PACE_IO.md).
