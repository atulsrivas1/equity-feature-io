# Experimental transactional DuckDB result sink

`equity-feature-duckdb-sink==0.1.0a0` exposes `DuckDBSink` and
`DuckDBSinkFactory` from `equity_feature_duckdb_sink`; dependencies are
SDK0.1.0a2 and DuckDB1.5.6. [Logical publication v1](../contracts/IO_V1.md)
and [delivery evidence](../EQ127_DELIVERY.md) distinguish the contract from
actual native acceptance. No source or calculation semantics change.

Constructor: `DuckDBSink(output_path: Path, destination_scope: str, *, limits:
SinkRequirements = DEFAULT_LIMITS, max_projection_bytes: int = 67108864,
max_control_bytes: int = 33554432, caller_committed_at_ns: int | None = None)`.
It creates no namespace. Direct `begin/write/commit/abort/lookup/read` satisfy
the public ResultSink protocol; `close` and context exit release resources.
`publish` validates the complete caller-supplied result tuple before beginning.
[Package example](../../packages/duckdb-sink/README.md) shows direct injection.
Explicit SinkRegistry registration uses an application-chosen ID and
DuckDBSinkFactory; config keys are `output_path`, `destination_scope`, the two
byte bounds, optional commit time and the five logical max_* fields. Unknown
keys, bool-as-int and unsupported versions/capabilities fail with redacted
typed errors; credentials are not consumed. No import-time registration.

## Closed storage and exact values

Storage version `efio-duckdb1`, independent of logical1:

| Table | Key and stored data |
| --- | --- |
| efio_metadata | BIGINT id1, exact storage_version VARCHAR singleton |
| efio_reservations | VARCHAR pub_key PK, attempt VARCHAR, state VARCHAR, full envelope BLOB |
| efio_results | pub_key/attempt/result_ordinal PK; canonical record/cells_bundle/evidence_bundle BLOB |
| efio_cells | pub_key/attempt/result_ordinal/column_ordinal/entity_ordinal PK; typed values/headers/quality |
| efio_evidence | pub_key/attempt/result_ordinal/evidence_ordinal PK; full typed evidence projection |
| efio_completions | pub_key PK; attempt, full envelope BLOB, completion receipt BLOB |

Column order/types/nullability/primary keys, exact table set and metadata are
validated. Ordinals/time/counts are BIGINT. Cells carry namespace, instrument/
session/feature IDs, algorithm/schema/dtype/unit, is_null, nullable int64,
DECIMAL(38,0), DOUBLE, BOOLEAN, UTF8 VARCHAR and structured canonical BLOB,
quality status/expected/observed and ordered VARCHAR[] reasons. Evidence carries
feature/entity/input/row IDs, event/known-at/effective start/end UTCns,
use/exclusion reason/boundary; unknown known-at remains NULL. No datetime,
Pandas, float or string conversion substitutes for exact integer/decimal units.

Each result's three ArtifactReferences are opaque destination-relative
`K/attempt/rNNNNNN.result`, `.cells`, `.evidence` row identities, with exact
stored BLOB SHA and length. Projection bundles are ordered primitive tuples,
decimal encoded as exact integer and structured BLOB as inert hex, never
executable objects. Full canonical record is authoritative; readers compare
both bundles and independently fetched typed rows. Zero publication has no
artifacts; an observed-empty result has three empty/record bundles and distinct
logical content. A database page/file digest is not a generation reference:
later commits/checkpoints change pages while older row bytes/receipts survive.

## Visibility, lifetime and recovery

Acquire stable-inode OS lease before opening any engine handle. Existing DB
must pass read_only branding/schema preflight; an arbitrary source DB cannot
become an implicit sink. New DB is built in a caller-owned unique temporary
file, closed, then published under exclusive lease. Retained bootstrap/namespace
files are caller cleanup/quota; no source/accepted generation is deleted.

Control autocommits STAGING/content reservation, then an independent data
connection begins the transaction. Whole-unit writes stage BLOBs and typed rows;
completion plus reservationCOMMITTED enter the same data COMMIT. Autocommit
control queries prove factual commitment from fresh snapshots. Prior to COMMIT,
own lookup is STAGING/no receipt; same-owner retry after actual COMMIT/lost
response verifies and returns original receipt. Raw uncertainty returns
COMMIT_UNKNOWN; factual lookup/replay resolves it without guessing from staged
rows. Corrupt retained control/result/projection bytes withhold receipts and
remain CORRUPTION through recovery.

Abort rolls back staged data, persists ABORTED/content reservation and closes
all handles before unlocking. Same content gets a new exclusive attempt;
different content under K conflicts. A committed generation cannot be retracted
by cancellation/abort. Foreign, closed or out-of-order sessions fail. No resume
offset, worker task claim or scheduling is provided.

| Topology | Declared behavior |
| --- | --- |
| One owner, separate same-process control/data connections | Serialized methods, independent committed view |
| Another cooperating live owner or reader, any key | BUSY before native connection access |
| Sequential exclusive handoff after close/process exit | Recovery/new attempt or original committed receipt, on qualified native OS/filesystem |
| Simultaneous native cross-process DB sharing or raw external connections ignoring lease | Unqualified |

Native CPython3.12 x64 Windows/Linux with actual filesystem/runtime recorded
per report. URI/UNC/symlink/special memory destinations rejected. Local mount
selection is caller responsibility; network/object stores, hostile replacement,
power-loss and kernel/storage failures are unqualified. Policy retains
reservations at least7days while caller preserves DB; no automatic receipt
expiry or elapsed7day certification.

## Admission and measured limits

Logical defaults100results/1MiBunit/10MiBtotal/100000cells/evidence; only smaller
validated settings. Conservative repeated-payload admission precedes projection
allocation, and actual three-BLOB total stays within64MiB per attempt. Control
record bound32MiB. SQL readers check counts, OCTET_LENGTH, repeated variable
payload and array lengths before complete BLOB/row fetch, then exact parity.
Conservative admission may reject a workload before its serialized output
would reach the configured cap; no minimum workload capacity is promised.

Engine settings128MiB memory/1thread/0Bspill and external access plus extension
auto-install/load disabled. Admission/write OutOfMemory returns redacted RESOURCE_LIMIT;
uncertain commit uses factual recovery. Engine memory is not a hard process RSS
limit; DB/WAL/total namespace growth needs caller quota/retention/cleanup. Fresh
64/2048-cell probes record exact parity/DB/WAL/control/BLOB/RSS/wall durations,
without speedup/latency/resource extrapolation. Current reviewed/native/fresh
artifact/main acceptance and limitations remain linked in delivery evidence.
