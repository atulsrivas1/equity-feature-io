# Current implementation ownership — EQ122

Current optional implementation is in this I/O repository, experimentala8; original R4 story/version statements below are historical accepted contract provenance. Only package/receipt version markers and repository ownership change in extraction. Source/math/schema/availability/sampling/precision/limits stay unchanged. [Migration](../DUCKDB_MIGRATION.md) records compatibility and actual delivery gates.

# DuckDB acquisition evidence

Optional0.1.0a5 adds local acquisition observations to the existing bounded
[reader](DUCKDB_READER.md), [resolver](DUCKDB_RESOLVER.md),
[mapping](DUCKDB_MAPPING.md) and [governance](DUCKDB_GOVERNANCE.md).
[EQ053 plan](https://github.com/atulsrivas1/equity-features/blob/main/docs/stories/EQ-053_PLAN.md) preceded implementation;
[issue60](https://github.com/atulsrivas1/equity-features/issues/60) owns final gates.
Pure corepaira4/contracts/schema1/formulas/dependencies remain unchanged.

## Configure and obtain evidence

```python
from dataclasses import replace
from equity_feature_duckdb import DuckDBHistoricalAdapter, VerificationPolicy

# config is the explicit caller-owned ReadConfig; request is AcquisitionRequest.
policy = VerificationPolicy(max_hash_bytes=1_073_741_824, max_files=4096,
                            require_original_pins=True)
adapter = DuckDBHistoricalAdapter(replace(config, verification=policy))
result = adapter.read(request)
receipt = result.receipt
assert receipt is not None
print(receipt.schema, receipt.pin_strength, receipt.identity_digest)
```

Default policy uses the same bounds and require_original_pins=False. All selected
originals are hashed before and after SQL materialization, even without pins; there
is no size-only bypass. Required pins are the caller-supplied original_sha256 in
resolved FilePins. Missing required pins produce SourceError(UNAVAILABLE); observed
hashes never retroactively become prior pins. Any supplied original pin is enforced
regardless of the strict flag. Selected files/budget use exact positive integers;
the strict flag is an exact Boolean. Cancellation is checked during bounded hashes.

The accepted resolver reinspects the actual current route and all retained selected
partition metadata against the resolution and its catalog hash. This catches stale
catalog declarations and a changed resolution, including a self-consistently edited
digest. It preserves caller FilePin receipt IDs; those IDs are assertions, not
authenticated catalog issuers. Original files must match declared sizes; reader
schema/row-count checks still apply. Expected original hashes must match actual
observations, and before/after original hashes must match. Optimized files are never
queried; supplied optimized hashes are checked before/after. Without such a pin,
optimized content identity remains unverified despite retained path/size metadata.

All successful hashes share one cumulative max_hash_bytes budget, including the
resolver's two catalog reads, each selected original twice, each pinned optimized
file twice, and the final catalog read. Typical successful total is
`3 * catalog_bytes + 2 * original_bytes + 2 * pinned_optimized_bytes`.
This counts user-space file bytes hashed, not physical storage traffic. Exceeding
the bound raises SourceError(LIMIT) and exposes no partial output. Hash/schema/
metadata mismatches use safe fixed SCHEMA errors; missing files use UNAVAILABLE.
Backend/private paths are suppressed in errors.

## Receipt fields and identities

Successful actual data/empty/missing reads return a frozen AcquisitionReceipt,
schema acquisition1, adapter_version0.1.0a5, canonical_schema1. ReadResult's optional
default allows existing manual construction; actual public reads populate it.

| Field | Meaning |
| --- | --- |
| request_digest / configuration_digest | Exact request and explicit full mapping, supplied sessions, scope, coverage policy, verification settings and source configuration |
| resolved_digest / catalog_sha256 | Metadata resolution identity and matching actual catalog bytes |
| input_evidence_digest | Versioned original-read2 input identity including actual selected content observations |
| files | Owned FileEvidence tuples retaining whole ResolvedPartition, observed original SHA256 and checked optimized SHA256 or None |
| missing_sessions | Retained resolution's missing partition dates; not manufactured empty rows |
| source / normalization | Full-population canonical SourceBinding and MappingReport, or explicit missing-report absence |
| coverage / availability / calendar_version | Preserved source coverage and caller C/K/E/mode/calendar assertions |
| disposition / rows | data includes observed empty; missing is zero delivery without canonical population |
| pin_strength | all_selected_originals_pinned, observed_without_all_original_pins, or no_selected_files |
| hash_bytes / identity_digest | Successful cumulative hashed bytes and SHA256 of canonical sorted compact JSON of all receipt fields |

No timestamps/timing samples enter receipt identity. Repeating unchanged reads
with unchanged request/config yields the same receipt digest. Source mapping starts
with original-read2 input evidence; retained-map1 binds actual canonical columns,
normalization policy/conversion reports and metadata. Final receipt digest binds
that full-population output source, without a circular output mapping dependency.
Original occurrence tokens now include observed original content and physical row
identity: unchanged source occurrences stay stable across request subsets/chunks;
a valid unpinned same-size file replacement before acquisition changes occurrence
and receipt identities. Request/chunk configuration still changes delivery identity.
The prefix/version upgrade is an intentional experimental identity change from a3/a4.

Terminal missing output retains explicit missing dates and no normalization report;
observed empty has a real zero-row canonical mapping report. Neither becomes
complete source coverage by file presence or hash success. Unknown/later known-at
and source admission/substitutions remain unchanged; receipt availability records
the request rather than certifying provider PIT. Supplied calendar, eligibility,
coverage and precision policies remain assertions requiring independent admission.

## Limits, measurement and privacy

Matching pre/post observations detect changed bytes at those points. They do not
provide atomic snapshot isolation or rule out transient changes and reversions
between checks, file-system/hash collisions or arbitrary external mutations after
materialization. Immutable or independently retained source pins strengthen replay;
this API does not lock, rewrite or delete sources. Original/optimized byte hashes do
not prove numerical rewrite parity, exchange truth, rights or unknown availability.

ReadMetrics.verification_ns separates metadata/hash checks from SQL-fetch, owned
mapping/materialization and delivery-copy phases. verification_hash_bytes matches
receipt.hash_bytes. External whole-read timing includes all verification overhead.
Existing measurement native lifetime high-water/process-cap/I/O limits remain;
earlier a3 costs stay dated evidence. Current installed quick harness checks receipt
and numerical population parity and records these extra metrics.

Real receipts include private paths and retained source metadata. Keep them in the
private local evidence companion, with authorized access; do not publish them as
public fixtures or package artifacts. Public examples use synthetic files. This is
optional acquisition evidence for future EQ103 reuse, not a new pure calculation
execution receipt or provider certificate. Actual installed synthetic conformance,
private numerical integration and final R4 acceptance remain separate stories.

EQ055 experimentala7 uses native strict ASCII UTCns SQL arithmetic, retaining Python mapping/parser parity and actual receipt adapter stamp. No row-callback SQL timestamp parsing, float epochs or TIMESTAMP_NS sentinel conversion. Integer UTCns/standard retained formats and purecore/math/runtimepins are unchanged; Unicode-digit clock/fraction input is rejected consistently. [Private qualification methodology](DUCKDB_REAL_QUALIFICATION.md) separates native/source checks from pending actual installed real-data acceptance and current delivery gates.
