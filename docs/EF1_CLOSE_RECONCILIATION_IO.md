# Close-reconciliation I/O source checkpoint - October 22, 2026

Status: source authored against the frozen `ef1-close-compare1` contract by the
EQ212 [#570](https://github.com/atulsrivas1/equity-features/issues/570) I/O layer for
EQ168 [#508](https://github.com/atulsrivas1/equity-features/issues/508). The pure
library producer is authored in parallel; nothing below was executed against it.

Added the [supplied-input API](api/EF1_REFERENCE_CLOSE_INPUTS.md), the exact four-role
nullable container, lossless conversion, the `k1:` reference-id encoder, the config
builder and three original synthetic requests. No fetching, source-specific schema,
BPS or tolerance mathematics, close selection or sink/SDK/version change.

Actually executed (Python 3.12, core main c754e5d with the merged library producer
on the path): C01/C02/C03 run through compute_ef1 giving within_tolerance (BPS 0.0,
supplied 1250), outside_tolerance (BPS 79.36507936507937, supplied 1260) and
reference_unavailable (all numeric outputs null). The library build_ef1_config
reproduces each synthetic config byte for byte, so make_reference_close_config
matches it too. The public example ran. Each result published to a new scratch
DuckDB sink and read back identical (decimal128 coefficient, float64 hex-exact,
bool, string, the bps unit), also after close/reopen. tools/check_extraction.py with
the core root exited 0. Expected results are deliberately absent from the fixtures.

NOT executed: the worker, mypy, independent oracle comparison.

Remaining gates: library availability and manual run of the example, cross-layer
fixtures (compact contract fixtures expanded to canonical packets), worker and
sink readback (decimal128 coefficient, float64 hex, bool, state), source-evolution
declaration review, independent review, observed-source rights and release.
