# Supplied close-reconciliation inputs

EQ212 [#570](https://github.com/atulsrivas1/equity-features/issues/570) supplies the
EQ168 [#508](https://github.com/atulsrivas1/equity-features/issues/508)
`ef1.reference_close` producer through the existing canonical I/O boundary. The
contract is the frozen `ef1-close-compare1` v1 proposal
(`docs/ef1/CLOSE_RECONCILIATION_CONTRACT_PROPOSAL.md` and `.json` in the core
repository). This is source authoring for one slice; original-source admission
and release acceptance remain separate.

`equity_feature_duckdb.reference_close` exports:

- `make_reference_close_batch(kind, column_order, rows, *, metadata)` converts an
  exact tuple rectangle to a canonical REFERENCE or BAR batch. Original cells,
  column presence/order, rows, nulls, units, adjustment, coverage and clocks survive
  unchanged. The metadata object is retained. Generic
  `validate_batch(batch, required_fields=())` applies without contextual arguments
  and may refuse before computation.
- `make_reference_close_population_proof(row, *, metadata)` requires the eight
  supplied cells of the unchanged regular-BAR proof (`ef1.regular_bar.population.v1`).
  Supplied JSON bytes, digest and original clock are preserved; no proof or
  membership hash is generated.
- `make_authoritative_close_reference_id(scope_id, source_close_id)` encodes two
  supplied identities as `k1:B(scope_id):B(source_close_id)` (unpadded base64url of
  UTF8). Length and scope-equality limits belong to the pure producer.
- `make_authoritative_close(row, *, metadata)` converts one supplied record with
  the nine cells instrument_id, session_id, reference_id, fact_kind,
  effective_start_ns, effective_end_ns, text, price, known_at_ns; factor_num and
  factor_den are optional pass-through cells. Price is the supplied integer
  coefficient at the config PriceUnit scale. Nothing is rescaled, filled, inferred
  or replaced; the revision binding `text == source.snapshot_id` is supplied, not
  generated, and checked by the producer.
- `make_reference_close_config(*, calendar, scope_id, tolerance_bps_num,
  tolerance_bps_den, session, window, availability, price_unit, adjustment)` builds the
  `ef1.reference_close` ConfigSpec (v1/schema 1, one `ef1_context_json`, policy label
  `ef1-close-compare1`, canonical ASCII JSON). The tolerance pair is an explicit
  caller input with no default; reducedness, ranges and consistency are validated
  by the pure decoder, not here.
- `ReferenceCloseInputs(calendar_provenance=None, bars=None, population_proof=None,
  authoritative_close=None, provenance=("unavailable",)*4)` exposes four fixed
  nullable `.slots` in `.roles` order: calendar_provenance REFERENCE, bars BAR,
  population_proof REFERENCE, authoritative_close REFERENCE. `.batches` is the
  present-only subsequence. The calculated close is not a slot; it is selected by the
  producer from `bars`. Duplicate input IDs, differing namespaces, wrong kinds and
  mismatched provenance refuse.
- `synthetic_reference_close_config(case_id)` and
  `synthetic_reference_close_fixture(case_id)` return original literal synthetic
  requests: `C01_within_tolerance` (supplied 12.50), `C02_outside_tolerance`
  (supplied 12.60), `C03_absent_authoritative_close` (slot unavailable). Tolerance is
  10/1 BPS and the cutoff is the actual close (30). The helpers contain no expected
  results and calculate neither the close, BPS nor a verdict.

Per-role origin declarations are `synthetic`, `duckdb_backed_observed` or
`unavailable`; unavailable corresponds exactly to absence. Observed is a caller
declaration, not proof of rights or original known-at.

The adapter never sorts, filters, repairs, derives BPS, selects or replaces the
calculated close, substitutes a caller-computed value for a missing supplied close,
or normalizes scale, currency or basis. Duplicate, inconsistent-session, unit,
basis and revision facts pass through unchanged and are refused by the pure
library. The two close values stay under separate feature ids (supplied coefficient
in this result, EQ166 float64 elsewhere). The existing DuckDB sink, SDK, codec and
versions are reused; whether decimal128, float64 hex and the `bps` unit round-trip
there is verified only when executed.

[Executable synthetic example](../../examples/ef1_reference_close.py) uses `.slots`
with `compute_ef1`. See [validation and remaining gates](../EF1_CLOSE_RECONCILIATION_IO.md).

## Contract catalogue

Internal, synthetic, pre-release. Generated input and output contract pages for the producers this page covers (core wins on conflict; the catalogue computes nothing and names no data supplier). Overview: [catalogue INDEX](../contracts/catalogue/INDEX.md); use: [CATALOGUE.md](../contracts/CATALOGUE.md).

- `ef1.reference_close`: [input](../contracts/catalogue/ef1.reference_close/input.md), [output](../contracts/catalogue/ef1.reference_close/output.md)
