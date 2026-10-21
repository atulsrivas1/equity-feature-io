# Supplied regular completed-BAR prices

EQ212 [#570](https://github.com/atulsrivas1/equity-features/issues/570) transports the reviewed numerical EQ166 [#506](https://github.com/atulsrivas1/equity-features/issues/506) inputs. Contract/oracle source is [f4aeec98](https://github.com/atulsrivas1/equity-features/tree/f4aeec98f05f81e38813c98a5faf59b27e845ba5/docs/ef1/regular_bar_prices). This is an additive source candidate under the coordinator freeze, not release acceptance.

`equity_feature_duckdb.regular_bar_prices` exports:

- `make_regular_bar_price_batch(kind, column_order, rows, *, metadata)` converts an exact tuple rectangle into a canonical REFERENCE or BAR batch. Column/row order, supplied cells, nulls, clocks and the original metadata object survive unchanged. Canonical validation may reject malformed facts before pure computation.
- `make_regular_bar_population_proof(row, *, metadata)` requires all eight original proof cells: instrument_id, session_id, reference_id, fact_kind, effective_start_ns, effective_end_ns, text, known_at_ns. It preserves the supplied text, digest and clock; it does not derive membership or establish historical source truth.
- `RegularBarPriceInputs(calendar_provenance=None, bars=None, population_proof=None, provenance=("unavailable",)*3)` has three fixed nullable `.slots` in `.roles` order. Present kinds are REFERENCE, BAR, REFERENCE. `.batches` is their present-only subsequence, never the pure input tuple. Empty batches remain present. Duplicate input IDs, differing namespaces, wrong role kinds and mismatched provenance refuse at the container.
- `synthetic_regular_bar_price_config(case_id="R01_two_independent_endpoints")` and `synthetic_regular_bar_price_fixture(case_id="R01_two_independent_endpoints")` return original literal supplied facts/config. The second supported case is `R08_unknown_before_first`. Neither helper includes expected results or generates a proof.

Provenance is declared per role as `synthetic`, `duckdb_backed_observed` or `unavailable`; unavailable must correspond exactly to absence. A declared observed origin is not evidence of source capabilities, rights, auction exclusion or original known-at. A source lacking independently causal membership evidence must report unavailable or use explicitly synthetic facts. No observed dataset is admitted by this implementation.

The adapter does not fill missing columns, repair invalid OHLC, sort, clip, infer phase membership, choose first/last observations or calculate prices. Numeric absence and present-null remain distinct. The pure library owns the independent first-open/calculated-close rules, exact `float(Fraction(p, 10**scale))` conversion, proof admission, readiness and evidence. Calculated close is a regular-prefix BAR endpoint, not official-close certification.

Canonical contracts remain 0.0.4a4; the exact result backend is python-exact/0.0.4a5, schema 1, math policy v1, evidence_limit 2. ConfigSpec has schema 1 / algorithm v1 and no build-version field. SourceBinding retains its original four fields. No codec, sink schema or version changes are introduced. Workers reconstruct all three slots using explicit roles/bindings.

See [the executable synthetic example](../../examples/ef1_regular_bar_prices.py) and [author validation/remaining gates](../EF1_REGULAR_BAR_PRICES_IO.md). Existing SDK/output sink publication uses a new separate synthetic destination with full-result retry/readback; source stores remain separate. Stable one-NUL sink lock sidecars retain the existing no-unlink lifetime.
