# EF4-I2 supplied projections I/O source checkpoint (EQ-172)

Status: source authored against the frozen EF4 contract I2 (`ef4-proj1`, `ef4-rel1`, `ef4-rate1`; core
`docs/ef4/PATH_PROJECTIONS_CONTRACT_PROPOSAL.md`, implementation rulings in `PATH_PROJECTIONS_IMPLEMENTATION.md`, core
`origin/main` 2517ce5) by the EF4 I/O layer (EF4-IO #613, EQ-172).

Modules:

- `packages/duckdb/src/equity_feature_duckdb/ef4_projections.py`: supplied-input mapping and hand-built core envelopes.
  Imports only `equity_feature_contracts` and this package's EF3 daily grid codec (`relative_rv`). No core import.
- `packages/duckdb/src/equity_feature_duckdb/ef4_projections_sink.py`: optional DuckDB publication through the SDK path.
  Optional dependencies, imported lazily inside `publish_results`: `equity-feature-io-contracts`,
  `equity-feature-io-sdk`, `equity-feature-duckdb-sink`. Not imported by the adapter.

No package version change, no sink change, no worker. The core library is not modified.

Mapping rules: one BAR batch per role (the epoch bars arrive as one flat list here; the chunked R17 delivery is not
modelled, so no chunks are concatenated), per-slot coverage `bar:<i>` (session projection `slot:<i>`), declared aggregate
coverage on every batch, `core_benchmark_ids` as canonical compact JSON text, REFERENCE reference ids in the closed
`x1:` grammar. Envelopes are built by hand in the core parameter layout; supplied parameters are passed through
unvalidated, so the core decoder refuses bad or unknown ones.

Executed (Python 3.12, `python -I`; scratch manual driver only, not committed; no unit tests by owner policy), core
`origin/main` 2517ce5:

- All 111 result fixtures (22 session, 19 bar, 39 relative, 31 rate; 340 outputs) were mapped by the adapter, checked
  against the core builders (envelope equality 222 of 222 builder calls), computed by the core library and published to
  a new DuckDB file per fixture, then read back. Two id bindings (all instrument, benchmark, session, grid and namespace
  ids renamed). Result: 111 of 111 matched under both bindings: status, reasons, expected and observed counts, values per
  the acceptance rule, and the sink round trip equal to the library output. Grid digests equal the core digests (82 of 82).
  A republish returned the same receipt.
- All 114 refusal recipes were applied to their base fixtures and run through the adapter and the core library. Result:
  114 of 114 raised the recorded error code. 26 were refused at I/O and 88 by the library.
- `tools/check_extraction.py --core-root C:\Atul\Claude\equity-features` exited 0 with both new modules declared in
  `EF1_SOURCE_EVOLUTION.json` and the check list.

Layer attribution against the recorded `raised_by` (13 recipes; codes all match):

- 11 recipes recorded as producer admission are refused at I/O, by the shared canonical batch constructors (wire type and
  precision faults, unknown adjustment basis, REFERENCE identity duplicates): SPR10, SPR11, SPR18, BPR10, BPR20, RXR22,
  RXR26, RXR27, RXR28, RXR33, RPR27.
- SPR12 and SPR13 are library checks: with the wire session names bound to the bound session ids, the library refuses
  them with DUPLICATE and INVALID_ORDER. They are not refused at I/O; they are recorded as shared validator in the
  contract.

Risks and not executed: a worker or release run, mypy, a negative control on the adapter, an independent oracle beyond the
contract's own hand-derived values, the source-evolution declaration review, and release acceptance (EQ-163).
