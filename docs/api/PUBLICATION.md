# Publication v1 API and extension kit

Canonical [EQ125 #282](https://github.com/atulsrivas1/equity-features/issues/282), E19/R4.1. Experimental matching io-contracts/SDK0.1.0a2; exact canonical contracts0.0.4a4. The [frozen specification](../contracts/IO_V1.md) defines unchanged efio-json1/key1/content1. This implementation supplies immutable contracts, safe codec, lifecycle helpers and logical conformance. Backend implementations and process/storage qualification remain EQ126/127; worker claims/scheduling/catalogs remain R5.

## Public types and operations

`equity_feature_io_contracts` exports FeatureHeader, ResultDescriptor, PublicationIdentity (the exact K fields), PublicationEnvelope (K plus expected content/counts/limits/operational time), ArtifactReference, CompletionReceipt, PublicationState, PublicationStatus, AbortOutcome, SinkCapabilities, SinkError/Code, WriteSession and ResultSink. Immutable tuples/exact int64 counts/timestamps/version labels/receipt-state coherence are checked. Concrete capabilities implement the existing structural factory view. Canonical metadata/results are reused, without copied schemas or mathematical definitions.

ResultSink implements capabilities, begin(envelope)->session|original receipt, write(session,ordinal,FeatureResult), commit(session)->receipt, abort(session)->outcome, lookup(key)->status and read(receipt)->bounded tuple of complete results. Handles are trusted local opaque objects scoped to one sink/attempt; attempt_id is diagnostic, not a portable reconstruction token. Every backend must check ownership/order/descriptors/negotiated counts/bytes/cells/evidence and preserve reservation tombstones and original receipts within its stated retention scope. Capability modes and retention are declarations requiring backend evidence, not guarantees inferred from class names.

`equity_feature_io_sdk` exports prepare_publication, verify_content, verify_receipt, publish and the result/envelope/receipt encode/decode functions with pre-construction exact-version admission, content_digest, idempotency_key, descriptor and qualify_sink. The closed codec imports precisely29canonical records/fourenums; no dynamic import, executable payload or pickle. It reconstructs canonical constructors and rejects duplicates, extra/missing/unknown fields, invalid Unicode, noncanonical scalar/JSON spelling, nonfinite floats and forged invalid objects. Integer/ns/scaled-decimal strings and float.hex retain exact precision/signed zero; no Unicode normalization. K excludes counts/content/limits/operational timestamps; same intended generation with changed content conflicts. Physical hashes are separate from logical content.

```python
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import prepare_publication, publish, verify_receipt
# supplied_results: tuple of validated canonical FeatureResult; supplied_sink: ResultSink.
limits = SinkRequirements(max_results=100, max_chunk_bytes=1_048_576,
                          max_total_bytes=10_485_760, max_result_cells=100_000,
                          max_evidence_rows=100_000)
envelope = prepare_publication(supplied_results, destination_scope="result-destination",
    generation_id="generation1", job_id="job1", partition_id="partition1", limits=limits)
receipt = publish(supplied_sink, envelope, supplied_results)
readback = supplied_sink.read(receipt)  # backend verifies referenced physical bytes/components
verify_receipt(receipt, envelope, readback)  # complete logical identity/count/content verification
```

Preparation requires a concrete tuple, one complete FeatureResult per write. Requested bounds are admitted before begin; callers select compatible limits. Each complete encoded result and cumulative publication is checked; this API does not fragment structured rows or claim row-proportional memory. Preparation/validation can reencode complete result units; resource certification requires actual backend measurements. No SDK acquisition, credentials, paths, clocks, schedules or storage backend imports occur.

## Failure and recovery

publish validates content and declared capabilities before begin, writes contiguous ordinals, checks cancellation before each write/commit and validates committed/replayed receipts. Partial precommit failure follows abort. An ABORTED outcome permits a retry classification/new begin; a COMMITTED abort preserves the original receipt; UNKNOWN requires lookup. Raw commit exceptions default to COMMIT_UNKNOWN. Confirmed COMMITTED lookup returns its verified original receipt; failed/unknown/noncommitted lookup never certifies absence or rollback. A caller may receive COMMIT_UNKNOWN and must resolve state through the backend's qualified recovery policy. Typed backend failures remain distinct; diagnostics suppress raw exception/config/credential content. Cancellation cannot retract a committed generation. No exactly-once worker/storage promise is made.

verify_receipt checks complete K/key/content/count/descriptor bindings, with supplied results when available; physical references require backend hashing/existence checks. readback corruption never becomes missing/zero data. Envelope/receipt JSON uses exact inert plain objects with tagged canonical metadata/counts, no session serialization. Decoding a receipt also recomputes its key. Original artifact references and first caller commit timestamp remain unchanged on replay.

## Reusable logical qualification

`qualify_sink(factory, synthetic_results, limits)` calls a caller-provided factory creating a NEW isolated destination for each case. It executes21logical checks: complete readback/original replay/lookup; committed/staging/aborted different-content conflict; staging busy/nonvisibility; idempotent abort/new attempt; abort after commitment; zero publication; version and writer requirement rejection; ordinal/foreign-session/partial/limit/descriptor rejection; receipt tamper and explicit supersession preserving the earlier receipt. Report cases retain expected/observed stable outcomes; raw extension diagnostics are suppressed. Caller owns destination creation/cleanup and supported capability selection. It does real writes, so never point it at production/private sources or an unrelated destination.

The independently packaged factory fixture.a1 adds an in-memory MemorySink and18explicit canonical synthetic results covering every closed record/enum, null/status/structured/scaled/ns/evidence/availability ordering. MemorySink's scope is one Python instance; restart and pre/postvisibility failures are simulations. It is not production storage, elapsed-time/process durability, provider/source rights or the full EQ128 extension example. Additional unit fixtures execute the20frozen trace expectations, response-loss/unknown lookup/cancel/physical corruption and intentionally defective reader/replay detection. Actual Windows/Linux storage/process matrices remain separate numbered work.

Validation: `python tests/test_publication.py`; installed execution uses `--installed --report-json <file>`. Hand-written nonempty count/missing/partial/evidence wire/content/key goldens live in [tests/publication_goldens.json](../../tests/publication_goldens.json); they are authored with stdlib JSON/SHA without calling the production serializer. Native/fresh-form builder binds these bytes and test-suite hashes. Passing logical conformance does not certify untested backend guarantees.

## Operational requirements and staging policy

The frozen envelope carries logical versions/counts/limits, not requested visibility/writer topology/retention. prepare_publication accepts a limits-only SinkRequirements (visibility/writer_mode None, retention1); it rejects any non-limit guarantee rather than silently losing it. Supply additional exact requirements to `publish(..., requirements=requested_requirements)`. The publisher admits both envelope limits and supplied versions/bounds/visibility/writer_mode/retention before begin; rejected requests create no reservation. For example, prepare with the limits above, then use `requested_requirements = dataclasses.replace(limits, visibility="manifest_last", writer_mode="serialized_writer", reservation_retention_ns=1000)` at publication. A transactional/single_writer/retention1 fixture rejects that request. Request fields are local admission constraints; they do not widen frozen K or make an unsupported backend guarantee true.

qualify_sink accepts explicit `staging_recovery="busy"` (default) or `"restart"`, matching the frozen policy alternatives. Restart qualification requires a new exclusive handle, invalidated old handle and STAGING lookup without a receipt, followed by complete writes using that replacement handle, commit, receipt verification and exact readback. A logical restart check does not establish exclusive process ownership or durable recovery; the backend must separately qualify and document those guarantees. A backend declaring restart is not universally required to return BUSY.

Envelope/receipt encoders and decoders reject unsupported exact versions and descriptor schema/math declarations. Decoder checks the raw version declarations before constructing current canonical records; recomputing a future-version key does not admit an unknown schema. Malformed wire remains INVALID_CONTENT; unsupported versions are INCOMPATIBLE_VERSION. No fallback or future-schema interpretation is inferred.

Factual `CORRUPTION` from write, commit, abort or lookup remains an error. A recovery receipt cannot override detected corruption. Backends must verify physical and logical committed content before exposing a committed receipt; a receipt alone does not establish intact stored bytes.
