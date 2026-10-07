# equity-feature-duckdb-sink

Experimental transactional local result sink, Python 3.12 / SDK 0.1.0a2 /
DuckDB 1.5.6. [EQ127](https://github.com/atulsrivas1/equity-features/issues/284)
tracks current acceptance and [delivery evidence](https://github.com/atulsrivas1/equity-feature-io/blob/main/docs/EQ127_DELIVERY.md).

```python
from pathlib import Path
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_duckdb_sink.sink import DEFAULT_LIMITS
from equity_feature_io_sdk.publication import prepare_publication, publish

# results is a caller-supplied tuple of complete canonical FeatureResult records.
envelope = prepare_publication(results, destination_scope="daily-output",
    generation_id="g1", job_id="job1", partition_id="p1", limits=DEFAULT_LIMITS)
with DuckDBSink(Path("output/results.duckdb"), "daily-output") as sink:
    receipt = publish(sink, envelope, results)
    recovered = sink.read(receipt)
```

Constructor validates without creating a namespace. Existing databases undergo
read-only branded schema validation before any write connection opens. Select a
new output database, never a source store. The factory accepts explicit
`output_path` and `destination_scope` plus smaller bounds and optional caller
commit time; it consumes no credentials and performs no automatic discovery.

Storage `efio-duckdb1` uses six closed tables. Each complete result retains its
canonical record BLOB and two deterministic typed projection bundles, with
immutable byte SHA/length references. SQL cells preserve signed int64,
decimal38, float64 including signed zero, booleans, UTF8, structured canonical
bytes, null/status/count/reasons/unit metadata. Evidence preserves UTC
nanoseconds and nullable known-at. Readers verify BLOB references, canonical
content and exact typed rows. Whole mutable database pages are not generation
artifacts; later generations preserve older row BLOBs and original receipts.

A stable cooperative OS lease serializes each full attempt. All engine handles
close before lease release. Other live owners/readers receive BUSY. Supported
native process use is exclusive sequential handoff on actually qualified local
Windows/Linux filesystems, with independent same-process committed-view
connections. Simultaneous native multi-process database sharing, external
connections ignoring the lease, network stores and adversarial replacement are
unqualified. Explicit close/context exit releases abandoned attempts.

STAGING reservation commits separately before the data transaction. Result
BLOBs/SQL rows/completion/reservation COMMITTED become visible in one SQL COMMIT.
The independent autocommit control view verifies actual commitment. Abort rolls
back staged rows and retains ABORTED/content reservation. Same content retries
with a new exclusive attempt or replays the original committed receipt;
different content conflicts. Uncertain COMMIT requires factual lookup;
corruption withholds receipts. No resumable offset or worker scheduling.

Default admission: 100 results, 1 MiB complete unit, 10 MiB total logical bytes,
100000 cumulative cells/evidence rows, 64 MiB serialized projection budget per
attempt, 32 MiB control record. Repeated payload is admitted before allocation;
SQL readers bound counts/BLOB/variable payload before fetching. DuckDB uses
128 MiB engine memory limit, one thread, zero spill and disabled external
access/extension auto-install/load. Engine limits are not hard process RSS or
total database-growth caps. Namespace quota, cleanup and retained bootstrap
files belong to the caller. Reservations have a seven-day retention policy
while the caller preserves the database; receipts have no automatic expiry.
Process termination recovery does not certify power-loss or storage failures.
