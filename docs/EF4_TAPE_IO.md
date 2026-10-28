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

1. Shared codec (io-sdk `codec.py`, `_notional_cell`). Superseded by the rank-aware check (see "Refresh" below). The first draft rebuilt a top-K cell through the shared constructor and fell back to `object.__new__` on `INVALID_ORDER`. The merged codec decides by the feature id instead: only a `tape.top_k_notional` column is decoded as a notional-ordered cell, after the bounds, row-type and duplicate-identity checks and a rank check on `(-price * size, event_ns, order_key, event_id)`; a cell out of rank is refused `INVALID_CONTENT`. Every other feature keeps the shared size-ranked constructor.
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

- Closed (see "Refresh"): the codec re-checks the notional rank on read, so a reordered cell with a valid encoding is refused `INVALID_CONTENT`.
- The top-K cell is built by `object.__new__` in the library (`notional_cell`) and in the codec fallback; any later `replace` or constructor rebuild raises `INVALID_ORDER` until the amendment lands.
- Two refusal codes differ at the I/O layer (above).
- Session end and the seed scope (`open - 1` to `open`) are adapter choices; they are not in the contract and are visible in the API.

## Refresh - October 28, 2026 (matches io `main` 31590b1)

This section supersedes the statements above where they differ.

- Coverage fails closed (io #51). A TRADE batch with rows and no declared `coverage` is refused `INVALID_SCHEMA` ("coverage not declared") at `tape.py` `trade_batch`; it is never defaulted to complete. A batch with no rows and no coverage is the declared empty batch (`Coverage(0, 0, True)`).
- Rank-aware notional check (io-sdk codec, merged). See deviation 1: the decoder is keyed by the feature id `tape.top_k_notional` and refuses an out-of-rank cell `INVALID_CONTENT`. The risk "codec does not re-check notional order" is closed.
- Refusal drivers unchanged: 73 of 75 recipes raise the contract code (RF18 and RF35 differ as described above); the shared constructor still refuses notional-ordered cells in library code paths, which is why the codec builds the cell itself.
- Parquet round trip (executed, scratch driver, io `main` 31590b1, Python 3.12, pyarrow 20.0.0): a `tape.top_k_notional` result with a cell whose notional order differs from the size order (3 rows, k = 3) was written with `ParquetSink`, read back by its receipt and read again after closing and reopening the sink. Both readbacks are byte-equal to the library result under `encode_result`. A bar projection result with dollar outputs (`projection.up_dollar_volume`, `down_dollar_volume`, fraction) round trips the same way.
- Bundles (executed): the `bundles` package does not carry EF4 results. `write_bundle` accepts only the `session.compute_trades.v1` shape and refuses an EF4 configuration `unsupported_version`. Its typed decoder (`_typed.py`) still rebuilds `TopKTrades` through the shared size-ranked constructor and refuses a notional-ordered cell (`ContractError`: "topK rows must be ranked"). Because no EF4 result can reach that decoder through `write_bundle`, this is recorded as an accepted limit, not changed here. Bundle support for EF4 would need both a producer shape and a feature-keyed decoder.
