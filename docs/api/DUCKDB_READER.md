# Current implementation ownership — EQ122

Current optional implementation is in this I/O repository, experimentala8; original R4 story/version statements below are historical accepted contract provenance. Only package/receipt version markers and repository ownership change in extraction. Source/math/schema/availability/sampling/precision/limits stay unchanged. [Migration](../DUCKDB_MIGRATION.md) records compatibility and actual delivery gates.

# Bounded historical DuckDB reads

EQ051 adds optional `equity-feature-duckdb`0.1.0a3. Corepair0.0.4a4/schema1 and
DuckDB1.5.6 remain unchanged. [Issue58](https://github.com/atulsrivas1/equity-features/issues/58)
owns delivery acceptance; R4 conformance and private numerical acceptance remain
EQ054/055. [Resolver](DUCKDB_RESOLVER.md) and [mapping](DUCKDB_MAPPING.md) policies
apply before reading.

## Configuration and requests

`ReadConfig(catalog_path, resolved, mapping, namespace, source_id, calendar_version,
sessions, partition_sessions, scope, coverage_assertion=None, max_files=4096,
max_batch_rows=1024, threads=1, memory_limit_mb=256)` requires an absolute existing
catalog Path, a resolved selection, explicit MappingPolicy and InputScope. Sessions
are supplied SessionSpecs in one namespace with unique IDs and nonoverlapping
bounds inside scope. Exact selected ISO partition dates map explicitly to session
IDs; the adapter does not derive exchange sessions from file dates. Calendar version
identifies the caller's supplied calendar; it does not validate calendar authority.

`DuckDBHistoricalAdapter(config).read(request, cancellation=None)` returns
`ReadResult(canonical, batches, metrics, mapping_report)`. It supports one mapped
historical raw kind: trades, trade-snapshot TBBO, minute bars or UTC daily bars.
Requests must agree with snapshot, units, namespace, identities and scope. Live
reads, adjusted inputs, auction acquisition, preopen quote seeds, continuous quote
reconstruction and reference acquisition are unsupported. Governed history and
reference construction belong to EQ052.

## Selection, ownership and identity

A private read-only connection reads explicit original local Parquet paths.
Catalog views, remote sources and path globs are never executed. Projection names
come from a controlled field list; paths, instrument IDs and predicate values are
bound. Exact VARCHAR UTCns parsing returns BIGINT without timestamp truncation.
Instrument/time selection intersects each supplied session. Events use
`lower <= event_ns < upper`; bars require `lower <= start_ns` and
`start_ns + duration <= upper`, with duration60s or24h. UTC daily remains distinct
from an exchange RTH day. Final canonical validation remains mandatory.

The reader preserves physical original-file row numbers. It orders selected rows
by exact time, resolved file index and original row number, preserving tied equal
payload occurrences. Global retained order keys are deterministic tie breakers,
not certified exchange sequence. Optimized-file physical positions cannot replace
original positions. Event identity binds the resolved selection, original path,
asserted hash when supplied and original row number; stability across different
resolver selections is not promised.

The eager population is bounded by the smaller request/mapping row limit and is
fully validated before any envelope is yielded. An n+1 query detects excess rows;
file and chunk limits also fail before exposure. Mapping runs once over the whole
population. Canonical and chunk envelopes own immutable columns; chunks retain
the same mapping version/source coverage and unique request/ordinal/slice input
IDs. Full canonical population and MappingReport remain available for calculation
composition and explicit rounding evidence. `iter_batches(request,cancellation)`
performs the same eager read, then checks cancellation between yields. Previously
yielded prefixes cannot be retracted.

## Coverage and failure semantics

Default source coverage is `Coverage(None, observed_rows, False)`. Optional
`CoverageAssertion(instruments,sessions,start_ns,end_ns,expected_rows,policy_id)`
is a caller assertion for one exact request population. Its identities, bounds
and actual selected row count must match to retain complete coverage. Subsets
cannot inherit completeness. This assertion does not certify provider truth,
market interval completeness or source availability timing.

Observed empty acquisition produces an empty canonical batch. A selected missing
partition produces one terminal missing envelope with unknown coverage and no
canonical population or mapping report; partial complete output is withheld.
Missing original files, malformed fields, stale catalog row counts, invalid
capabilities and exhausted bounds produce fixed safe SourceErrors. Raw backend
messages and source paths are suppressed. Catalog name/schema ambiguity is handled
by quoting the connection-reported database identifier and qualifying the catalog
tables; selection values remain bound.

File size, schema and declared row count are checked during acquisition. These
checks cannot detect every same-sized mutation; immutable catalog/file receipt
binding remains EQ053. Retained unknown/later known-at values remain unchanged;
reading history does not establish PIT eligibility. Cancellation is checked before
acquisition and between files, fetches, mapping/copy stages and yields. Synchronous
SQL/UDF work has no hard midquery responsiveness guarantee. Caller serializes use.

## Measurement and installation

ReadMetrics reports `sql_fetch_ns`, `mapping_ns` (sorting, source-column/occurrence
materialization and canonical conversion), `delivery_copy_ns`, delivered rows,
selected files, selected file byte lengths, canonical cells and chunk count.
Selected file lengths are not measured storage I/O. External whole-read timing
includes preflight overhead outside these phases.

`benchmarks/duckdb_read.py` requires actual installed packages and synthetic
fixtures with independent integer expected times, price coefficients, quantities
and occurrence counts. It reports separate setup/read samples, phase metrics,
deduplicated reachable canonical/envelope Python bytes and Windows/Linux native
process lifetime high-water bytes. Native peaks include imports/setup and are not
exclusive read allocation deltas. The DuckDB memory setting is not a hard process
cap. No zero-copy, throughput, cold-cache or full-corpus claim is made.

The optional builder runs installed wheel/sdist reader tests, strict typing and
the quick measurement/parity case, preserving core-file/metadata invariance.
BothOS artifacts include `read-<system>-<form>.json` alongside installed reports.
Use [installation instructions](https://github.com/atulsrivas1/equity-features/blob/main/docs/INSTALLING.md); source-tree tests alone do not
complete the actual artifact/publication gate.


EQ051 clean installation additionally pins NumPy2.2.6 in the optional adapter
runtime. DuckDB1.5.6 create_function requires NumPy in the observed fresh environment;
the development environment had masked this dependency. Install DuckDB1.5.6 and
NumPy2.2.6 explicitly before --no-deps project archive installation. Core runtime
dependencies remain unchanged; NumPy's existing upstream notice/hash provenance
is recorded in [release integrity](https://github.com/atulsrivas1/equity-features/blob/main/docs/RELEASE_INTEGRITY.md). Both native installed forms must verify
this exact runtime. Null timestamps pass through the parser and fail closed, following
[DuckDB UDF null semantics](https://www.duckdb.org/docs/current/clients/python/function).

Observed local installed costs and limits: [measurement record](https://github.com/atulsrivas1/equity-features/blob/main/docs/benchmarks/EQ-051_READ.md).


EQ053 a5 supersedes the earlier pending-stability boundary above with mandatory bounded catalog/original pre/post observations and optional supplied optimized pins. ReadConfig.verification controls cumulative budgets/strict original pins; ReadResult.receipt and ReadMetrics.verification_ns/verification_hash_bytes retain evidence/cost. Source prefix original-read2 and observed content occurrence tokens replace a3/a4 identities. [Evidence API](DUCKDB_EVIDENCE.md) defines observed versus pinned/non-atomic/provider/PIT/privacy limits.

EQ055 experimentala7 uses native strict ASCII UTCns SQL arithmetic, retaining Python mapping/parser parity and actual receipt adapter stamp. No row-callback SQL timestamp parsing, float epochs or TIMESTAMP_NS sentinel conversion. Integer UTCns/standard retained formats and purecore/math/runtimepins are unchanged; Unicode-digit clock/fraction input is rejected consistently. [Private qualification methodology](DUCKDB_REAL_QUALIFICATION.md) separates native/source checks from pending actual installed real-data acceptance and current delivery gates.
