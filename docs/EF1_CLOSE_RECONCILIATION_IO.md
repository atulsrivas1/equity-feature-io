# Close-reconciliation I/O source checkpoint - October 22, 2026

Status: source authored against the frozen `ef1-close-compare1` contract by the
EQ212 [#570](https://github.com/atulsrivas1/equity-features/issues/570) I/O layer for
EQ168 [#508](https://github.com/atulsrivas1/equity-features/issues/508). The pure
library producer is authored in parallel; nothing below was executed against it.

Added the [supplied-input API](api/EF1_REFERENCE_CLOSE_INPUTS.md), the exact four-role
nullable container, lossless conversion, the `k1:` reference-id encoder, the config
builder and three original synthetic requests. No fetching, source-specific schema,
BPS or tolerance mathematics, close selection or sink/SDK/version change.

What was actually checked (Python 3.12, core `main` packages on the path, library
producer absent): the module imports; the three synthetic fixtures construct and pass
generic canonical validation; the config builder output equals the synthetic config
byte for byte; the synthetic calendar `c1:` id equals the core `calendar_proof_id`
for the reference-close context. The synthetic population digest was computed once
with the core membership projection and embedded as a literal.

NOT executed: `compute_ef1` on these inputs, the worker, any DuckDB write or readback,
the example, mypy. Expected results are deliberately absent. Unverified assumptions:
the library reuses the regular-BAR population proof unchanged (producer text
`regular_bar_prices`), and accepts a bar whose end equals the actual close as the
complete regular prefix.

Remaining gates: library availability and manual run of the example, cross-layer
fixtures (compact contract fixtures expanded to canonical packets), worker and
sink readback (decimal128 coefficient, float64 hex, bool, state), source-evolution
declaration review, independent review, observed-source rights and release.
