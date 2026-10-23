# EF2 money-flow and retracement I/O source checkpoint - October 23, 2026

Status: source authored against the frozen `ef2-mf1` / `ef2-retrace1` contract by the EF2 I/O
layer (EF2-IO [#609](https://github.com/atulsrivas1/equity-features/issues/609)) for EQ-150
[#484](https://github.com/atulsrivas1/equity-features/issues/484) and EQ-238
[#663](https://github.com/atulsrivas1/equity-features/issues/663). See the
[supplied-input API](api/EF2_MONEY_FLOW_RETRACEMENT_INPUTS.md). No indicator or retracement
mathematics, no extremum derivation, no sink/SDK/version change.

Executed (Python 3.12, `python -I`, core main 364fe61 with the merged library): all 68 synthetic
fixtures build with generic canonical validation (money flow in both empty-slot forms); every synthetic
config is byte-identical to the library `build_money_flow_config` / `build_retracement_config`
(so both builders are kept); all 36 money-flow and 32 retracement fixtures run through
`compute_money_flow` / `compute_retracement_level` and match the contract value (int64 exact, float64
by `float.hex`), status, reasons, expected and observed with zero mismatches. Each result was published
as its own generation to a new scratch DuckDB sink and read back identical (int64 `shares` OBV,
float64 `shares`, `fraction`, `currency/share`), an idempotent republish returned the same receipt, and a
close/reopen read matched. `tools/check_extraction.py` with the core root exited 0.

NOT executed: witnesses/evidence comparison against the contract, the worker, mypy, independent oracle.

Remaining gates: library availability and manual run, worker and sink readback, source-evolution
declaration review, independent review, observed-source rights and release.
