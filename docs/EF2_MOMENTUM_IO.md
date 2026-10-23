# EF2 momentum and trend I/O source checkpoint - October 23, 2026

Status: source authored against the frozen momentum and trend contract (`intraday.momentum.v1`,
`ef2-conv1`, Amendment 1) by the EF2 I/O layer (EF2-IO
[#609](https://github.com/atulsrivas1/equity-features/issues/609)). See the
[supplied-input API](api/EF2_MOMENTUM_INPUTS.md). No indicator mathematics, no sink/SDK/version change.

Executed (Python 3.12, `python -I`, core main 70e8bb2 with the merged library): all 100 contract result
fixtures build (117 runs counting the prefix fixtures P01 to P03 as series A and B at every prefix
length) with generic canonical validation; every synthetic config is byte-identical to the library
`build_momentum_config` (so the builder is kept); every run goes through `compute_momentum` and matches
the contract value (tolerance or exact_plus_zero, `+0.0` bit-checked), status, reasons, expected and
observed with zero mismatches, and the evidence rows match. Each result was published as its own
generation to a new scratch DuckDB sink (float64 with `DMI points`, `stochastic points`,
`Williams %R points` and `currency/share`; no unit refusal) and read back identical bit for bit, an
idempotent republish returned the same receipt, and a close/reopen read matched.
`tools/check_extraction.py` with the core root exited 0.

NOT executed: the worker, mypy, independent oracle, the 23 refusal fixtures E01 to E23 (library side).

Remaining gates: worker and sink readback, source-evolution declaration review, independent review,
observed-source rights and release.
