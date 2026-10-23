# EF3 robust history, volume pace and mean-ratio I/O source checkpoint - October 23, 2026

Status: source authored against the frozen EF3 contract (`ef3-robust1`, `ef3-pace1`, `ef3-mean1`) by the EF3 I/O layer
(EF3-IO [#611](https://github.com/atulsrivas1/equity-features/issues/611)). See the
[supplied-input API](api/EF3_ROBUST_PACE_INPUTS.md). No mathematics, no sink or package version change, no worker.

Spec and library: core `main` commit `6adf840` (EF3 robust history, volume pace and mean-ratio producers, PR #694). The
library was run from a `git archive 6adf840` export at `C:\Users\MONIKA~1\AppData\Local\Temp\ef3e-io-scratch\core`
(equivalent to a `6adf840` worktree). The real core checkout `C:\Atul\Claude\equity-features` is on detached `d8ed913`,
which predates the robust modules; it was used only as the `--core-root` for `tools/check_extraction.py`.

Executed (Python 3.12, `python -I`, scratch harness inserting the core and io package source roots):

- Results: all 124 result fixtures (44 history, 24 cohort, 37 pace, 19 mean-ratio) were built with the adapter, computed
  by the library and compared per output with the contract: status, reasons, expected and observed counts, value (bit
  exact float64 or exact int64 `cohort.rank`, R17 tolerance where the fixture says so), and witness ids in order. 406 of
  406 outputs matched. Each output was computed as its own selection, the contract's per-output evidence list.
- Configurations: the adapter envelope of every result equals the library builder called with the same explicit
  parameters (ConfigSpec equality).
- Prefix: H25, P18 (alternate construction, below) and R16 were built with appended later sessions and matched their base.
- Refusals: all 48 refusal fixtures were built from a valid base with one violation each. All 48 raised the contract's
  code (48 of 48) from the adapter's batch build or from the library. One sub-case per fixture, not the 63 sub-cases of
  the EF3-D checkpoint.
- Sink: each of the 124 joint results (one selection of all listed outputs of its fixture) was published as its own
  generation to a new scratch DuckDB file. A republish in the same session returned the same receipt for all 124. After
  close and reopen, every result read back bit-identical (binary64 bits, `+0.0`, statuses, reasons, counts, evidence).
- `python -I tools/check_extraction.py --core-root C:\Atul\Claude\equity-features` (real checkout, `d8ed913`) exited 0 with
  `robust_pace.py` declared in `EF1_SOURCE_EVOLUTION.json`. The same change also corrected the stale declared digest of
  `relative_rv.py` (`b119cfec...` to `07e26cc2...`, the committed blob).
- The synthetic example (`examples/ef3_robust_pace.py`) runs and prints the three configurations and the role sizes.

Deviations and choices:

- `python -I` ignores `PYTHONPATH`, so the scratch harness inserts the core and io package source roots itself.
- Reference identities use the closed `x1:` form: `x1:` plus the unpadded URL-safe base64 of the id text. The contract's
  `x1:B(id)` is notation for that encoding; the literal string is refused by the library.
- Instruments: the contract names no instrument id for any fixture. Entity-level runs use the id `Q9` (not `X`), with
  every builder taking an explicit `instrument_id`. Cohort members keep the contract's names; a variant run renaming
  member `A` to `X` (24 cohort fixtures) matched the contract, so no name is inferred from an instrument. Coverage
  entries are named by an explicit role (`session` or `member`).
- Session ids are the bare governed index (`"0"`, `"5"`) because the contract's witnesses are `session:5`.
- Cohort-only fixtures do not state `window` or `min_history`; the envelope needs both, so the cohort harness passes 1 and 1.
  Cohort outputs do not read them.
- `grid_version` is the fixed label `ef3-grid1`; the contract fixtures do not state one.
- P18 cannot be built literally (the appended session's bars would lie after the market cutoff that the target's bucket
  evaluation needs). It was built with the target closing at offset 200 and the market cutoff at offset 1500, so the
  appended session (bucket 1, volume 12345, known at 150) lies before the cutoff. The evaluation bucket is 1 and the
  result equals P01b, as the contract's own note states.
- Price rows carry volume 100 with open = high = low = close = c. A null price row carries null OHLC and volume 0 (zero
  volume with null OHLC is the shared rule; a positive volume with a null price is refused). The volume of a priced price
  row is not read by any output.
- Exclusion-only slots (`["xu"]`, `["xf"]`) carry a placeholder value 1 in the row; the value is ignored because the
  session is excluded.
- Excluded sessions keep their row with the fixture value, so the ignored-value property is exercised.
- Refusal construction: a case that the shared validators reject while the batch is built counts as refused there; a case
  reached only by the library counts as refused in compute. Both are reported with the contract's code.
- The core library and the contract were not changed.

NOT executed: the EF3 worker (#612), mypy, an independent oracle beyond the contract's hand-derived values, the
source-evolution declaration review beyond `check_extraction.py`, observed-source rights and release acceptance (EQ-157).
The 124-fixture and 48-refusal harness, and the publication script, are scratch code and are not committed.

Remaining gates: worker and sink readback in the worker layer, independent review of the adapter, the header-ledger and
shared-contract amendment (the core implementation note's review items), source-evolution declaration review, and release.
