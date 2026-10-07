# Experimental Parquet generation API — EQ126

## BUG-005 reader correction — 0.1.0a1

Canonical [repair301](https://github.com/atulsrivas1/equity-features/issues/301), [plan](../BUG005_PLAN.md). Completion is observed before reservation binding: cooperating writers publish it last and never replace completed records. This prevents mixing an absent/old reservation with a newly committed attempt. When completion was absent, lookup may return the factual ABSENT/STAGING/ABORTED snapshot observed during its operation; repeat lookup discovers concurrent commitment. No unbounded reader retry or new lock is added. Stable completion without reservation, mismatched attempt/envelope and corrupted components still return CORRUPTION. Existing format/SDK/math/source/commit-uncertainty/writer ownership remain unchanged.

The corrected package is0.1.0a1. Native fresh wheel/sdist/current-main qualification and actual delivery evidence are required on issue301; earlier .a0 tests/receipts below retain their historical scope. New deterministic first-publication/ABORTED/STAGING/existence-interleaving and stable missing/attempt/envelope-corruption cases supplement existing physical/process checks. This document does not declare the repair accepted before those gates.

Canonical [EQ126 #283](https://github.com/atulsrivas1/equity-features/issues/283); see [pre-code plan](../EQ126_PLAN.md), linked companionPR6/corePR296 and current Project for release stage. Source qualification snapshots are recorded below and in [delivery evidence](../EQ126_DELIVERY.md); the linked canonical issue/Project is current release authority. New optional equity-feature-parquet0.1.0a0, PyArrow20.0.0, accepted I/OcontractsSDK.a2/canonical.a4. No mathematical definition/source semantics change; no automatic registration or worker command.

`ParquetSink(root: Path, destination_scope: str, *, limits: SinkRequirements, max_physical_bytes=67108864, max_control_bytes=33554432, caller_committed_at_ns=None)` implements the accepted ResultSink protocol. Root is a trusted caller-owned local directory. Constructor validates supported platform, scope, limits and audit timestamp without creating a namespace. Default logical maxima100results/1MiBunit/10MiBtotal/100000cumulative cells+evidence; smaller supported bounds only. The explicit audit timestamp is caller supplied or null. It is independent of canonical availability and original receipt remains unchanged on replay.

Use context management or explicit close: `with ParquetSink(root, scope) as sink:` then accepted prepare_publication/publish/read with limits-only preparation and, when needed, separate operational requirements. Visibility manifest_last, writer_mode serialized_writer, lookup/abort/read true. A single stable-inode OS writer lock serializes whole attempts across cooperating local processes. Live contention returns BUSY; foreign or closed write handles INVALID_SESSION. Abort releases active ownership and retains an ABORTED reservation; retry same content gets a new exclusive attempt. Different content/counts on a reserved key conflicts regardless of STAGING/ABORTED/COMMITTED. Complete replay verifies every component and returns byte-equivalent original receipt. Lookup is factual; corruption/unavailability never becomes ABSENT. Detected corruption withholds committed receipts/readback; recovery cannot mask it.

Explicit ParquetSinkFactory protocol1 supports scalar root/destination_scope, five logical maxima, physical/control maxima and nullable caller_committed_at_ns. Unknown/invalid fields, bool-as-int and URI/UNC root fail. Factory validates configuration with fixed redacted errors and does not consume CredentialProvider. Register an instance in per-run SinkRegistry explicitly; direct injection uses the same backend. No package discovery or credential serialization.

## Closed layout and complete readers

Only `<root>/.efio-parquet1/` belongs to this backend. writer.lock is stable and never replaced/unlinked. Per SHA key: reservation.json, complete.json, and unique32hex attempt directories. Each ordered complete result has rNNNNNN.result.json, rNNNNNN.cells.parquet, rNNNNNN.evidence.parquet. Receipt IDs are key/attempt/filename; every component has exact byte length/SHA256. Zero publication has no component references and its complete receipt remains persisted. One zero-row canonical result still has all3components/metadata; absent and observed-empty are distinct.

Reservation control fields exactly schema/attempt_id/state/envelope; state STAGING or ABORTED. Completion exactly schema/attempt_id/envelope/receipt. Envelope/receipt strings contain their canonical accepted encodings. Control JSON is ASCII/sorted/compact/closed/no duplicates/unknown fields. Completion is written last through flushed/fsynced same-directory temporary control replacement. All precompletion files are ignored by qualified readers. No directory-rename atomicity assumption. Components are immutable after completion; all required components/schemas/counts/hashes/full descriptors/content/key are validated before visibility and readback.

Result.json retains the exact complete canonical record. Cells are typed ordered analytics projections with ordinal/namespace/entity/feature/algorithm/type/unit/schema/null, int64/decimal128(38,0)/float64/bool/UTF8 scalar columns or canonical binary structured value and matched status/expected/observed/ordered reasons. Evidence is typed ordered ordinal/feature/entity/input/row/event/known-at/effective/use/reason/boundary. UTCns stays signed int64, known-at null stays null; no timestamp inference/rescaling. Nested reasons use explicit Arrow child name element. Both Parquet schemas have exact efio_storage/efio_table metadata and explicit empty tables. Readers verify projected values/order/type/null/quality/evidence against the complete canonical record; Parquet alone is insufficient to reconstruct all metadata/structured semantics.

## Bounds, retention and limits

Physical64MiB bound is per active/committed attempt; control32MiB is per record, separate from logical counts. Reject repeated metadata expansion before Arrow buffer construction and cap every physical stream write before exceeding the remaining attempt budget. Check persisted physical hashes/sizes/footer rows/schema before allocating tables; admit only UNCOMPRESSED PLAIN/RLE (no dictionaries), bounded footer uncompressed bytes/row groups/leaf counts and conservative repeated payload/fixed-width/offset allowance before Arrow read; read only bounded complete result tuples. No hard RSS/latency/global retained storage claim. Retained old partial attempts, tombstones/control temporaries and number of generations can grow; caller owns quotas/explicit cleanup. Backend never automatically deletes staging/input/committed data or evicts reservations. Declared reservation floor7days is policy while caller preserves the namespace, not an elapsed7day test. Receipt/read retention has no backend expiry.

Current implemented platform selection is CPython3.12 x64 native Windows/Linux; qualify actual local filesystem/runtime in installed reports. Reject obvious URI/UNC roots; caller must select a qualified local filesystem, including checking mapped mounts. POSIX flock/Windows msvcrt ownership are cooperative, with real owned-child process-exit recovery qualified in native installed Windows/NTFS and Linux/ext4 forms at source8892ff6. File flush/fsync and Linux directory fsync are used; Windows directory fsync is unavailable here. Network/object stores, adversarial namespace replacement/writers, machine power loss, kernel/filesystem failure and universal fsync durability are unqualified. Cancellation/abort cannot retract verified commitment; uncertain commit returns COMMIT_UNKNOWN/lookup. Close releases any owned active attempt even if an error prevents proving abort; leftover STAGING requires new exclusive restart. No scheduled cleanup/task claim/catalog policy.

## Current development evidence

17 independent local methods/strict5 files pass, including21 real Parquet logical cases and18 complete synthetic results, independent typed extrema/null/signedzero/UTCns, three-component corruption and changed projection with recomputed physical reference, real live instance locking/conflicts, partial/control/byte/metadata-expansion limits, factory/direct paths and public source->bar expected500/51200/102.6. Initial schema/fixture failures are preserved in handoff. These are development checks, not native process/installed/current-main release acceptance. Eight real process methods locally pass: five kill/restart storage boundaries, live contention, two same-content writers and two different-content writers with postcommit conflict retry. Two fresh Windows/NTFS processes measure64/2048cells with exact int64/result/status parity. Source8892ff6 actual repeat/both fresh forms/native downloaded14archives/fourserver qualification forms pass; final documentation-head/main acceptance remains required. Source correctness/private rights and backend qualification are separate; no new private execution.

## Resource measurement method and corrected review

[Interim automated review](https://github.com/atulsrivas1/equity-feature-io/pull/6#issuecomment-6030431572) reproduced expanded ZSTD and NONE/dictionary buffers before corruption rejection. The format/allocation admission above corrects that finding; two recomputed-reference regressions assert no ParquetFile.read call. Final-head review is still required. First concurrency fixture assumed a loser always sees CONFLICT; legitimate BUSY before durable reservation is now accepted, followed by a factual conflict retry after commitment. No backend change was needed for that fixture. First resource harness omitted the required explicit limits argument; failed run is excluded, corrected fresh measurements retained.

Fresh-process reports include full Python/OS/architecture/filesystem, package versions, script SHA, logical SHA/bytes, physical/control bytes, Arrow pool peak, lifetime RSS/import lifetime peak and begin/write/commit/read wall durations. [Microsoft PeakWorkingSetSize](https://learn.microsoft.com/windows/win32/api/psapi/ns-psapi-process_memory_counters) is bytes; [Python getrusage](https://docs.python.org/3.12/library/resource.html) exposes Linux ru_maxrss, converted from KiB to bytes here. Import baseline is itself an observed lifetime peak, not a subtractable resident baseline. Arrow peak excludes Python/OS buffers; lifetime RSS includes imports and fixtures. Single workload observations are neither a speedup nor stable latency nor a hard RSS cap. Filesystem type qualifies only the tested native temporary volume; no path/private payload is published.

## Public direct and factory composition example

Supply previously computed complete results; calculation/provider acquisition remains caller-owned. The root and operational generation/job/partition IDs are caller decisions. This synthetic example uses public interfaces only:

```python
from pathlib import Path
from equity_feature_contracts.results import FeatureResult
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk.publication import prepare_publication, publish
from equity_feature_parquet import ParquetSink

limits = SinkRequirements(max_results=100, max_chunk_bytes=1048576,
                         max_total_bytes=10485760, max_result_cells=100000,
                         max_evidence_rows=100000)

def store(results: tuple[FeatureResult, ...], root: Path) -> tuple[FeatureResult, ...]:
    envelope = prepare_publication(results, destination_scope="synthetic-results",
        generation_id="g1", job_id="j1", partition_id="p1", limits=limits)
    with ParquetSink(root, "synthetic-results", limits=limits) as sink:
        receipt = publish(sink, envelope, results)
        return sink.read(receipt)
```

For explicit factories, create `SinkRegistry[ParquetSink]()`, register `ParquetSinkFactory()` under a caller-owned ID, and call its public resolve method with scalar root/destination_scope config, credential provider and requirements. The factory does not read credentials; the registry performs accepted protocol/capability admission. Close the resulting sink or use its context manager. Direct/factory equivalence is executed by the independent roundtrip suite. Importing the module does not register factories or create storage.

Compatibility is storage efio-parquet1 with logical protocol1/efio-json1/efio-key1/efio-content1, accepted canonical0.0.4a4/SDK0.1.0a2. A different storage/logical version is unsupported, without automatic upgrade/migration. Source adapter0.1.0a8 is independent; worker composition/version alignment belongs to EQ129. Published experimental artifacts, source/build hashes and actual native reports determine accepted combinations; no registry/stable tag is implied.

## Qualified source measurements

Source8892ff6 native push [Parquet37568388355](https://github.com/atulsrivas1/equity-feature-io/actions/runs/37568388355), [foundation37568388169](https://github.com/atulsrivas1/equity-feature-io/actions/runs/37568388169) and linked core632cc24 qualify actual committed source, not GitHub pull-request merge checkout. New14 actual archives (two sink/five dependency wheels per OS) and source/test/builder hashes are verified. Both fresh forms per OS have17physical cases,8real process cases,64/2048cell measured workloads, strict public/external typing/two invalid calls rejected and canonical before/after equality, with NumPy/Pandas absent. Independent public bar goldens retain500/51200/102.6/missingovernight.

| Source observation | 64cells | 2048cells |
| --- | ---: | ---: |
| Canonical bytes | 25378 | 793226 |
| Three physical components bytes | 40966 | 1081970 |
| Arrow allocator peak bytes | 27264 | 760896 |
| Linux3.12.14/ext4 lifetime RSS across wheel/sdist bytes | 81285120–85377024 | 108027904–108355584 |
| Windows3.12.10/NTFS lifetime RSS across wheel/sdist bytes | 108675072–108716032 | 121356288–121901056 |

These are single fresh-process observations from retained version-bound reports, without a memory/latency promise or subtraction of import peak. Reports retain control bytes, audit runtime, workload SHA and phase wall durations. Documentation-only packaged README changes require current repeat/fresh/native artifacts before final acceptance; source8892ff6 is preserved as earlier successful qualification. Release readiness, successful-main artifact/readback and actual Released/Done remain separate gates.
