# EF2 supplied money-flow and retracement conversion - EF2-IO #609

This source candidate maps SUPPLIED facts into the roles of the frozen `ef2-mf1` and
`ef2-retrace1` contract (core `docs/ef2/MONEYFLOW_RETRACEMENT_CONTRACT_PROPOSAL.md`):
OHLCV bars with volume in the config's declared adjustment basis, and the exact
integer-coefficient prior-window high and low as two REFERENCE rows. It contains no
money-flow multiplier, OBV, A/D, CMF or retracement-level mathematics, no extremum
derivation, no default period or ratio, no acquisition and no scale, currency, basis or
volume normalization. Adapter and package versions are unchanged.

```python
from equity_feature_duckdb.money_flow import (
    MoneyFlowInputs, make_money_flow_batch, make_slot_coverage, make_money_flow_config,
    synthetic_money_flow_fixture, synthetic_money_flow_config, synthetic_money_flow_features,
    SYNTHETIC_MONEY_FLOW_CASES,
)
from equity_feature_duckdb.retracement import (
    RetracementInputs, make_extremum_reference_id, make_extremum_batch, make_retracement_config,
    synthetic_retracement_fixture, synthetic_retracement_config, SYNTHETIC_RETRACEMENT_CASES,
)
```

## Money flow (`equity_feature_duckdb.money_flow`)

- `make_money_flow_batch(column_order, rows, *, metadata)` converts exact supplied BAR cells
  (`high`, `low`, `close`, `volume`, `known_at_ns`, grid `start_ns`/`end_ns`, no invented `open`)
  into a BAR batch, retaining order and metadata. `make_slot_coverage(index, start_ns, end_ns,
  expected=, observed=, complete=)` builds the per-slot `slot:<index>` coverage entry of the R17 grid.
  A coverage-proven empty slot is either a zero-volume null-OHLC row with complete coverage or
  complete coverage with `expected=0` and no row; a null volume stays null (never assumed zero).
- `MoneyFlowInputs(bars=None, provenance=("unavailable",))`: one nullable role `bars` holding a
  tuple of BAR chunks (`.slots == (bars,)`, `.batches`). Distinct chunk `input_id`s and one
  namespace are required; origins must match delivery.
- `make_money_flow_config(...)` builds the `ef2.money_flow` ConfigSpec (`ef2-money-flow-v1`). The
  contract names the parameters (R17 context, `policy_version`, `cmf_period` only with CMF,
  `evidence_limit`) but not their wire layout; this builder assumes the accepted R17 envelope
  unchanged (closed canonical context chunks and digest, byte-identical to the R17 context codec)
  plus those scalar parameters. Ranges, mode, anchor/target and vocabulary belong to the pure decoder.
- `SYNTHETIC_MONEY_FLOW_CASES` lists the contract's own 36 result fixture ids (M01..M36).
  `synthetic_money_flow_fixture(case_id, *, empty_form="row"|"coverage")`,
  `synthetic_money_flow_config(case_id)` and `synthetic_money_flow_features(case_id)` (the fixture's
  selected output subset; M34 selects two) return original inputs and carry no expected value.

## Retracement (`equity_feature_duckdb.retracement`)

- `make_extremum_reference_id(window_set_id)` encodes `x1:B(window_set_id)` (unpadded base64url).
- `make_extremum_batch(rows, *, metadata)` converts supplied rows with all eleven original cells
  (`price` is the exact int64 coefficient, never a float64; `factor_num`/`factor_den` are the
  upstream observed slots and window length or null) into a REFERENCE batch. Nothing is rounded,
  rescaled or checked; text/snapshot binding, factor all-or-none and shortfall rules are the
  producer's.
- `RetracementInputs(prior_high=None, prior_low=None, provenance=("unavailable",)*2)`: two nullable
  slots in role order; `None` is missing delivery, a zero-row batch is present-empty.
- `make_retracement_config(*, direction, ratio_num, ratio_den, session, window, availability,
  adjustment, price_unit, evidence_limit=0)` builds `ef2.retracement_level`
  (`ef2-retracement-level-v1`) with five flat parameters (assumed layout, as above). No default
  ratio; the pure decoder owns reducedness and the `0..1` domain.
- `SYNTHETIC_RETRACEMENT_CASES` lists T01..T32 with `synthetic_retracement_fixture(case_id)` and
  `synthetic_retracement_config(case_id)`; no expected values.

Synthetic choices the contract does not fix (listed for the worker): entity X/S, namespace SYN,
session [0, 100), ten-ns grid with anchor slot 0, K = evaluation = 100, raw basis, USD (scale 2;
T10 scale 0, T11 scale 6), `evidence_limit` 0 for money flow and 2 for retracement, unknown and
future money-flow slots as zero-volume null-OHLC rows, the null-volume slot known at 50, the gap
retracement side as a present row with incomplete coverage of unknown expected count, effective
instants `0` and null.

[Executable synthetic example](../../examples/ef2_money_flow_retracement.py). See
[validation and remaining gates](../EF2_MONEY_FLOW_RETRACEMENT_IO.md).
