# EF4-H quote dynamics and VWAP path I/O source checkpoint - October 23, 2026

Status: source authored against the frozen EF4-H contract (`ef4-quote1`, `ef4-vwap1`, algorithms `ef4-quote-dynamics-v1`
and `ef4-vwap-path-v1`) by the EF4-H I/O layer (EQ-159 and EQ-160). See the [supplied-input API](api/EF4_QUOTE_VWAP_INPUTS.md).
No mathematics, no sink or package version change, no worker.

Library: core `main` commit `c4042b8` (EF4-H library PR #707 merged, then #710). The library was run from a `git archive` of
that commit in a scratch directory. The shared core checkout was not modified.

## Executed (Python 3.12, scratch runner inserting the core and io package source roots)

- Results: all 69 result fixtures (30 quote, 39 VWAP) were fed through the adapter. Each fixture was expanded from the contract
  notation with the fixture-expansion model (`build_model`); null roles were undelivered. Every selected output was computed
  as its own selection (witness lists), and the joint selection was computed and published. 507 of 507 output cells matched
  the contract: status, reasons, expected and observed counts, witnesses in order, and the value under its acceptance rule
  (exact integer; bit-exact float64 for `exact_float64`; bit-exact `+0.0` for `exact_plus_zero`; the 8 ulp or 1e-12 tolerance
  otherwise).
- Round trip: 69 of 69 joint results were published as one generation each to one new scratch DuckDB file, read back, and
  compared with the library output by canonical encoding (every float by its hex, evidence rows included). After close and
  reopen, 69 of 69 read back identical.
- Configurations: the adapter envelope equals the core builders (`build_quote_dynamics_config`, `build_vwap_path_config`) for
  every result request.
- Refusals: all 80 refusal recipes were applied to their base model with the harness `apply_ops`, then passed through the
  adapter and the library. 80 of 80 raised the stated error code. Layer observed: 29 at the I/O boundary (adapter batch
  construction, the shared batch validator, or the shared batch constructor) and 51 in the library.
- Layer differences from the contract's `raised_by`: RQ09 (`S.cutoff`, stated shared validator) is raised by the library,
  because the batch validator does not see the market cutoff. RQ12 (`L.batch_kind`, stated library) is raised by the shared
  batch constructor, because the column schema fixes the kind. RV43 (`S.bar_notional_bounds`, stated shared validator) is
  raised at the I/O boundary, which is the shared validator's position here. Configuration recipes (C.*) pass their mutated
  values through the adapter as supplied parameters and are refused by the library. `C.capability` is refused by the library
  capability guard, since capability is not a `ConfigSpec` field.
- Harness self-check: `ef4h_fixture_expand.py` on the frozen contract reports all 69 result fixtures and 80 refusal recipes
  matching the independent recompute (507 outputs compared).
- `python -I tools/check_extraction.py --core-root C:\Atul\Claude\equity-features` exits 0. The new adapter is declared in
  `EF1_SOURCE_EVOLUTION.json` and listed in the extraction check's additive set (the check hardcodes that set, as it did for EF3).
- The synthetic example (`examples/ef4_quote_vwap.py`) runs and prints the two configurations and role sizes.

## Deviations and choices

- Module constants: `NAMESPACE`, source, snapshot (`snap`) and mapping labels only. Entity, session, interval, grid version,
  series policy, proof and series ids are caller values. The runner used the contract placeholders `I`, `S0`, `G` and `P`.
- Reference identities use the library grammar `x1:` plus unpadded base64url. The contract notation `x1:B(text)` denotes that
  encoding; the runner maps the fixture notation with the same encoding.
- Coverage: every event role is declared explicitly. Quote and trade rows use an aggregate plus one interval entry named by the
  scope. Bars use per-slot entries (complete rows, incomplete rows, declared gaps) with an incomplete aggregate. Grid, bounds and
  proof facts are declared complete. A trade role delivered without a declaration in a fixture (RV31 mutation) is declared
  complete by the runner, because the recipe mutates delivered rows and the model carries no declaration.
- Config envelopes: the adapter builds the same `ConfigSpec` as the core builders and passes caller parameters through unchanged.
  The runner proves equality with the core builders on all 69 results.
- Basis: `adjustment(basis)` maps a supplied basis to an `AdjustmentSpec`. Non-raw bases use placeholder labels; the L.basis
  recipes are refused by the library's adjustment check.
- OHLC: bars carry supplied OHLC columns only when a supplied bar has them, so the base fixtures keep the default column set.
- Harness reuse: the fixture model builder and mutation engine of the contract harness are imported from a scratch copy, which
  was not modified. The runner wraps the harness builder for null roles, since the builder expects delivered roles.
- No unit tests (owner policy). Manual runs only.

## NOT executed

Unit tests (policy), mypy, the EF4 worker, the EF4 shared amendment (identifiers, coverage declaration form and the result-wide
evidence cap are pinned in the core documentation only), observed-source admission and rights, release acceptance, and any
performance claim.

## Remaining gates

Independent review of the adapter, the shared-amendment ruling on the layer of RQ09, RQ12 and RV43, the worker and sink readback in
the worker layer, and release.
