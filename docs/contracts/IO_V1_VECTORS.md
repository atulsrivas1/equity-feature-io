# I/O v1 independent expected vectors

These are hand-worked design expectations for [IO_V1](IO_V1.md), not executed sink certification. EQ125 must implement and execute them against its runtime codec/fake sinks; EQ126/127 add actual backend/process fixtures. Synthetic labels only. No formula is changed.

## Scalar byte examples

Each code span is the exact ASCII C(x) byte sequence, without a newline. Scalar types remain distinct; an int64 unit/scaled integer cannot be rounded through binary64.

| Supplied canonical value | Expected bytes |
| --- | --- |
| unknown known_at / null scalar | `null` |
| zero integer | `{"int":"0"}` |
| exact UTCns minimum | `{"int":"-9223372036854775808"}` |
| exact UTCns maximum | `{"int":"9223372036854775807"}` |
| decimal128 maximum | `{"int":"99999999999999999999999999999999999999"}` |
| positive float zero | `{"float64":"0x0.0p+0"}` |
| negative float zero | `{"float64":"-0x0.0p+0"}` |
| float 1.25 | `{"float64":"0x1.4000000000000p+0"}` |
| Boolean false | `false` |
| literal string zero | `"0"` |
| status enum AVAILABLE | `{"enum":"results.Status","value":"available"}` |
| source input kind BAR | `{"enum":"inputs.DataKind","value":"bar"}` |
| entity instrument I / session S | `{"fields":{"instrument_id":"I","session_id":"S"},"record":"results.EntityKey"}` |
| string e followed by combining acute | `"e\u0301"` |
| precomposed e acute | `"\u00e9"` |

The two accented strings remain unequal: no Unicode normalization. Integer/float/string/Boolean/null zeros remain unequal. Decoder must reject int spelling +1, 01 or -0, float NaN/Infinity/noncanonical hex spelling, duplicate keys, unknown classes, unexpected fields, unpaired surrogates and executable payloads. DType/CanonicalBatch are not in the output codec registry.

## Complete-result distinctions

Take canonical namespace synthetic / session S, availability C=10/K=10/E=10 mode known_at; config digest 64 zero hex characters, no input bindings, backend synthetic version1, evidence_limit0/schema1/mathv1. These are supplied synthetic metadata, not a source truth assertion.

1. Empty complete result: values=(), quality=(), evidence=(), the metadata above. One result, zero cells/evidence; its metadata must survive. It differs from an envelope with zero result descriptors and no result writes.
2. Observed-empty count: feature synthetic.count, algorithm1/dtypeINT64/unitcount, entity I/S, value0; quality AVAILABLE/expected0/observed0/reasons(). One result, one cell, zero evidence. An empty observation permits this zero count; it is not a missing value.
3. Missing input: same column identity/entity, valueNone; quality MISSING_INPUT/expectedNone/observed0/reasons(ABSENT_INPUT). One result, one cell, zero evidence. This differs from case2 in value and quality, and must not become zero/AVAILABLE during storage.
4. Partial structured result: BreadthCounts(advancing1, declining0, unchanged0, expected2); quality INCOMPLETE_COVERAGE/expected2/observed1/reasons(PARTIAL_UNIVERSE). Preserve the nonnull structured value permitted by canonical validation; blanket nulling of every unavailable status would lose valid partial output.
5. Evidence mutation: bind one canonical BAR input with a supplied SourceBinding and a complete input scope, evidence(event_ns9, known_at_ns9, use consumed). Changing known_at_ns to null changes content even where selected value is unchanged; deleting evidence changes content and evidence_count. Neither change may replay the original receipt under the same reserved key. The null variant is decoded then passed to canonical validation; if invalid for the supplied result, reject it rather than infer known_at.

Every full result must validate with the existing canonical constructors before codec admission. Descriptor equality alone cannot prove content equality. Changing algorithm/unit/config/source metadata changes key identity as specified; changing a value or evidence under unchanged metadata keeps the intended key but changes content SHA and conflicts.

## Framing examples

