# EF4-G tape and notional top-K I/O source checkpoint - October 23, 2026

Status: source authored against the frozen EF4 contract (`ef4-tape1`, `ef4-notional1`, proposal `TAPE_CONTRACT_PROPOSAL.json`) by the EF4-G I/O layer (EQ-158 and EQ-162). See the [supplied-input API](api/EF4_TAPE_INPUTS.md). No mathematics, no worker, no release acceptance, no package version change.

Spec and library: core `main` commit `c4042b8` (EF4-G library, PRs #706 and #710), read with `git archive` into a scratch export. The shared core checkout was not modified. The fixture expander `ef4g_fixture_expand.py` was copied to scratch and imported unmodified.

## Executed (manual, Python 3.12, scratch runners; no unit tests, per owner policy)

- Results: every result fixture (50 window, 25 top-K, 7 partition-merge) under both identity bindings of the expander, through the adapter, the library, the DuckDB sink and back. Every output (status, reasons, expected and observed counts, witness list, value) matched the contract: integers exactly, float64 by bit pattern (stricter than the `tolerance` class). 1025 output cells compared. G01 to G03 (the generators: three window totals, two window totals with a seed, three top-K ids with the index-mod-4 partition merge) matched their stored expectations.
- Round trip: 227 of 227 results (fixtures, merged results, partial results and generator results) were written as one generation each to one new scratch DuckDB file, the sink was closed and reopened, and every result was read back by its receipt. Each read-back result equals the library output and has identical canonical bytes (`encode_result`).
- Refusals: all 75 recipes through the adapter and the library under both bindings. 73 of 75 recipes raise the contract code (146 of 150 binding legs). 16 recipes are refused by the I/O layer (adapter batch construction and shared validators) and 59 by the library. Two recipes raise a different code at the I/O layer (below).
- The author's stdlib recompute harness (`ef4g_fixture_expand.py`) on the same contract exits 0 (`OK`), so the contract values used as the reference are internally consistent.
- Example `examples/ef4_tape.py` runs. `examples/ef3_breadth_adaptive.py` still runs (regression for the shared codec change).

## Deviations and choices

1. Shared codec (io-sdk `codec.py`, `_top_k_cell`). A top-K cell is first rebuilt through the shared constructor, as before. Only on `INVALID_ORDER` (a notional-ordered cell) does it assemble the stored fields with `object.__new__`, after the same bounds, row-type and duplicate-identity checks. Size-ranked cells (EF1 to EF3) take the unchanged path. This is the ruling "the sink must store and read the cell fields, not rebuild through the public constructor"; the rank-aware order check is still missing from the shared validator and is the EF4 shared amendment item.
2. Session end. A fixture `close` is used when present; a closing-auction session ends at the cutoff C (the harness notation `close = C`); every other session ends at `9 * 10^18` ns (a harness choice, not a contract value).
3. Seed reference id `x1:` plus the unpadded URL-safe base64 of the caller's seed-set id (the contract's `x1:B(seed_set_id)`). Seed-set identities are the runner's `seedset-a` and `other`, taken from the notation of the fixture bindings.
4. Reconstruction fixtures (W17, TK10e) use `mode = reconstruction` with the identity label `ef4-supplied-reconstruction`. The contract names no label; the label is an adapter constant.
5. Eligibility policy. The fixtures carry no eligibility policy; the runner passes `eligible_trade` explicitly (the label the EF1 synthetic contexts use). It is a caller parameter of every builder, not a constant.
6. Parameters are passed as supplied, including `policy_version` and any extra parameter (`extra_parameters`). An earlier adapter draft hard-coded the policy version and dropped extra parameters; the refusal run caught it (RF27, RF29, RF53, RF66) and it was fixed before the final run.
7. Top-K witnesses are plain `event_id` (the result validator binds a top-K row to its evidence by `row_id == event_id`); window witnesses keep `trade:` and `seed:` prefixes.
8. Window evidence is bounded result-wide by the library (`evidence_limit * 9`); the adapter passes the config parameter unchanged.
9. Refusal RF69 (a supplied partial whose rows arrive in the delivered order n1, n4, n7) is not an adapter input. The runner built that partial by reordering the computed partial's cell rows, and the library's merge refused with `INVALID_ORDER` as the contract requires.
10. Generator runs use the instrument and session `G` (the generator's own labels), price scale 0 and evidence limit 0 for window totals.

## Refusal code mismatches at the I/O layer (not hidden)

- RF18 (`batch_kind = quote`): the shared batch validator refuses first with `UNSUPPORTED_SAMPLING` (the quote kind carries the trade sampling label). Contract code `INVALID_SCHEMA`.
- RF35 (`seed.count = 2`, two identical `ef4.tick.seed` facts): the shared REFERENCE validator refuses first with `DUPLICATE`. Contract code `INVALID_SCHEMA` ("exactly one seed fact").

Both are refusals of the supplied input; the difference is the code of the first shared validator, not whether the input is accepted.

## Not executed

Unit tests (owner policy), mypy and lint beyond compilation, an independent oracle beyond the contract's hand-derived values and the author harness, the EF4 worker, the shared EF4 amendment (rank-aware `TopKTrades` order check, header ledger), release acceptance (EQ-163), installed-artifact runs, and performance claims.

## Risks

- The codec fallback does not re-check notional order on read: a stored notional-ordered cell is trusted once its canonical bytes match. The canonical byte check and the library's identity bindings still detect a changed record, but a forged, reordered cell with a valid encoding would not be refused on read.
- The top-K cell is built by `object.__new__` in the library (`notional_cell`) and in the codec fallback; any later `replace` or constructor rebuild raises `INVALID_ORDER` until the amendment lands.
- Two refusal codes differ at the I/O layer (above).
- Session end and the seed scope (`open - 1` to `open`) are adapter choices; they are not in the contract and are visible in the API.
