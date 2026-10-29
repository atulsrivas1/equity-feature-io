# Retired and deferred builders

PO final status 2026-10-29.

- **tools/build_duckdb.py: RETIRED.** It snapshotted `packages/duckdb`, `packages/contracts` and `packages/features` from the core repository at a pinned commit to qualify the
  adapter against core archives. The adapter lives in this repository since ADR-1 and core no longer contains `packages/duckdb`, so the builder cannot run and cannot be ported without
  reintroducing that path. Its role is covered by `build_foundation`, `build_duckdb_sink`, `build_parquet`, `build_extensions`, `build_acquisition` and `build_files` (which build and qualify the
  adapter dependents against core archives) and by `tools/check_extraction.py`. The module stays only for `inspect_adapter`, used by `tests/duckdb/test_packaging.py`; `main()` refuses to run.
- **tools/build_matrix.py: DEFERRED (not blocking).** It reproduces the accepted archive matrix at fixed historical commits and `tests/matrix/accepted_archives.json`; both are historical evidence and are intentionally unchanged.
