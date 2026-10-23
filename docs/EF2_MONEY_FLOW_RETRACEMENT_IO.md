# EF2 money-flow and retracement I/O source checkpoint - October 23, 2026

Status: source authored against the frozen `ef2-mf1` / `ef2-retrace1` contract by the EF2 I/O
layer (EF2-IO [#609](https://github.com/atulsrivas1/equity-features/issues/609)) for EQ-150
[#484](https://github.com/atulsrivas1/equity-features/issues/484) and EQ-238
[#663](https://github.com/atulsrivas1/equity-features/issues/663). See the
[supplied-input API](api/EF2_MONEY_FLOW_RETRACEMENT_INPUTS.md). No indicator or retracement
mathematics, no extremum derivation, no sink/SDK/version change.

Executed (Python 3.12, `python -I`): all 36 money-flow and 32 retracement synthetic fixtures
build with generic canonical validation, money flow in both empty-slot forms; the R17 admission
function accepts every money-flow BAR chunk, and the config context chunks and digest equal the
R17 context codec byte for byte.

NOT executed (pending the library producers, `ef2-b-library`): computation against the
contract's expected values, the DuckDB sink round-trip of the new units and dtypes (int64 OBV,
float64 shares / fraction / currency per share), the worker, mypy.

Assumptions the contract leaves open (the config wire layout of the money-flow and retracement
parameters) are marked in the API document and must be reconciled with the library decoder
before the worker compares config digests.

Remaining gates: library availability and manual run, worker and sink readback, source-evolution
declaration review, independent review, observed-source rights and release.
