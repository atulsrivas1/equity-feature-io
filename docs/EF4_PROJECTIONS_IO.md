# EF4-I2 supplied projections I/O source checkpoint (EQ-172)

Status: source authored against the frozen EF4 contract I2 (`ef4-proj1`, `ef4-rel1`, `ef4-rate1`; core
`docs/ef4/PATH_PROJECTIONS_CONTRACT_PROPOSAL.md`, implementation rulings in `PATH_PROJECTIONS_IMPLEMENTATION.md`) by the
EF4 I/O layer (EF4-IO #613, EQ-172). Module: `packages/duckdb/src/equity_feature_duckdb/ef4_projections.py`. No package
version change, no sink change, no worker.

Pinned rulings: one BAR batch per role with per-slot coverage `bar:<i>` (the epoch bar delivery is concatenated here);
declared aggregate coverage on every batch; `core_benchmark_ids` passed to the core builder (encoded as canonical JSON
text by the library); daily role keyed by (instrument, session) with the library DUPLICATE check; REFERENCE evidence
boundary `ordinary` (library); unique input ids across legs and membership roles (library).

Executed (Python 3.12, `python -I`, scratch manual run only; no unit tests by owner policy):

- All 111 result fixtures (22 session, 19 bar, 39 relative, 31 rate; 340 outputs) were mapped from the compact notation,
  computed through the core builders and computation, published to a new DuckDB file per fixture and read back. Two id
  bindings were used (all instrument, benchmark, session, grid and namespace ids renamed). Result: 111 of 111 matched
  under both bindings, status, reasons, expected and observed counts, values per the acceptance rule, and the sink round
  trip equal to the library output. A republish returned the same receipt.
- All 114 refusal recipes were applied to their base fixtures and run through the adapter. Result: 114 of 114 raised the
  recorded error code. 26 were refused at I/O (this layer or the shared batch rules while batches were built) and 88 by
  the library.
- `tools/check_extraction.py --core-root C:\Atul\Claude\equity-features` exited 0 with `ef4_projections.py` declared in
  `EF1_SOURCE_EVOLUTION.json` and the check list.

Deviations and risks:

- 13 recipes are refused at I/O where the contract records the producer admission or the library (or the reverse for
  SPR12 and SPR13): the canonical batch constructors refuse wire type and precision faults, unknown adjustment basis
  values, and REFERENCE identity duplicates before the library runs. Codes match; the layer differs.
- SPR12 and SPR13 are not reached as recorded. The recipes name an interval that does not belong to the session they
  give, so the library refuses INCONSISTENT_IDENTITY (row not on the governed grid) or INVALID_ORDER (library grid order)
  before a shared DUPLICATE or INVALID_ORDER. The recorded code is still reached by none of the layers for those rows.
- Refusal classification was run on the scratch harness only; no commit of the harness.
- NOT executed: a worker or release run, mypy, a negative control on the adapter, an independent oracle beyond the contract's
  hand-derived values, the source-evolution declaration review, and release acceptance (EQ-163).
