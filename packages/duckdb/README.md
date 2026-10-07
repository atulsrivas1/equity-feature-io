# Experimental DuckDB adapter

`equity-feature-duckdb`0.1.0a8 is optional and stays outside both pure packages.
It resolves bounded catalog metadata and maps owned retained-source columns into
canonical schema1. Bounded original-Parquet historical reads use caller-supplied
sessions, explicit coverage policies and exact UTCns predicates. R4 is incomplete.

Callers declare snapshot, units, price interpretation/rounding, source clock,
instrument/session identity and trade eligibility evidence. Missing/null/zero,
unknown known-at, substitutions and unverified admission stay explicit. Hashes
bind bytes; they do not establish provider truth, rights, completeness or PIT.

See repository docs/api/DUCKDB_RESOLVER.md, docs/api/DUCKDB_MAPPING.md and
docs/api/DUCKDB_READER.md. Installed synthetic reports distinguish whole-read
costs, mapping/copy phases and native lifetime peaks; no hard process cap.
No provider downloads, credentials, scheduling, publication or live feed.


EQ051 clean installation additionally pins NumPy2.2.6 in the optional adapter
runtime. DuckDB1.5.6 create_function requires NumPy in the observed fresh environment;
the development environment had masked this dependency. Install DuckDB1.5.6 and
NumPy2.2.6 explicitly before --no-deps project archive installation. Core runtime
dependencies remain unchanged; NumPy's existing upstream notice/hash provenance
is recorded in [release integrity](../../docs/RELEASE_INTEGRITY.md). Both native installed forms must verify
this exact runtime. Null timestamps pass through the parser and fail closed, following
[DuckDB UDF null semantics](https://www.duckdb.org/docs/current/clients/python/function).


EQ052 adds caller-owned versioned calendar/history requests, actual daily slot
certificate validation and supplied reference intent with visible availability gaps.
Existing pure HistoryContext/WindowSpec/policy admission remains authoritative.
See repository docs/api/DUCKDB_GOVERNANCE.md; no calendar/reference fetching or
UTCdaily-to-RTH relabeling. Actual delivery gates remain on issue59.


Version0.1.0a5 returns acquisition1 receipts and bounded catalog/original stability observations with explicit VerificationPolicy. Supplied pins differ from observed hashes; optimized data remains unqueried. Raw real receipts contain private paths. See docs/api/DUCKDB_EVIDENCE.md for fields, identity upgrade, budgets and non-atomic/provider/PIT limits. Purecore remains unchanged.

Version0.1.0a6 adds installed synthetic SDK qualification with thirty actual DuckDB outcomes and sixteen independently expected numerical/unit/status/source-binding checks. See repository docs/api/DUCKDB_CONFORMANCE.md and examples/duckdb_conformance.py. Installed typing covers six adapter modules and that example. Source-only runs are developer evidence; private real-data and final delivery gates remain separate.

Version0.1.0a7 parses SQL UTCns with a connection-local native macro and exact HUGEINT arithmetic/guardedBIGINT, strict ASCII ISO/null/calendar/clock/fraction/bounds checks. Python mapping stays exact; undocumented Unicode clock/fraction digits reject consistently. Purecore/runtimepins unchanged; actual receipt stampa7. See docs/api/DUCKDB_REAL_QUALIFICATION.md; current installed/private/delivery gates remain.

EQ122 moves current implementation to equity-feature-io; existing distributions/imports and R4 behavior are preserved. Only adapter receipt/package version markers and repository metadata change. See [migration](../../docs/DUCKDB_MIGRATION.md) and [current API](../../docs/api/DUCKDB_READER.md). Historical a7 acquisition/receipt evidence is retained in canonical equity-features.
