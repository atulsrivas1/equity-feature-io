# Current implementation ownership — EQ122

Current optional implementation is in this I/O repository, experimentala8; original R4 story/version statements below are historical accepted contract provenance. Only package/receipt version markers and repository ownership change in extraction. Source/math/schema/availability/sampling/precision/limits stay unchanged. [Migration](../DUCKDB_MIGRATION.md) records compatibility and actual delivery gates.

# Actual installed DuckDB conformance

[EQ054](https://github.com/atulsrivas1/equity-features/issues/61) qualifies the
optional adapter with the existing pure [SDK](https://github.com/atulsrivas1/equity-features/blob/main/docs/contracts/ADAPTER_KIT.md).
The [concrete pre-code plan](https://github.com/atulsrivas1/equity-features/blob/main/docs/stories/EQ-054_PLAN.md) fixes thirty cases and
independent expected results. Optional0.1.0a6 preserves original-read2/retained-map1,
canonical schema1, corepaira4/consumer0.4.0/math/dependencies and runtime pins
DuckDB1.5.6/NumPy2.2.6. Acquisition1 records actual adapter versiona6.

## Reproduce the standalone fixture

Install the actual core and optional wheel or source archives in a fresh environment
as described in [installation](https://github.com/atulsrivas1/equity-features/blob/main/docs/INSTALLING.md), including explicit native pins.
Run the checked-in [standalone example](../../examples/duckdb_conformance.py) using
that environment's Python from a directory outside repository imports:

```text
python -I /absolute/checkout/examples/duckdb_conformance.py --installed --output conformance.json
```

On Windows, use the corresponding absolute Windows path. --installed requires
actual site-packages imports of both pure packages, optional adapter, DuckDB and
NumPy; source/editable imports do not satisfy it. The example uses fictional caller
identities, actual temporary DuckDB catalogs and original/optimized Parquet files.
All temporary fixture files are cleaned up. No credentials or provider data.
run_suite(require_installed=False) permits developer/source testing, accurately
reports import provenance, and does not substitute for installed acceptance.

Actual adapter iteration returns envelopes or captured safe SourceErrorCodes. Those
finite observed outcomes enter unchanged run_conformance. Independent expected codes
are fixed separately; unexpected exceptions or mismatched outcomes fail the command.
The SDK does not acquire sources itself. Three cases intentionally mutate actual
delivered envelopes and are labeled SDK validation probes, not bad adapter outputs.
Constructor and semantic invariants remain enforced; no object mutation bypass.

## Checked populations and mathematics

| Population | Actual checks |
| --- | --- |
| Trades | Three price100/102/102, size2/3/3 observations, two tied equal payloads with distinct occurrences; exact1ns selection and empty selection |
| Sampled quotes | Actual TBBO bid10/ask12, scaled coefficients1000/1200; explicit trade_snapshot; continuous request rejected |
| Minute bars | Two complete intervals, OHLCV(10,12,9,11,3) and(11,14,10,12,5); partial end excludes unfinished second bar |
| UTCdaily | Three supplied24h slots with closes10/20/30; incomplete final cutoff excludes the last interval |
| Source routes | One actual catalog with overlapping curated/prepared metadata; each explicit snapshot delivers3 rows, never a union |
| Unsupported/missing/errors | Snapshot/namespace/unit/identity, row/chunk/hash bounds, actual cancellation, missing eligibility/partition/file, stale catalog/pin |
| SDK rejections | Invalid ordinal/final and inconsistent source coverage across actual delivered chunks |

Sixteen independent numerical/unit/quality/binding assertions consume actual read
populations through installed public calculations. Trades give count3, volume8,
notional81200 at price scale2, VWAP101.5 and mean8/3. Bars give open10/high14/low9/
close12/volume8 and close-weighted proxy93/8=11.625; actual notional is missing input.
Daily SMA3 and anchored EMA3 seed both equal20. Unknown and later known-at remain
present and make causal trade count unavailable. Values/statuses/units and actual
canonical source binding are checked; ratio tolerance is absolute/relative1e-12.
Synthetic known-at, eligibility, calendar and selected-population certificates are
explicit fixture assertions, not inferred provider evidence.

Source coverage may legitimately exceed a requested/delivered subset. The SDK checks
consistent source coverage across chunks, independently of each chunk's actual
delivered count; it does not authenticate a declared complete source population.
The coverage rejection probe changes only one chunk's full source assertion. Earlier
uniformly changed source counts were a legal declaration and are not called defects.

Prior independent DuckDB tests retain resolver overlap/substitution/missing/schema/
pin boundaries, price/time/quantity/null/occurrence mapping, bounded original reads,
supplied holiday/DST/earlyclose/reference history gaps and cumulative hash races.
Together these constitute synthetic qualification; no in-memory adapter replaces
actual reads. All existing pure calculations/capabilities remain unchanged.

## Installed reports and limits

The optional repeat builder runs the standalone --installed example for actual
wheel and source packages on both native operating systems, checks core module/
metadata invariance and installed typing of six adapter modules plus the example.
Each bundle retains conformance-<system>-<form>.json alongside installed/read reports.
duckdb-conformance1 binds thirty named expected/observed/stage outcomes, sixteen
numerical/unit/status/binding checks, installed import enforcement, runtime/producer,
current source commit/clean status, normalized-LF harness SHA256 and actual three
input archive hashes/form. Four native conformance reports expand total current
optional/Foundation native reports from20 to24; archive count remains24.

Qualification checks these finite synthetic populations, error codes and admitted
calculations. It cannot establish provider truth, private source support, source
completeness/rights, exchange ordering, causal availability, atomic snapshot isolation,
hard resource caps or full-corpus performance. [Acquisition evidence](DUCKDB_EVIDENCE.md)
and [measured read](DUCKDB_READER.md) limitations remain. EQ055 must separately freeze
and qualify actual private numerical scope. Final source/receipt reviews, currentCI,
four fresh downloaded-form installations, actualmain artifact/report/publication
and Releasedpostread gates precede EQ054 Done; EQ056 requires both testing layers.

EQ055 experimentala7 uses native strict ASCII UTCns SQL arithmetic, retaining Python mapping/parser parity and actual receipt adapter stamp. No row-callback SQL timestamp parsing, float epochs or TIMESTAMP_NS sentinel conversion. Integer UTCns/standard retained formats and purecore/math/runtimepins are unchanged; Unicode-digit clock/fraction input is rejected consistently. [Private qualification methodology](DUCKDB_REAL_QUALIFICATION.md) separates native/source checks from pending actual installed real-data acceptance and current delivery gates.
