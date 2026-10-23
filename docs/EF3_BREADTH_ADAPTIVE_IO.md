# EF3 breadth and adaptive volume I/O source checkpoint - October 23, 2026

Status: source authored against the frozen EF3 contract (`ef3-breadth1`, `ef3-obsbreadth1`, `ef3-adaptive1`) by the EF3 I/O layer
(EF3-IO [#611](https://github.com/atulsrivas1/equity-features/issues/611)). See the
[supplied-input API](api/EF3_BREADTH_ADAPTIVE_INPUTS.md). No mathematics, no sink or package version change, no worker.

Spec and library: core `main` commit `ee92759` (EF3 breadth and adaptive volume library producers, PR #695). The library was
run from a detached worktree of that commit at `C:\Users\MONIKA~1\AppData\Local\Temp\ef3f-io-scratch\core-wt`. The shared
checkout `C:\Atul\Claude\equity-features` was not modified. That worktree was also the `--core-root` for
`tools/check_extraction.py`.

Executed (Python 3.12, `python -I`, scratch harness inserting the core and io package source roots):

- Results: all 99 result fixtures (49 declared, 20 observed, 30 adaptive) were built with the adapter. Each output was computed
  as its own selection and compared with the contract: status, reasons, expected and observed counts, value (exact int64, or
  float64 bit pattern for fractions and ratios), and evidence rows in order. 1224 of 1224 output cells matched (784 declared,
  140 observed, 300 adaptive).
- Configurations: for every selection the adapter envelope equals the library builder called with the same explicit
  parameters (ConfigSpec equality), including the tolerance parameters present only when their output is selected.
- Prefix: AD06 was checked for j = 0..6 with `C = t_j + 1` (`t_0` taken as 1 ns). Each cutoff on the full stream equals the
  first-j-row stream for all ten outputs (7 of 7).
- Refusals: the 62 refusal fixtures (RB 30, RO 15, RA 17) were built as one violation each from a valid base (DB08, OB01,
  AD06). All 62 raised the contract code, either while a role batch was built (shared validator) or at compute (library or
  capability check). The phase was not recorded per case. Fixtures with two legs (RB14 eight and ten slots, RB18 both
  tolerance directions, RO05 two floors, RA09 two warm-up bounds) ran both legs.
- Sink: each of the 99 joint results (one selection of all listed outputs of its fixture) was published as its own generation
  to one new scratch DuckDB file. A republish in the same session returned the same receipt for all 99. After close and
  reopen, every result read back bit-identical (canonical encoding).
- `python -I tools/check_extraction.py --core-root C:\Users\MONIKA~1\AppData\Local\Temp\ef3f-io-scratch\core-wt` exited 0 with
  `breadth_adaptive.py` declared in `EF1_SOURCE_EVOLUTION.json` (sha256 `cd8aa244...` of the final module).
- The synthetic example (`examples/ef3_breadth_adaptive.py`) runs and prints the three configurations and the role sizes.

Deviations and choices:

- `python -I` ignores `PYTHONPATH`, so the scratch harness inserts the core and io package source roots itself.
- Instruments: the contract names no instrument id. Every builder takes the entity explicitly; the harness used the labels
  `SYN-BREADTH` (declared aggregate), `SYN-ROSTER-AGG` (observed aggregate) and `Q9` (adaptive). Member names are the
  fixture names.
- Identifiers chosen here (not in the contract, to be pinned by the amendment and #611): population id `SYN-POP`, revision
  `rev-1`, roster record set `SYN-ROSTER`, epoch `e1` (AD24 uses `e2` through its own `epoch` field), adaptive event ids
  `ev<sequence>`, session id `0`. Reference grammars are `x1:`, `bh1:` (six digit stint), `bf1:`, `ob1:`, `ao1:` (19 digit
  sequence) with the base64url text component; the contract's `B(id)` notation is that encoding.
- Coverage: a complete role declares its row count as expected (`Coverage(n, n, True)`); an incomplete role declares
  `Coverage(None, n, False)`. The contract's batch-level coverage is used; no per-interval entries.
- Session: one governed session `0` spanning `[0, 10^12)` ns. The population role's static bounds equal this session. The
  bound is a harness choice (wide enough for every fixture time), not a contract value.
- Units: declared and observed roles use scale 2 (the fixture default), the adaptive stream uses scale 0 for raw rates.
  Every role of one request carries the same PriceUnit.
- Fixture notation is not wire format. The population field `e` is not mapped (no contract meaning). Fixtures with
  `mode: reconstruction` (DB41, AD25) are mapped with the same `known_at` availability; the contract's outputs are matched
  exactly, so no reconstruction reason is carried.
- Evidence limits come from each fixture (`evidence_limit`), with no default in the builders. One selection per output
  reproduces the per-output witness lists; the evidence cap is result-wide in the library.
- The configuration envelope is rebuilt in the adapter (as in the robust-history adapter) and proven equal to the library
  builders by the harness; the adapter does not import the library.
- The roster row of another group that precedes the cutoff with null or future `known_at` (core implementation note 5,
  RULING NEEDED) is passed through unchanged; the library applies its current reading. No ruling is made here.
- The harness and the refusal constructions are scratch code and are not committed, following the robust-history checkpoint.

NOT executed: unit tests (policy), the EF3 worker (#612), mypy, an independent oracle beyond the contract's hand-derived values,
observed-source admission and rights, the EF3 shared amendment (identifiers, `evidence_limit` default, RULING NEEDED item),
release acceptance (EQ-157), and any performance claim beyond the author's own timings.

Remaining gates: worker and sink readback in the worker layer, independent review of the adapter, the header-ledger and
shared-contract amendment, the RULING NEEDED roster item, and release.
