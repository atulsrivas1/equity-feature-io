# Supplied regular first eligible trade price

EQ212 [#570](https://github.com/atulsrivas1/equity-features/issues/570) supplies the
selected EQ166 [#506](https://github.com/atulsrivas1/equity-features/issues/506)
producer through the existing canonical I/O boundary. The frozen shared contract
is in [draft PR628](https://github.com/atulsrivas1/equity-features/pull/628).
This is source authoring for one slice; original-source admission and release
acceptance remain separate.

`equity_feature_duckdb.regular_first_trade_price` exports:

- `make_regular_first_trade_price_batch(kind, column_order, rows, *, metadata)`
  converts an exact tuple rectangle to a canonical REFERENCE or TRADE batch.
  Original cells, column presence/order, rows, event IDs/order keys, nulls, units,
  adjustment, coverage and clocks survive unchanged. The metadata object is
  retained. Generic `validate_batch(batch, required_fields=())` applies without
  contextual session/availability arguments and may refuse before computation.
- `make_regular_trade_population_proof(row, *, metadata)` requires the eight
  supplied cells instrument_id, session_id, reference_id, fact_kind,
  effective_start_ns, effective_end_ns, text, known_at_ns. Supplied JSON bytes,
  digest and original clock are preserved. This helper generates no proof or
  membership hash and does not establish causal truth.
- `RegularFirstTradePriceInputs(calendar_provenance=None, trades=None,
  population_proof=None, provenance=("unavailable",)*3)` exposes exactly three
  fixed nullable `.slots` in `.roles` order: calendar_provenance REFERENCE,
  trades TRADE, population_proof REFERENCE. `.batches` is the present-only
  subsequence. Empty batches remain present with their actual bindings. Duplicate
  input IDs, differing namespaces, wrong kinds and mismatched provenance refuse.
- `synthetic_regular_first_trade_price_config(case_id="R001")` and
  `synthetic_regular_first_trade_price_fixture(case_id="R001")` return original
  literal synthetic requests; R019 is the second supported case. R001 has a false
  row before the selected eligible trade. R019 supplies a future selected numeric
  clock with a later known trade. The helpers contain no expected results and
  calculate neither firstness nor price.

Per-role origin declarations are `synthetic`, `duckdb_backed_observed` or
`unavailable`; unavailable corresponds exactly to absence. Observed is a caller
declaration, not proof of rights, phase membership, coverage or original known-at.
No provider/N-drive observations are admitted by these helpers.

The adapter never sorts, filters, repairs, derives eligibility from size, selects
a trade, canonicalizes proof text or backdates availability. Whole-column absence
and present-null cells remain distinct. Supplied invalid price/size on any
eligible row can refuse generically even with peer proofs absent. The pure
library owns the new ef1.regular_trade.population.v1 family, rtp1 binding,
readiness, selected original row before numeric availability in both modes,
exact Fraction conversion and one original selected witness. Reusing the old
gap TRADE membership document format does not admit old gap/BAR proofs.

Canonical package0.0.4a4, ConfigSpec schema1/algorithmv1 and existing four-field
SourceBinding are unchanged. Result backend remains python-exact/0.0.4a5,
schema1/mathv1, exact evidence_limit1. No source-specific schema enters the pure
API. Workers reconstruct nullable roles using role/binding identities.

[Executable synthetic example](../../examples/ef1_regular_first_trade_price.py)
uses `.slots` with the existing compute_ef1 API. Existing SDK/codec/output sink
require no source/schema/version change for this scalar FeatureResult. Actual
fresh synthetic DuckDB publication, complete readback/retry/reopen and stable
one-NUL lock sidecars were exercised on the initial pinned core candidate. The
corrected core separately passed numerical/SDK recheck; its physical checks are
owned by the worker. The initial private controller's child-exit persistence
limitation and source epochs are recorded in the validation checkpoint.
Source stores and new output stores remain separate. See
[validation and remaining gates](../EF1_REGULAR_FIRST_TRADE_PRICE_IO.md).
