# Current implementation ownership — EQ122

Current optional implementation is in this I/O repository, experimentala8; original R4 story/version statements below are historical accepted contract provenance. Only package/receipt version markers and repository ownership change in extraction. Source/math/schema/availability/sampling/precision/limits stay unchanged. [Migration](../DUCKDB_MIGRATION.md) records compatibility and actual delivery gates.

# Explicit DuckDB catalog resolution

EQ049 [issue56](https://github.com/atulsrivas1/equity-features/issues/56),
[pre-code plan](https://github.com/atulsrivas1/equity-features/blob/main/docs/stories/EQ-049_PLAN.md). Experimental optional distribution
`equity-feature-duckdb`0.1.0a1 / import `equity_feature_duckdb`; contracts0.0.4a4,
DuckDB1.5.6, CPython3.12. Source is reviewed and qualified in installed artifacts; [delivery](https://github.com/atulsrivas1/equity-features/blob/main/docs/stories/EQ-049_DELIVERY.md) records final receipt gates.
The pure contracts/features distributions remain unchanged and never import it.

```python
from pathlib import Path
from equity_feature_duckdb import CatalogConfig, SourceSelection, resolve_source

# Caller supplies an absolute local synthetic catalog, never an inferred drive.
config = CatalogConfig(Path("fictional.duckdb").resolve())
selection = SourceSelection("prepared", "frozen1", "FICTION", "ohlcv-1d",
                            ("2025-03-03",))
resolved = resolve_source(config, selection)
```

`CatalogConfig(path: Path, expected_sha256=None, max_sessions=366, max_files=4096,
max_hash_bytes=1073741824)` requires an absolute local path and positive exact
int64 bounds. `SourceSelection(layer,snapshot,dataset,source_schema,sessions,
expected_schema_sha256=None)` owns unique exact ISO partition dates; layer is
curated/prepared and schema trades/tbbo/ohlcv-1m/ohlcv-1d. Partition dates are not
a governed calendar. No latest-generation lookup or implicit overlap union.

`FilePin(original_path,original_sha256=None,optimized_sha256=None,receipt_id=None)`
binds a caller-owned receipt assertion by exact original path. Hashes must be
lowercase SHA256. Selected files are independently read to check asserted hashes;
path/size/provenance is never turned into an invented content hash. A receipt ID is
a retained assertion, not authentication of the external receipt or source truth.
Extra/duplicate pins fail. Missing hashes stay null. The schema hash is SHA256 of
the exact UTF8 catalog `column_signature`, not an independently inspected Parquet
schema. EQ050 qualifies the actual source schema and normalization.

`resolve_source(config,selection,*,pins=(),cancellation=None)` returns frozen
`ResolvedSource`: selection, actual catalog hash, one view route, ordered partition
records, missing dates and identity digest. Partition records retain declared row
counts, original/optimized paths/sizes/checked hashes, schema identity, receipt ID,
original/substituted dataset and unmodified admission text. `declared_empty` means
the catalog reports zero rows; canonical observed-empty requires EQ051's actual
row acquisition. No completeness, known-at, eligibility, source uniqueness, price
precision, calendar or PIT certification follows from metadata resolution.

The catalog exposes static `catalog.datasets` and `catalog.files` tables as
described in the synthetic tests. Exactly one dataset route must match all four
selection fields; each selected file must agree with its route. Dates are bound
SQL values, never identifier interpolation. Unsafe view identifiers, route/schema
conflicts, duplicate selected original/optimized paths and malformed/null metadata
fail. Multiple disjoint files per date are retained. Missing dates remain explicit.
Selection chooses the requested layer/generation exclusively even where another
layer overlaps. Files are ordered by date/original path for receipt determinism;
that order is not claimed as exchange-event order.

Resolution uses a private read-only connection (one thread, DuckDB memory setting
256MB), checks selected physical file presence/declared byte length, and hashes
asserted pins in chunks of at most1MiB. The cumulative byte budget includes both
catalog reads and any file hashes. Metadata requests stop at max_files+1; file/date
bounds reject oversized results. Cancellation is checked before/between catalog,
file and hash operations; synchronous DuckDB metadata execution itself has no
interrupt responsiveness promise. Hashing is bounded I/O, not a throughput claim.

Catalog before/after hashes reject observed changes. This does not lock external
files or certify an immutable multi-file transaction; files without a supplied pin
are checked only for presence/size. EQ053 owns acquisition stability semantics.
Caller-owned local catalogs/paths are trusted configuration. Read-only connection
mode is not an untrusted SQL/native-code sandbox. DuckDB's memory setting is not
a hard process-memory limit. No provider extension/network/job/publication is used.

Failures use existing safe `SourceErrorCode`: SCHEMA for malformed metadata,
ambiguity or stale pins; UNAVAILABLE for missing catalog/population/physical file;
LIMIT for configured date/file/hash budgets; CANCELLED for supplied cancellation;
TRANSPORT for local file inspection failures. DuckDB query/schema failures map to
SCHEMA with a fixed message. Errors suppress original exception text/private paths.
Unknown source admission is retained; neither successful reads nor hashes admit it.

Qualification uses actual fictional temporary DuckDB catalogs and independently
authored bytes. EQ049 checks metadata; EQ054 will run the public conformance kit
against actual canonical DuckDB delivery, and EQ055 will freeze and verify private
representative real-source numerical integration. R4 needs both; it remains open.

Primary documentation: [DuckDB Python read-only connections](https://duckdb.org/docs/lts/clients/python/dbapi)
and [configuration semantics](https://duckdb.org/docs/current/configuration/overview).
The tested version pin/actual installed checks, not an upstream claim alone,
establish this adapter's supported scope.
