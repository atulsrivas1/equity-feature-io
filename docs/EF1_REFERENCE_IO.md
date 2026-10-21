# EF1 supplied REFERENCE conversion — EQ168 / EQ212

This additive adapter surface implements source composition for the frozen
classification/action subset in canonical draft PR587, portable JSON SHA256
`5160d91fc966137a1728c6c26dde15d6772ea35811efc4ea9832b2f7460a28f0`.
It is source-authored and awaits independent review and exact-head local validation.
It does not close the original official/reference-close or full inventory gates.

`equity_feature_duckdb.ef1.ReferenceClassificationInputs` owns exactly three
nullable positions: `classification_facts`, `classification_history`,
`classification_projection`. `ReferenceActionInputs` owns exactly six:
`market`, `action_facts`, `action_history`, `action_projection`,
`source_representation`, `source_quantity_basis`. `.slots` retains missing None
positions; `.batches` is the present subsequence in this order. Pass `.slots` to
the pure producer. Existing anchor/clock/path present-only APIs are unchanged.

Every slot has an explicit provenance entry: `duckdb_backed_observed`, `synthetic`
or `unavailable`. The last requires None; the first two require an actual batch.
These are caller source declarations, not source authentication or invented
coverage. Mixed observed/synthetic roles retain their original declarations.
No database, provider, dates or authority are discovered by these helpers.

`make_reference_rows` accepts a concrete tuple of explicit canonical row mappings,
actual BatchMetadata and explicit instrument/session. It retains every supplied
column/value and rejects unknown fields or inconsistent row shapes. Null/blank
classification text retains original bytes and spaces under EF1-REF-A2. Null
unused optional fields remain supplied fields; populated forbidden payloads
reject. Actual null or late known-at and incomplete/empty populations are retained
for library assessment. No sorting, deduplication, filtering, inferred freshness,
latest snapshot selection or field dropping occurs.

`ReferenceCertificate` and `make_reference_proof` convert actual supplied proof
rows to the closed h1/a1/r1/q1 grammar, including reversible original target input
IDs, scope/kind where required, and certificate IDs. Canonical bounds and all
original rows validate. Proofs match actual target namespace/entity/source/revision
and cannot name themselves. Missing target delivery remains missing even if a
proof names it. History/projection declarations do not authenticate a publisher.
The aggregate REFERENCE population bound stays4096. Action market accepts TRADE,
BAR or DAILY with original metadata and fields; factor application and numerical
feature logic remain exclusively outside this adapter surface.

The public synthetic helpers return fresh R01/R02/R03 source fixtures and context
selections. R01 supports sector, industry and universe explicitly; R02 is present
complete-empty0/0, not missing. R03 retains input price100,size10,split1/2 and raw
source quantity. The gate returns admission strings, never transformed50/20 data.
These examples use namespace `fixture`, entity X/S, explicit nanosecond clocks and
original source IDs. They are synthetic, with no N-drive data or rights claim.

Prospective tests include the55 independent full frozen packets, full result
metadata/quality/witness comparison, every omitted role, all three classification
kinds, empty action population, retained null/late knowledge and complete
DuckDBSink publish/read/idempotence/reopen equality. The55 packet readbacks are
55 subcases, not55 separately counted unittest methods. The generic output sink,
result codec, schemas and versions are unchanged. Task-wire admission and installed
cross-repository composition still require coordinator qualification.

No project imports, syntax/type checks, tests, builds, installs, benchmarks or DB
operations were run under the protected EQ142 resource reservation. Actual source
checks and exact changed-file hashes are recorded in the author handoff. Hosted
CI is optional evidence; applicable local validation governs merge.

Independent source review correction: an actual empty proof batch previously
escaped publisher/revision comparison because it had no decoded target row. The
adapter now compares actual source/snapshot metadata for every present batch in
each facts/market relationship group, independently of row target IDs. Empty
proofs cannot bypass an actual target or conflict with another supplied proof even
when the target is missing. No target ID is manufactured. Original decoded-target
checks remain unchanged. Three new source-authored methods cover wrong publisher,
wrong revision and missing-target proof conflicts across classification/action
facts and market proof groups. Current count27methods=22inputs+5composition;
no runtime check was executed. Fresh independent recheck remains required.