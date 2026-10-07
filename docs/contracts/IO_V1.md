# Experimental I/O contract v1

Normative design for [EQ123](https://github.com/atulsrivas1/equity-features/issues/280), E19 / R4.1. This freezes interfaces before EQ124 factories and EQ125 runtime types, codec and conformance. No sink implementation or storage guarantee is delivered by this specification. The installed io-contracts/SDK0.1.0a0 foundations and DuckDB0.1.0a8 remain unchanged. [Architecture](https://github.com/atulsrivas1/equity-features/blob/main/docs/IO_WORKER_ARCHITECTURE.md) defines ownership; [vectors](IO_V1_VECTORS.md) provide independently expected cases.

## Compatibility and source ownership

I/O protocol `1`, codec `efio-json1`, identity `efio-key1` and logical digest `efio-content1` are exact strings. Canonical input/result schema is `1`, math policy `v1`, supported canonical distribution equity-feature-contracts0.0.4a4. These independent versions are not release milestone names. Unknown versions fail before acquisition, reservation or writes. Later versions need an explicit compatibility decision and new fixtures; numeric similarity never authorizes decoding an unknown schema.

The canonical acquisition interfaces remain equity_feature_contracts: AdapterCapabilities, AcquisitionRequest, AdapterBatch, historical/live protocols, SourceErrorCode and canonical validation. Companion Source is a composition-facing name for those interfaces, not a second batch schema. Synchronous historical acquisition and optional async live acquisition stay separate; no live implementation is implied. Source declared capabilities must satisfy the requested kinds/schema/units/basis/sampling/mode/bounds before acquisition. Credentials remain separately supplied caller objects, absent from requests/results/logs. Existing canonical errors retain their meanings and identities. No source is certified by I/O protocol admission.

I/O contracts depends only on canonical contracts and Python standard library; I/O SDK depends inward on I/O contracts. Optional backends have their own dependencies. Workers/calculations never become I/O-contracts dependencies. Core receives facts and produces canonical FeatureResult objects without storage access. The sink must reuse those objects; it cannot copy their schemas, rescale prices, fill nulls, infer availability or recompute mathematics. Factories and per-run source/sink namespaces belong to EQ124.

## Result completeness and bounded units

One write unit is one complete canonical FeatureResult, validated by its original canonical constructors. It contains all values, quality, ResultMetadata and evidence; every nested structured cell and input binding is included. A zero-row result remains a complete result with metadata and empty sequences. Missing input is a canonical unavailable value/quality condition, not an empty write, omitted component or zero value. Partial structured outputs permitted by canonical validators remain permitted with their original quality. Unknown known_at remains null.

The caller enumerates results in a fixed order starting at ordinal zero. Each FeatureResult is atomic as a write unit; codec v1 does not split one result's values/quality/evidence across calls. Array order is retained, including feature/entity/evidence/structured-row/reason order. Reordering changes logical content. Storage may use several tables/files but must reconstruct that order. Chunk placement/compression/filesystem names do not affect logical digest. A result exceeding negotiated limits fails RESOURCE_LIMIT; future row-fragment streaming needs a separate protocol. This restriction bounds each write but does not claim memory proportional to a single row or certify backend resource behavior.

Envelope limits are positive exact int64 max_results, max_chunk_bytes and max_total_bytes; max_result_cells and max_evidence_rows are nonnegative exact int64. Result cells counts sum len(column.entities); evidence counts sum len(result.evidence). Nested structured rows remain bounded by canonical encoded chunk/total byte limits even where they do not add result cells. Bytes refer to the exact canonical encoded result bytes below, excluding frame headers. All cumulative arithmetic is checked before writes. Caller and sink enforce the smaller of requested limits and declared backend limits. No lazy executable objects or arbitrary generators are accepted as result content.

## Safe canonical encoding

C(x) is ASCII JSON bytes, with keys sorted by Unicode code point, no insignificant whitespace, no BOM/trailing newline, ensure_ascii escaping and no NaN/Infinity. Strings retain exact Unicode code points without normalization; lone surrogates are rejected. JSON quotes and backslashes use backslash escapes; backspace/formfeed/newline/return/tab use `\b`, `\f`, `\n`, `\r`, `\t`, other control characters use lowercase `\u00xx`. Non-ASCII uses lowercase four-hex-digit Unicode escapes, supplementary code points use their surrogate pair. Printable ASCII is literal except quote/backslash; slash is not escaped. This is the spelling of Python3.12 json.dumps(sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False), applied to the closed wire tree. Object keys cannot repeat. Unknown/extra/missing fields or tags are rejected, as are noncanonical scalar spelling and duplicate JSON keys. No pickle, eval, uploaded code, arbitrary import or dynamic class lookup is allowed.

| Canonical value | Wire form |
| --- | --- |
| None | `null` |
| exact bool | `true` or `false` |
| exact str | JSON string |
| exact int | `{"int":"-9223372036854775808"}`; canonical decimal, zero `0`, no plus/leading zeros/negative zero |
| exact finite float64 | `{"float64":"-0x0.0p+0"}`; exactly Python binary64 float.hex spelling, including signed zero |
| enum | `{"enum":"results.Status","value":"available"}`; closed registry name and exact member value |
| tuple/list | JSON array of encoded elements; decoded canonical tuple |
| allowed canonical dataclass | `{"fields":{...all declared fields...},"record":"results.FeatureResult"}` |

Enum recognition precedes strings; bool precedes int. A dataclass's fields are exactly the canonical0.0.4a4 declared dataclass fields, including defaults, recursively encoded. There is no wire-derived executable name resolution. Encoder/decoder has an explicit static registry mapping the following names to the already imported canonical class objects; these names are wire labels, not import paths:

- results records: EntityKey, BreadthCounts, BreadthFraction, IntervalOHLCVRow, IntervalVolumeShareRow, IntervalOHLCV, IntervalVolumeShares, TopKTradeRow, TopKTrades, QuoteStateCounts, QuoteObservation, SampledSpread, QuoteDurations, TimeWeightedSpread, FeatureColumn, QualityRow, InputBinding, ResultMetadata, EvidenceRow, FeatureResult.
- inputs records: BatchMetadata, SourceBinding, Coverage, PriceUnit, AdjustmentSpec, InputScope, IntervalCoverage.
- specs records: AvailabilitySpec and IntervalSpec.
- enums: results.Status, results.Reason, results.ValueType and inputs.DataKind.

The codec must reconstruct each object through its canonical constructor from its exact field set, then validate the complete FeatureResult. Decimal128/int64 bounds, units, cutoff rules, nested invariants, null validity and source/mapping identities remain canonical responsibilities. Fractions returned by computed properties are not additional fields; numerator/count records retain their exact integers. Inputs themselves are never encoded as output substitutes. SHA identities already present in metadata are preserved, including the existing ResultMetadata.identity_digest algorithm; this codec does not replace it.

The closed registry contains precisely the 20 results records, seven inputs records, two specs records and four enum names listed above, as defined in canonical coremain45b3a6b1aefaf50aad9f188018b904ad82c2121a. BatchMetadata contains no enum fields itself; DataKind is required by InputBinding. Classes such as CanonicalBatch, SessionSpec, FeatureSpec, InputSchema, Field and DType are outside this output closure. Unknown record names fail even if installed in the canonical package. Adding a canonical field/class requires a new admitted codec version rather than automatic widening.

## Logical content and publication identity

Let B_i=C(result_i), in caller ordinal order. Content SHA256 is lowercase hex of SHA256 over ASCII `efio-content1` followed by one NUL byte, then for each result: its byte length as unsigned 8-byte big-endian followed by B_i. Empty publication hashes only the domain prefix; one empty FeatureResult is a different content identity. This incremental framing distinguishes concatenations and is independent of write-call grouping and physical file bytes. Digest is exact; numerical tolerance is for qualification, not content equality. Any value, status, unit, evidence, input identity, order, unknown availability or algorithm/config change changes its encoded content.

Envelope fields are exactly protocol_version, codec_version, identity_version, digest_version, canonical_package_version, canonical_schema_version, math_policy_version, destination_scope, generation_id, job_id, partition_id, result_descriptors, expected_content_sha256, result_count, cell_count, evidence_count, content_bytes, max_results, max_chunk_bytes, max_total_bytes, max_result_cells, max_evidence_rows, supersedes_key and caller_created_at_ns. Optional fields are present with null rather than omitted. Counts are nonnegative exact int64; result_count equals descriptor length. A canonical package version names the version string0.0.4a4, never a module path. Labels are nonempty strings without embedded control/surrogate characters. UTCns is exact signed int64. SHA256 fields are 64 lowercase hex characters. No credential/private access location is required: destination_scope is a caller-visible logical destination identity, not a credentialed URI.

Each result descriptor is a plain object with exactly metadata (encoded canonical ResultMetadata) and features (ordered array of plain header objects with exactly feature_id, algorithm_version, dtype, unit, schema_version). Headers preserve canonical enum encoding for dtype and exact strings for other fields. Descriptor metadata binds source snapshot/mapping/input versions, cutoff/availability/config/backend identities through its canonical fields. On write, the actual descriptor must exactly equal the envelope descriptor. No new canonical metadata schema is introduced.

The idempotency key is SHA256 of ASCII `efio-key1` plus NUL plus C(K), where K is a plain object with exactly protocol_version, codec_version, identity_version, digest_version, canonical_package_version, canonical_schema_version, math_policy_version, destination_scope, generation_id, job_id, partition_id, result_descriptors and supersedes_key (including null), using their envelope values. Counts, content SHA, bounds and operational caller_created_at_ns are outside K: content changes under the same intended generation must conflict rather than silently get a new key. Canonical strings and tagged dataclass/integers/enums follow the same encoding rules. Both sides recompute the key. Any destination/config/source/version identity change uses a different key. A correction also uses a new generation_id and explicit supersedes_key; sinks retain earlier accepted receipts and never delete/retract them. Catalog selection/supersession policy belongs to workers.

Envelope cannot claim unsupported or false metadata compatibility. Every descriptor's session/namespace must be internally canonical; cross-result duplicate (namespace, entity, feature_id) keys fail INVALID_CONTENT. Algorithm/config identity is declared metadata, not a new accuracy certificate. Limits/counts must agree with delivered content. A digest mismatch or changed declared content on a reserved key is a conflict; corrupted persisted content is CORRUPTION. Changes to operational timestamps or limits alone do not change the intended generation/content, but admission and count checks still apply before replay.

## Planned sink API

Names/signatures below are the EQ125 implementation target, not installed imports at EQ123. Typed immutable envelope/receipt/capability/error objects will carry the fields defined here. A session handle is opaque, scoped to one sink instance/attempt and cannot be decoded from untrusted executable data.

```text
capabilities() -> SinkCapabilities
begin(envelope) -> WriteSession | CompletionReceipt
write(session, ordinal, FeatureResult) -> None
commit(session) -> CompletionReceipt
abort(session) -> AbortOutcome
lookup(idempotency_key) -> PublicationStatus
read(CompletionReceipt) -> bounded canonical FeatureResult sequence
```

Capabilities lists exact accepted versions, supported visibility/writer/lookup/abort/read modes and bounds. Before begin, requested guarantees are checked; unsupported requirements fail before reservation. Writes require contiguous ordinals, matching descriptors and limits; duplicate/out-of-order writes fail INVALID_CONTENT. Retry starts a new attempt via begin, never guesses how many writes survived. Session handles from another sink/attempt fail INVALID_SESSION. Empty publication commits with zero results and complete empty count/descriptor bindings.

CompletionReceipt includes protocol/codec/key/digest versions, recomputed key, complete identity K, content SHA, verified counts, canonical versions and ordered artifact references. Each reference is an opaque destination-relative identifier, storage byte SHA256 and byte length; references cannot contain credentials. Optional caller commit time is audit metadata, not inferred historical known_at. Receipt may be returned only after the declared visibility condition holds. It is immutable across replay/lookup. Readers verify the receipt identity/counts/content and all referenced storage hashes, reject missing/extra required components and corruption, and return full canonical results. Lookup/read retention capabilities must state their supported scope; failure or expired support cannot masquerade as an absent publication.

The planned typed objects have these exact fields; tuples are immutable, integers exact and bounds checked. Wire objects use these field names, no implicit defaults/omitted optional fields. An envelope is not part of C(FeatureResult), so operational metadata does not enter content SHA.

| Type | Fields |
| --- | --- |
| PublicationEnvelope | the exact envelope field list above |
| ResultDescriptor | metadata: canonical ResultMetadata; features: tuple of FeatureHeader |
| FeatureHeader | feature_id; algorithm_version; dtype: canonical ValueType; unit; schema_version |
| CompletionReceipt | identity: K; idempotency_key; content_sha256; result_count; cell_count; evidence_count; content_bytes; artifacts: tuple of ArtifactReference; caller_committed_at_ns: int64 or null |
| ArtifactReference | artifact_id: opaque label; byte_sha256: SHA256; byte_length: nonnegative int64 |
| PublicationStatus | state: ABSENT/STAGING/ABORTED/COMMITTED/UNKNOWN; receipt: CompletionReceipt or null |
| AbortOutcome | state: ABORTED/COMMITTED/UNKNOWN; receipt: CompletionReceipt or null |
| SinkCapabilities | protocol_versions; codec_versions; identity_versions; digest_versions; canonical_package_versions; canonical_schema_versions; math_policy_versions; visibility; writer_mode; supports_lookup; supports_abort; supports_read; reservation_retention_ns; max_results; max_chunk_bytes; max_total_bytes; max_result_cells; max_evidence_rows |

Capability version fields are nonempty tuples of unique strings; booleans exact. visibility is `manifest_last` or `transactional`; writer_mode is `single_writer` or `serialized_writer` or `conflict_safe_multi_writer`. No mode is assumed from a backend name. reservation_retention_ns is positive int64, beginning at first reservation; backend documentation must specify actual supported persistence/process scope and receipt/read retention separately. The v1 sink contract requires all three supports booleans true; a write-only extension is incompatible with this conformance target. Limits have envelope meanings. Receipt/state coherence is strict: COMMITTED has a receipt, every other state has null. Artifact IDs are unique; a receipt may reference no physical artifacts only for a backend whose complete empty publication is fully represented by its persisted receipt, qualified separately. All required result components must be bound regardless of artifact layout. Any successful replay returns the byte-equivalent original receipt including artifact references and first caller commit timestamp.

SinkError has code from the table below, redacted message, idempotency_key (SHA256 or null) and attempt_id (opaque label or null). WriteSession remains a locally trusted opaque interface handle; no portable serialized handle is promised. EQ124 translates configuration requirements into exact capability admission; it does not silently enable a required unsupported mode.

## Lifecycle and uncertain outcomes

Within a declared destination and retention scope, a key's first admitted envelope reserves its content SHA and counts. Different content/counts under that key conflicts in staging, committed or aborted state; tombstones preserve this reservation during supported retention. Same content replay when committed returns the original receipt without rewriting storage. Staging retry may fail BUSY or recover/restart only under the backend's explicitly qualified exclusive ownership rules. Aborted same-content retry may begin a new exclusive attempt. Lookup distinguishes ABSENT, STAGING, ABORTED, COMMITTED and UNKNOWN. COMMITTED requires a verified receipt; all other states have no completion receipt.

Only commit can make staging visible to qualified readers. An interrupted write has no completion receipt and staged bytes are ignored. Commit validates every descriptor/count/hash/component before visibility. A previsibility failure may be retryable; failure after possible visibility is COMMIT_UNKNOWN, requiring lookup rather than assuming rollback. Lookup UNKNOWN/transport failure also cannot certify absence. Once lookup confirms COMMITTED, return the original receipt; confirmed STAGING/ABORTED recovery follows declared capabilities. Execution across workers/storage is not exactly once.

Abort outcome is ABORTED, COMMITTED or UNKNOWN: ABORTED certifies no committed generation and successful invalidation of that attempt, COMMITTED preserves/returns the accepted receipt, UNKNOWN requires lookup. Cancellation before commit follows abort; cancellation after committed visibility cannot retract/delete the generation. Retrying abort is idempotent. Abort/cleanup only affects the sink's own staging namespace, never input stores. Worker task claims/checkpoints/catalog pointers and abandoned-stage cleanup scheduling remain separate later scope.

## Capability matrix and errors

| Property | v1 contract requirement | Backend qualification required |
| --- | --- | --- |
| complete logical readback | values/quality/metadata/evidence and exact ordering | physical schema/codec preservation and bounded reader |
| atomic visibility | receipts denote committed generations; staging ignored | manifest-last qualified filesystem or database transaction |
| idempotency | reserved key/content distinction and original receipt replay | durable key/receipt/tombstone storage, retention and concurrent conflict |
| uncertain commit | typed unknown outcome and lookup | lookup behavior after process/connection failure |
| cancellation/abort | cannot retract commitment | actual cleanup/session invalidation and commit races |
| writer ownership | explicit declared topology | single writer/serialized connection or qualified conflict protocol |
| resource bounds | enforce negotiated logical limits | actual memory/copy/I/O measurements and storage limits |

EQ126 Parquet and EQ127 DuckDB must qualify their platform/filesystem/process matrices. A manifest-last directory is not universally atomic; a DuckDB source adapter stays read-only and output sink uses an explicitly separate destination and serialized writer. These are design targets, not delivered capabilities. No backend may silently claim unsupported durability, multi-process shared writes or universal exactly-once behavior.

| Sink error code | Meaning / caller action |
| --- | --- |
| INCOMPATIBLE_VERSION | unsupported exact protocol/codec/canonical version; fix selection before I/O |
| INVALID_CONFIG | invalid envelope/destination/bounds; fix caller input |
| UNSUPPORTED_CAPABILITY | requested guarantee not supported; choose an admitted component |
| INVALID_CONTENT | noncanonical encoding/schema/order/duplicate or descriptor/count mismatch; no completion |
| INVALID_SESSION | wrong/closed attempt handle; never guess resumable offset |
| RESOURCE_LIMIT | negotiated bound exceeded; change request/partition |
| CONFLICT | reserved key differs in content/counts; use an explicit new generation for correction |
| BUSY | staging owner/writer contention; retry only under declared ownership policy |
| RETRYABLE_FAILURE | definitively precommit transient failure; retry via begin |
| COMMIT_UNKNOWN | visibility may have occurred; lookup and do not blindly overwrite |
| CANCELLED | request cancelled before confirmed commitment; abort/lookup as needed |
| CORRUPTION | receipt/artifact/decoded content mismatch; withhold readback and investigate |
| UNAVAILABLE | lookup/read cannot establish state or retention unsupported/expired; never infer absent |

Errors include stable code, opaque key/attempt when safe and redacted message, without serialized credentials/exceptions/config payloads. Canonical ContractError and source errors remain separate and may be translated into INVALID_CONTENT at the sink boundary without changing their definitions. A retryable classification is a supported factual precommit outcome, not a default for every exception. Raw backend failure around commit defaults to COMMIT_UNKNOWN unless noncommit is established.

## Mathematical and release impact

No formula, unit, algorithm/config definition, C/K/E timing, initialization, coverage or accepted R4 source limit changes. Serialization preserves supplied canonical facts and does not establish financial truth, source rights or provider admission. Core0.0.4a4 and the 39/23/22 calculation mode inventory remain unchanged. EQ123 publishes a reviewed specification and vectors; actual installed publication types, factories, SDK and sinks are separate numbered deliveries. Applicable unchanged package/artifact evidence, native CI, separate final-head semantic review and actual-main document/source readback remain mandatory before canonical Done.
