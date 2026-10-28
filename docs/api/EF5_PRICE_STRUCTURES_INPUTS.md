# EF5 supplied price-structure inputs

`equity_feature_duckdb.price_structures` maps supplied OHLCV (or close-only) bars on the R17 governed grid to the one nullable `bars`
role of the EF5 producers and builds their closed configuration envelopes. It performs no mathematics.

- `make_ef5_context(...)`: the R17 context for an epoch profile (`session_reset` is mode `reset`, `governed_history` is `carry`).
- `make_ef5_chunks(context, slots, ..., declare_coverage=...)`: one BAR chunk per actual session. Slot entries: `"absent"`/`"forming"`
  (no row, no coverage; the library tells a bar still forming at the market cutoff from an absent one), `"gap"` (declared incomplete),
  `"empty"` (proven empty, complete coverage of 0), or `{"values": ..., "known_at_ns": int | None}`. `declare_coverage` has no default;
  `False` with rows is refused INVALID_SCHEMA (E2).
- `make_ef5_config(producer, context, *, availability, adjustment, price_unit, policy_version, epoch_profile, evidence_limit,
  adjustment_label, adjustment_policy_version, **producer_parameters)`: every declaration is required. Producer parameters:
  candle `doji_body_max_fraction` (text `p/q`, at most 18 digits per side); structure `swing_strength`, `lookback`; technical
  `trend_window`, `trend_count`. Labels: `unadjusted` (raw, `raw-v1`) and `split_adjusted` (split, `split-factors-v1`).
- `Ef5Inputs`: the nullable `bars` role holder; `EF5_FEATURES` and `EF5_UNITS` list the 15 outputs and their units.

The library (`equity_features_intraday.compute_ef5`) performs every admission, decision and refusal.
