# EF3 relative statistics, daily log volatility and realized variance I/O source checkpoint - October 23, 2026

Status: source authored against the frozen EF3 contract (`ef3-rel1`, `ef3-dlv1`, `ef3-rv1`, Amendment 1) by the EF3
I/O layer (EF3-IO [#611](https://github.com/atulsrivas1/equity-features/issues/611)). See the
[supplied-input API](api/EF3_RELATIVE_RV_INPUTS.md). No mathematics, no sink or package version change, no worker.

Executed (Python 3.12, `python -I`, core `main` at d8ed913 with the merged EF3 library, PR #692):

- All 62 result fixtures (24 relative statistics, 17 daily log volatility, 21 realized variance) were built with the
  adapter, computed by the library and compared with the contract: values (R17 tolerance, or bit-exact where the
  fixture says `bits`), status, reasons, expected and observed counts, witnesses per output (one-output selection), and
  the joint evidence list where the contract gives one. Result: 62 of 62 matched, 0 mismatches. The adapter envelope
  of every relative, daily and realized-variance config is equal to the library builder for the same parameters.
- Prefix property: PX01 (three variants) and PX02 (three variants) were built with later sessions on the local grid and
  matched their base results (6 of 6). PX03 is not constructible with later bars under the R17 context; it was checked
  through its base RV21, whose slots and expected values equal RV07, and RV21 matched the library.
- Refusals: all 48 refusal fixtures were built from a valid base with the one violation described (63 sub-cases,
  including the boundary values of each parameter). All raised the contract's error code (48 of 48). Two sub-cases
  (RF19, RF26, zero close) were refused by the shared canonical BAR validation while the adapter built the batch, before
  the library ran; the code is the contract's INVALID_SCHEMA. The corresponding RF40 (null or zero close), RF41 (zero
  volume with OHLC) and RF42 (negative volume) sub-cases are likewise refused at batch build by that shared validation
  (INVALID_SCHEMA, INVALID_SCHEMA, BOUNDS), not by the library.
- Sink: each of the 62 joint results was published as its own generation to a new scratch DuckDB file (double values
  with their hex form, status, counts, reasons and evidence rows). A republish returned the same receipt. After close and
  reopen, all values were bit-identical (`struct` binary64 comparison, including `+0.0`), and all statuses, reasons,
  counts and evidence rows matched.
- `tools/check_extraction.py --core-root C:\Atul\Claude\equity-features` exited 0, with `relative_rv.py` declared in
  `EF1_SOURCE_EVOLUTION.json` and the check list.
- The synthetic example (`examples/ef3_relative_rv.py`) runs and prints the three configurations.

Deviations and choices:

- `python -I` ignores `PYTHONPATH`, so the scratch harness inserts the core package paths itself.
- The compact notation omits the close of an `unknown` slot. The adapter uses the placeholder close 1 (documented in the
  API); the slot is never READY and no output uses it.
- The 62/62 harness and the PX03 construction (RV21 check) are uncommitted scratch. The refusal harness (which reads the
  contract JSON read-only and builds the bad inputs) is scratch code too. Only the adapter and the synthetic example
  are in the repository.
- The core library and the contract were not changed.

NOT executed: the EF3 worker (#612), mypy, an independent oracle beyond the contract's own hand-derived values, the
source-evolution declaration review, observed-source rights and release acceptance (EQ-157).

Remaining gates: worker and sink readback in the worker layer, independent review of the adapter, source-evolution
declaration review, and release.
