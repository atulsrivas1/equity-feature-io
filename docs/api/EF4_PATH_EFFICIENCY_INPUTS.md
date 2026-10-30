# EF4 supplied path-efficiency and choppiness conversion - EQ-161 I/O

This source candidate maps SUPPLIED bars into the one nullable `bars` role of the frozen EF4 path-efficiency contract
(core `docs/ef4/PATH_EFFICIENCY_CONTRACT_PROPOSAL.md`; config `ef4.path_efficiency`, algorithm
`ef4-path-efficiency-v1`, policy `ef4-path1`). It contains no efficiency ratio, log, true-range, window-range or
choppiness mathematics, no default window, no acquisition, and no scale, currency or basis normalization.

```python
from equity_feature_duckdb.path_efficiency import (
    PathEfficiencyInputs, make_path_batch, make_path_chunks, make_path_config, make_path_context,
    make_slot_coverage, OHLCV_COLUMNS, CLOSE_COLUMNS, PATH_FEATURES, PATH_UNITS,
)
```

- `make_path_context(instrument_id, *, calendar_id, grid_id, revision, sessions, runs, anchor_index, target_index,
  epoch_profile)` returns the accepted R17 context (`IntradayContextSpec` from the EF3 relative/RV conversion). The
  mode is fixed by the profile: `session_reset` uses `reset`, `governed_history` uses `carry`.
- `make_path_chunks(context, slots, *, input_id, source_id, snapshot_id, namespace, price_unit, adjustment, columns,
  eligibility_policy)` builds one BAR chunk per actual session in context order. A slot is `"absent"` (no row, no
  coverage), `"gap"` (declared incomplete coverage), `"empty"` (no row, complete coverage of expected 0) or
  `{"values": tuple, "known_at_ns": int | None}` with values aligned to `columns`. Identity columns (instrument,
  session, start, end) come from the context. Chunk k is `<input_id>-<k:03>` and its scope is its session.
- `make_path_batch(column_order, rows, *, metadata)` and `make_slot_coverage(...)` are the lossless primitives.
- `PathEfficiencyInputs(bars=None, provenance=("unavailable",))` holds the nullable `bars` role (`.slots`, `.batches`).
- `make_path_config(context, *, window, epoch_profile, availability, adjustment, price_unit, evidence_limit,
  policy_version=POLICY_VERSION)` builds the closed envelope (byte-identical to the library builder). Its own checks:
  `price_unit` present (`INVALID_UNIT`), types, `window` in 2..4096, and `governed_history` window at most 63
  (`INVALID_CONFIG`, pinned ruling). Every other value passes to the library decoder.

The library (`equity_features_intraday.compute_path_efficiency`) performs every admission and decision. Configuration
refusal order follows the contract: shape, range and unit faults before the policy label.

[Executable supplied-input example](../../examples/ef4_path_efficiency.py). See
[validation and remaining gates](../EF4_PATH_EFFICIENCY_IO.md).

## Contract catalogue

Internal, synthetic, pre-release. Generated input and output contract pages for the producers this page covers (core wins on conflict; the catalogue computes nothing and names no data supplier). Overview: [catalogue INDEX](../contracts/catalogue/INDEX.md); use: [CATALOGUE.md](../contracts/CATALOGUE.md).

- `ef4.path_efficiency`: [input](../contracts/catalogue/ef4.path_efficiency/input.md), [output](../contracts/catalogue/ef4.path_efficiency/output.md)
