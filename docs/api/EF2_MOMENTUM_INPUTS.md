# EF2 supplied momentum and trend conversion - EF2-IO #609

This source candidate maps SUPPLIED OHLCV bars into the one `bars` role of the frozen momentum and
trend contract (core `docs/ef2/MOMENTUM_TREND_CONTRACT_PROPOSAL.md`; config `intraday.momentum.v1`,
convention group `ef2-conv1`; MACD, DMI/ADX, stochastic %K/%D and Williams %R). It contains no EMA,
MACD, directional-movement, ADX, stochastic or Williams mathematics, no default period, no
acquisition and no scale, currency, basis or unit normalization. Adapter and package versions are
unchanged.

```python
from equity_feature_duckdb.momentum import (
    MomentumInputs, make_momentum_batch, make_slot_coverage, make_momentum_config,
    synthetic_momentum_fixture, synthetic_momentum_config, synthetic_momentum_features,
    synthetic_momentum_prefix_lengths, SYNTHETIC_MOMENTUM_CASES,
    FAMILY_PERIODS, FAMILY_FEATURES, FEATURE_UNITS,
)
```

- `make_momentum_batch(column_order, rows, *, metadata)` converts exact supplied BAR cells
  (`high`, `low`, `close`, `volume`, `known_at_ns`, grid `start_ns`/`end_ns`, no invented `open`)
  into a BAR batch, retaining order and metadata. Columns the delivery lacks are simply not listed.
  `make_slot_coverage(index, start_ns, end_ns, expected=, observed=, complete=)` builds the
  per-slot `slot:<index>` coverage entry of the R17 grid.
- `MomentumInputs(bars=None, provenance=("unavailable",))`: one nullable role `bars` holding a tuple
  of BAR chunks (`.slots == (bars,)`, `.batches`). `None` is absent delivery; origins must match
  delivery; distinct chunk `input_id`s and one namespace are required.
- `make_momentum_config(...)` builds `intraday.momentum.v1` (`intraday-momentum-v1`) with the library
  keywords (`family='macd'|'dmi'|'stochastic'`, that family's period keywords, `availability`,
  `adjustment`, `price_unit`, `evidence_limit=0`, `conventions=None`) plus the explicit R17 context
  (`instrument_id`, `calendar_id`, `grid_id`, `revision`, `sessions`, `runs`, `anchor_index`,
  `target_index`, `mode`). Byte-identical to the library `build_momentum_config`. Ranges, bounds, mode
  and convention values (invalid_config, incompatible_version) belong to the pure decoder.
- `FAMILY_PERIODS`, `FAMILY_FEATURES` (lexical) and `FEATURE_UNITS` list the closed parameters, the ten
  output ids and their units (`currency/share`, `DMI points`, `stochastic points`, `Williams %R points`).
- `SYNTHETIC_MOMENTUM_CASES` lists the contract's own 100 result fixture ids (32 MACD, 38 DMI, 30
  stochastic) including D04 (Amendment 1 prices), D22 and the prefix fixtures P01 to P03.
  `synthetic_momentum_fixture(case_id, *, series="A", length=None, empty_form="row")`,
  `synthetic_momentum_config(case_id, *, length=None)` and `synthetic_momentum_features(case_id)` (the
  family's outputs, or the fixture's selected subset) return original inputs and carry no expected
  value. For P01 to P03, `synthetic_momentum_prefix_lengths(case_id)` lists the prefix lengths and
  `series="A"|"B"` with `length=` selects the series and prefix (config and inputs must use the same
  `length`).

Synthetic choices the contract does not fix (listed for the worker): entity X in namespace SYN, ten-ns
grid, one slot per fixture position, K = evaluation = end of the last slot (also the session close),
raw basis, USD at the fixture scale (0, or 2 for M09 and T28), `evidence_limit` the fixture's else the
contract default 10000, volume 100 on every priced bar, known_at 5 (future: K+50, unknown: null). With
anchor a > 0 slots 0..a-1 form a prior session `S0` (chunk `bars-000`) and the epoch session `S` the next
chunk; otherwise one chunk. MACD fixtures leave high and low null: a valid bar is supplied with high =
low = close. `missing` is a declared incomplete slot without a row; `empty` a zero-volume all-null-OHLC
row with complete coverage (or expected 0 without a row, `empty_form="coverage"`); `null` a row with null
volume and the listed OHLC field null (a positive-volume bar with a null OHLC cell is invalid);
`absent_columns` are omitted from the delivery; delivery `none` is `bars=None`.

[Executable synthetic example](../../examples/ef2_momentum.py). See
[validation and remaining gates](../EF2_MOMENTUM_IO.md).
