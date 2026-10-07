# Current implementation ownership — EQ122

Current optional implementation is in this I/O repository, experimentala8; original R4 story/version statements below are historical accepted contract provenance. Only package/receipt version markers and repository ownership change in extraction. Source/math/schema/availability/sampling/precision/limits stay unchanged. [Migration](../DUCKDB_MIGRATION.md) records compatibility and actual delivery gates.

# Explicit retained equity source mapping

EQ050 [issue57](https://github.com/atulsrivas1/equity-features/issues/57),
[pre-code plan](https://github.com/atulsrivas1/equity-features/blob/main/docs/stories/EQ-050_PLAN.md). Optional adapter0.1.0a2, contracts
0.0.4a4/schema1, DuckDB1.5.6. Core packages and mathematical algorithms unchanged.
This API transforms bounded caller-owned columns; EQ051 owns historical reads.

## API and declarations

`MappingPolicy(source_schema, price_unit, interpretation, rounding, instrument_ids,
source_clock, eligibility_policy=None, eligible_default=None, max_rows=10000)`
requires explicit PriceUnit, binary64_exact/decimal_repr interpretation, exact/
half_even rounding, unique integer-to-opaque-canonical instrument pairs, and clock
`event` for trades/TBBO or `receive_aggregation` for OHLCV. No source clock is
certified by a column name. A caller lacking clock evidence must not assert it.
Units/currency, instrument permanence and policy truth remain caller-owned.

`RowOccurrence(source_token, original_row, order_key)` declares an original retained
source occurrence with nonnegative int64 row/order. Its event ID hashes source
token plus original row; payload equality never merges distinct occurrences.
Order keys preserve supplied tie order, not certified exchange sequence/uniqueness.
The caller retains source-token lineage; it is not inferred from an optimized row.

`map_columns(policy, columns, *, metadata, occurrences, sessions) -> MappedSource`
accepts a concrete dictionary of equally sized tuple/list columns; each row needs
a typed occurrence and explicit session label. No partition-date session inference.
Required source columns are instrument_id and ts_utc even for zero rows.
MappingPolicy supplies price unit matching metadata, raw adjustment only, and quote
metadata must explicitly declare trade_snapshot. Metadata coverage/scope/source
remain supplied assertions. The mapper cannot certify completeness or a calendar.

The returned CanonicalBatch owns immutable columns. Existing validate_batch checks
semantic ordering, uniqueness, bounds, OHLC, nonnegative shares and quote states.
No sorting, filling, deduplication, ticker lookup, adjustment or source retrieval.
Missing payload columns remain absent; present nulls remain null; valid zero stays
zero. Missing values can leave dependent feature readiness unavailable.

## Fields, clocks and precision

| Source | Canonical mapping | Explicit limits |
| --- | --- | --- |
| trades | TRADE event_ns, occurrence event_id/order_key, price/size, eligible, optional condition | eligible Boolean source column with policy or governed caller default required; tick_rule_sign is not eligibility |
| tbbo | QUOTE event_ns, occurrence event_id/order_key, bid/ask/bid_size/ask_size | trade_snapshot only; normal/locked/crossed/invalid states retained |
| ohlcv-1m | BAR start_ns/end_ns, open/high/low/close/volume | whole UTC minute start; end=start+60s; declared receive aggregation clock |
| ohlcv-1d | DAILY start_ns/end_ns, open/high/low/close/volume | whole UTC day start; end=start+24h; no regular-session relabeling |

`parse_utc_ns` accepts exact int64 UTCns or YYYY-MM-DD[T or space]HH:MM:SS with
optional1–9 fractional digits and Z/+00:00. Integer day arithmetic preserves
nanoseconds beyond float precision and negative epochs; invalid calendars, leap
seconds, unknown offsets, float/Boolean epochs and int64 overflow fail. No float
timestamp conversion or microsecond truncation. Bar interval overflow also fails.

Retained DOUBLE prices use accepted quantize_float_prices. binary64_exact uses
actual binary value; decimal_repr uses shortest decimal text, an explicit alternate
interpretation. exact rejects remainder; half_even records rounded cells. Example
10.125 scale2 ->1012, 10.375 ->1038.0.1 at scale2 fails binary64_exact/exact but
decimal_repr/exact gives10. Original provider scaled coefficients are not recovered
or certified from DOUBLE by either policy. NaN/infinity/Boolean/non-float prices
and scaled overflow fail. Shares/volume require exact nonnegative int64 integers;
retained wider quantities exceeding int64 fail. No invented notional/trade count.

Optional supplied known_at_ns accepts the same exact parser and preserves null;
absence stays absent. Event time/bar end is never substituted for availability.
Causal features may remain unavailable; explicitly labeled reconstruction is
separate accepted core behavior. Zero-volume stale OHLC fails existing canonical
admission; caller explicit normalization is required, never silent clearing.

MappingReport retains retained-map1, rows, clock, eligibility policy/source, per-field
price conversion/rounded counts, unmapped field names and digest. Digest binds
policy, canonical columns, original metadata, occurrences and mapping report
choices; source mapping_version/input_id are extended with this identity. Original
source/snapshot and supplied coverage/availability remain intact. Report digests
are neither source truth nor authentication. Unknown source columns are unmapped.

## Errors, qualification and scope

Fixed safe SourceError messages suppress original contexts: SCHEMA for malformed
source/config/admission/identity/precision; UNAVAILABLE for unmapped instruments
or absent trade eligibility evidence; UNSUPPORTED for schemas/clock/sampling/
adjustment; LIMIT for row bound. Error messages expose no raw source paths/values.

Independent fixtures exercise four schemas, ns/int64 extrema, float policies and
hand ties, null/missing/zero, eligibility, equal payload occurrences, unknown/later
known-at, source-clock/interval/quantity/OHLC limits, identity binding and ownership.
Final review, native bothOS installed wheel/sdist and actual main publication gates
remain before Done. No private real-row numerical acceptance or R4 conformance
claim follows from mapping fixtures; EQ054/055 remain separate required layers.

Primary mapping context: [Databento OHLCV conventions](https://databento.com/docs/schemas-and-data-formats/ohlcv)
state interval-start, receive-based aggregation, UTC daily dates and omitted
no-trade intervals. Missing intervals do not become complete zero-volume rows.
[DBN source types](https://github.com/databento/dbn/tree/d368005a636bae84bff443cd6ddae6430a0ffd00/rust/dbn/src)
define original scaled prices; retained representation and caller declarations
need their own evidence. Provider documentation alone does not admit private rows.

EQ055 experimentala7 uses native strict ASCII UTCns SQL arithmetic, retaining Python mapping/parser parity and actual receipt adapter stamp. No row-callback SQL timestamp parsing, float epochs or TIMESTAMP_NS sentinel conversion. Integer UTCns/standard retained formats and purecore/math/runtimepins are unchanged; Unicode-digit clock/fraction input is rejected consistently. [Private qualification methodology](DUCKDB_REAL_QUALIFICATION.md) separates native/source checks from pending actual installed real-data acceptance and current delivery gates.