Domain bytes for logical content are ASCII efio-content1 plus byte00 (14 bytes). Zero-result publication hashes those bytes alone. A test sequence containing a scalar null (illustrating framing, not a legal FeatureResult publication) appends unsigned big-endian length4 (`0000000000000004` hex) then ASCII null. Two such frames are different from one frame of eight bytes. Backend files/compression/timestamps never enter this logical hash.

[Hand-authored golden](IO_V1_GOLDENS.json) contains the full607-byte C(empty FeatureResult) wire tree specified above. One framed empty result has content SHA256 `c44d3b04e6f721a11dcce6d0232b2125d61a48a55d73f8cc168deb43e27b1a2c`; zero results has `fbe925a7019c2ebb4df50356cc17f1666e1e0f6d39b01dcd4bdc6a2b24fe9a43`. SHA values are derived with the standard SHA256 primitive over the manually authored bytes, not output from a production codec. `python tools/check_io_spec.py --core-root <canonical-checkout>` verifies framing/digests,29-record/four-enum canonical closure, actual canonical empty/missing/partial validity and signed-zero facts. It does not execute a sink or implement the EQ125 serializer. EQ125 must match these bytes/hash and add nonempty structured/evidence/key goldens and runtime rejection/trace execution; a serializer self-roundtrip alone is insufficient.

Key bytes use efio-key1 plus byte00 followed by the exact sorted canonical K object. content_sha/counts/bounds/caller_created_at_ns are excluded from K. Change only caller_created_at_ns: same key/content, original receipt replay. Change only content bytes with identical descriptor: same key, different content, conflict. Change destination_scope, generation_id, config digest, source snapshot or ordered algorithm header: different K/key. supersedes_key is an opaque SHA of an earlier key, not a request to delete it.

## Hand-worked protocol traces

R means the original verified immutable completion receipt; K is one admitted key; A and B have unequal content digests/counts where stated. These are state expectations, not a fake backend whose behavior is asserted as production.

| Trace | Expected state / visible output |
| --- | --- |
| begin K/A; write all contiguous results; commit | COMMITTED, R binds A/counts; qualified read returns all components |
| begin K/A after commitment | original R, no new attempt/write/storage mutation |
| begin K/B after commitment | CONFLICT; R/A unchanged |
| begin K/A staging; another begin K/B | CONFLICT before B writes; staging A remains nonvisible |
| begin K/A; one write; precommit definitive failure; abort | ABORTED, no receipt/visible output; same-content retry uses new attempt |
| after ABORTED K/A, begin K/B within reservation retention | CONFLICT; abort did not authorize a different-content rewrite |
| begin K/A; commit persists; response lost | COMMIT_UNKNOWN to caller; lookup COMMITTED returns R; retry begin returns R |
| commit outcome unknown; lookup transport unavailable | UNKNOWN/UNAVAILABLE, no absence claim or blind overwrite |
| cancel before commitment; successful abort | ABORTED, no visible output; staging cleanup stays in owned destination |
| cancel after committed visibility; abort | COMMITTED with R; cannot retract accepted A |
| empty zero-result envelope; begin then commit | COMMITTED with zero counts/descriptors; no fabricated values |
| unknown codec2 before begin | INCOMPATIBLE_VERSION, no reservation or write |
| required multi-process writer support absent | UNSUPPORTED_CAPABILITY, no reservation or write |
| write ordinal1 before ordinal0 / duplicate ordinal | INVALID_CONTENT, no completion receipt |
| write exceeds bytes/cells/evidence bound | RESOURCE_LIMIT, no accepted completion |
| actual result descriptor differs from envelope | INVALID_CONTENT, no completion |
| commit has missing result/component/count or wrong digest | no completion; INVALID_CONTENT or CONFLICT as specified |
| alter one stored artifact byte/hash/required table | CORRUPTION, withhold readback even if value rows seem unchanged |
| lookup key without state evidence during outage | UNKNOWN/UNAVAILABLE; never ABSENT |
| new generation K2 with explicit supersedes K | new receipt R2; R preserved, catalog selection outside sink |

Reader visibility, response loss, abort/commit race and reservation tombstone retention need backend qualification. Source errors, unknown known_at and missing/observed-empty acquisition continue to follow existing canonical input contracts. No trace certifies provider truth, historical causal completeness, filesystem durability or worker task ownership.
