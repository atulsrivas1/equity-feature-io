# EQ127 transactional DuckDB sink delivery

Canonical [story284](https://github.com/atulsrivas1/equity-features/issues/284),
[companion PR7](https://github.com/atulsrivas1/equity-feature-io/pull/7),
[core PR297](https://github.com/atulsrivas1/equity-features/pull/297).
The [published plan](EQ127_PLAN.md) preceded code at713d11d/corebb23b5b.
Current Project In progress; no released backend acceptance yet.

Independent package equity-feature-duckdb-sink0.1.0a0 adds only SDK.a2 and
DuckDB1.5.6. Pure mathematics/canonical/SDK/sourceadapter/Parquet/worker package
bytes remain unchanged. No private rerun is required or claimed.

Six closed tables are defined by schema.py: metadata singleton;
reservations keyed by K with current attempt/state/envelope; results keyed by
K/attempt/result ordinal with three BLOBs; cells keyed by K/attempt/result/
column/entity ordinal; evidence keyed by K/attempt/result/evidence ordinal;
completions keyed by K with attempt/envelope/receipt. Fixed columns/types,
primary keys and nullability are validated before write admission. Complete
canonical BLOB is authority; cell/evidence bundles encode ordered primitive
tuples (decimal as exact integer, binary structured data as hex). The three
row-BLOB references bind exact stored byte lengths/SHA; SQL typed rows are
independently compared. Mutable DB page hashes do not identify generations.

Stable lease precedes read-only brand preflight and engine creation. New output
is bootstrapped in an owned temporary database, closed and published under the
lease. Existing arbitrary sources/wrong schemas are rejected before RW access.
Control connection performs autocommit only, avoiding stale read snapshots;
separate data transaction stages full units then completion/state in one COMMIT.
All engine handles close before unlocking. Other live owners, including
readers, receive BUSY; simultaneous native cross-process sharing is excluded.
Sequential process handoff, rollback/restart and original receipt replay are
qualified only by the actual native process tests.

Local preliminary evidence:18 independent development methods pass (43.095s),
including all18 complete synthetic records/54 row references,21 actual SDK
conformance cases, literal int64/decimal38/signedzero/UTF8/bool/null/UTCns,
500/51200/102.6/missingovernight calculation parity, fresh control visibility,
zero/empty/new-generation immutability, source protection, corruption and
bounded prefetch, foreign/closed handles, partial rollback and lost response
after actual COMMIT. Strict typing6files passes. Eight process methods passed
(37.019s); added ninth independently proves rejected unmarked DB AND WAL byte
invariance after terminating its owned synthetic writer (0.722s). Renewed
complete process and fresh/native forms remain required.

Initial full18 smoke failed because SDK to_wire intentionally rejects bytes.
Storage bundle codec now converts fixed-position BLOB values to inert hex;
canonical SDK bytes are unchanged. Initial constructor surfaced FactoryError;
it now translates to typed redacted SinkError. These failures are superseded
development evidence, not backend acceptance. Test assembly briefly misplaced
the missing-result check; corrected before renewed18-method success.

Preliminary fresh Windows3.12.10/NTFS workloads64/2048 exact cells/result/status
parity: logical25378/793226 bytes; row-BLOB38609/1223137 bytes; DB3682304/4730880;
post-close WAL0/0; control5055/5066; lifetime peak RSS62685184/82874368.
Observed write2.278/77.002s is measured development evidence, not a speedup or
latency commitment. Renewed probe records queried fixed engine settings.
Engine128MiB is not hard RSS, and DB/WAL/namespace growth remains caller quota.

Next freeze implementation/source, complete separate final-head automated
review/findings, native current CI/committed repeat/fresh wheel+sdist/public
typing/core invariance and source/archive/report/channel hashes. Actual
successful-main publication/readback precedes Released and postread Done.
No power-loss/network/adversarial namespace/universal durability/private rights
or hosted/human reviewer certificate; no R5/provider/service/stable tag work.

EQ127 rework [6031028441](https://github.com/atulsrivas1/equity-features/issues/284#issuecomment-6031028441): separate exact-source reviews [IO6031030267](https://github.com/atulsrivas1/equity-feature-io/pull/7#issuecomment-6031030267)/[core6031030775](https://github.com/atulsrivas1/equity-features/pull/297#issuecomment-6031030775) independently reproduced same-owner replay after actual COMMIT/lostresponse returning BUSY, and malformed stored reservation returning INVALID_CONTENT rather than CORRUPTION. Corrections inspect independent committed completion before same-owner BUSY and normalize stored decode failures to CORRUPTION; existing18-method suite now exercises both regressions. Historical handoff/lesson UTF8 bytes are restored exactly from pre-code sources, retaining only new EQ127 entries; trim EOF/ignore outputs. Initial a799907 native push37572041776 bothforms/14archives/two serverZIP hashes/allfiles and localrepeat/bothforms pass but are superseded/excluded from corrected acceptance; preserved in ignored eq127-duckdb-sink-initial and eq127-a799907-dist-duckdb-sink. Canonical284 returned Code review -> In progress. Renewed exact-head review/current native/freshinstalled/source/main gates remain mandatory.

Corrected local18-method suite (41.586s) and strict6files pass after both P2 regressions; git diff against pre-code has no whitespace errors. Historical text equals pre-code after removing new entries. Renewed native/fresh installed/review/main gates remain pending. Public API guide: [DuckDB sink](api/DUCKDB_SINK.md).
