# EF5 price structures I/O source checkpoint - October 28, 2026

Status: source authored against the frozen EF5 contract (`ef5.candle`, `ef5.structure`, `ef5.technical`; core
`docs/ef5/PRICE_STRUCTURES_CONTRACT_PROPOSAL.md`, errata `EF5_LIBRARY_ERRATA.md`) by the I/O layer. See the
[supplied-input API](api/EF5_PRICE_STRUCTURES_INPUTS.md). No mathematics, no sink/SDK/version change, no package version bump,
no new unit tests (policy); the fixture gate is `tools/verify_ef5_io.py`.

Executed (Python 3.12, pinned venv, core main with the merged EF5 library): the gate expanded every contract fixture to supplied
rows with `equity_feature_duckdb.price_structures`, built the context, BAR chunks and closed configuration with the adapter, computed
through `compute_ef5` and compared with the contract literals.

- 89/89 result fixtures (534 runs, each output alone and jointly): status, reasons, expected and observed counts, witnesses, value
  by the contract acceptance rule and the echoed adjustment basis (carried by the input bindings, errata E-L2) match.
- Adapter configurations are identical (parameters, identity, algorithm) to the library `build_ef5_config` for the same context.
- The library result survives the SDK codec round trip (`encode_result` / `decode_result`) for bool, int64 and float64 columns.
- 59/59 refusal recipes raise the recorded code (12 codes); 31 are already raised at the adapter.

Rulings honoured: E2 (rows delivered with coverage not declared are refused INVALID_SCHEMA at the adapter, `declare_coverage` has no
default, nothing is declared complete on the caller's behalf); known_at is passed exactly as supplied (`None` is unknown availability,
never defaulted); a negative volume is INVALID_SCHEMA (RF14); a missing adjustment policy version is UNSUPPORTED_ADJUSTMENT (RF55), a
missing label or parameter INVALID_CONFIG; the shared `AdjustmentSpec` defaults are never read.

Defaults applied by this layer (the brief list the contract requires): none. The compact notation's default known_at token and volume
exist only inside the gate, which states and passes them explicitly.

Not executed: the worker, mypy beyond `packages/duckdb/src`, DuckDB-backed observed sources, the sink readback in the shared runner,
bundles for the new roles (the bundles format is `session.compute_trades.v1` only), rights and release gates.
