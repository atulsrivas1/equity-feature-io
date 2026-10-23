# EF2 Ichimoku and price-channel I/O source checkpoint - October 23, 2026

Status: source authored against the frozen Ichimoku and price-channel contract (`ef2-v1`,
`ef2-channels-v1`) by the EF2 I/O layer (EF2-IO
[#609](https://github.com/atulsrivas1/equity-features/issues/609)). See the
[supplied-input API](api/EF2_CHANNELS_INPUTS.md). No indicator mathematics, no sink/SDK/version change.

Executed (Python 3.12, `python -I`, core main a53f440 with the merged library): all 74 contract result
fixtures build with generic canonical validation; every synthetic config is byte-identical to the
library `build_channels_config` (so the builder is kept); every fixture goes through `compute_channels`
and its 313 headers match the contract value (tolerance, exact ranking/boolean, or `+0.0` bit-checked),
status, reasons, expected and observed with zero mismatches, and the evidence rows match. Each result was
published as its own generation to a new scratch DuckDB sink (float64 with `currency/share` and
`fraction`, and bool with `boolean`; no dtype or unit refusal) and read back identical bit for bit, an
idempotent republish returned the same receipt, and a close/reopen read matched all 74.
`tools/check_extraction.py` with the core root exited 0.

NOT executed: the worker, mypy, independent oracle, the 21 refusal fixtures (library side).

Remaining gates: worker and sink readback, source-evolution declaration review, independent review,
observed-source rights and release.
