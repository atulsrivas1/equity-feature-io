# Current implementation ownership — EQ122

Current optional implementation is in this I/O repository, experimentala8; original R4 story/version statements below are historical accepted contract provenance. Only package/receipt version markers and repository ownership change in extraction. Source/math/schema/availability/sampling/precision/limits stay unchanged. [Migration](../DUCKDB_MIGRATION.md) records compatibility and actual delivery gates.

# Supplied calendars, history and references

EQ052 optional0.1.0a4 reuses unchanged schema1/corepaira4 contracts. It prepares
bounded requests and validates caller-owned evidence outside calculations.
[Issue59](https://github.com/atulsrivas1/equity-features/issues/59) owns actual
delivery acceptance; [pre-code plan](https://github.com/atulsrivas1/equity-features/blob/main/docs/stories/EQ-052_PLAN.md) freezes independent
expectations. Read with [reader](DUCKDB_READER.md), [history](https://github.com/atulsrivas1/equity-features/blob/main/docs/api/HISTORY.md) and
[action/reference policies](https://github.com/atulsrivas1/equity-features/blob/main/docs/api/ACTION_POLICIES.md).

## Calendar definition

`GovernedCalendar(namespace, version, evidence_id, dated_sessions, closed_dates=(),
grid_kind="supplied_sessions", max_sessions=4096)` owns concrete ISO-date/SessionSpec
pairs and declared closures. Unique dates/IDs, one namespace, increasing
nonoverlapping actual bounds and configured count are required. An explicit closed
date cannot also be a supplied session. Lists detach into tuples. No sorting,
timezone conversion, holiday lookup or calendar fetching occurs. A timezone label
does not compute UTC offsets: the caller supplies exact DST and early-close bounds,
including SessionSpec scheduled-close evidence. The definition digest binds all
supplied fields; it does not authenticate calendar authority.

`grid_kind="utc_daily_intervals"` requires date-matched UTC midnight and exactly24h
bounds. Retained source daily bars aggregate a UTC interval; they cannot become
exchange RTH daily bars by changing a label. Other supplied sessions may govern
intraday reads, with separately normalized compatible daily summaries prepared by
explicit caller composition. `sessions`, `partition_sessions` and `identity_digest`
expose immutable declarations.

For ReadConfig, supply these SessionSpecs and the explicit calendar version. Filter
partition-session pairs to the exact resolver-selected dates if resolving a subset;
ReadConfig requires equality with that selection. Keep the caller's source scope,
mapping policies and calendar evidence alongside the configuration. EQ053 binds
acquisition receipts; file dates alone never supply these definitions.

## Required history request

`plan_history(calendar, window, initialization_anchor=None,
anchor_previous_slot=False, max_sessions=4096)->HistoryPlan` requires the existing
WindowSpec governed IDs to match the whole calendar. Finite selection delegates to
WindowSpec: prior_only excludes target; completed_eod includes target. An explicit
initialization anchor retains the contiguous prefix through the same selected
endpoint. Optional previous-slot inclusion retains a present anchor predecessor.
Missing source partitions are not compressed out of this grid. Required absent/
future anchors or predecessors fail unavailable; configured slot limits fail limit.
Structural insufficient history remains visible in `history_complete` and cannot
produce a successful request. This property is request sufficiency, not input or
mathematical readiness. The plan digest binds all calendar/window/anchor controls.

Required counts follow accepted mathematics, selected explicitly by the caller:

| Calculation | Window/prefix requirement |
| --- | --- |
| Return horizon h | h+1 completed closes, target included |
| SMA period N | N completed closes, target included |
| Volatility over N returns | N+1 completed closes, target included |
| Prior high/low | N prior_only slots, target excluded |
| EMA / RSI | Explicit contiguous anchor prefix and accepted seed counts |
| ATR | Explicit TR anchor prefix plus its predecessor close and accepted seed counts |

`HistoryPlan.acquisition_request(request_id,kind,instruments,snapshot_id,price_unit,
availability,max_batch_rows=1024,max_rows=10000,max_batches=100,sampling="none")`
constructs the existing typed AcquisitionRequest with selected IDs and first-open/
last-close bounds. Supported market kinds use ordinary half-open events or completed
intervals; QUOTE requires explicit compatible sampling. DAILY requires the UTCdaily
calendar mode. Auctions/reference/live/adjusted acquisition remain reader limits.
Pure calculation config periods, algorithms, actual cutoffs and admission remain
authoritative; no feature values are calculated by request planning.

## Actual rows and slot certificates

`make_history_context(calendar,entity,daily,slot_coverage,
initialization_anchor=None,action_admission=None)->HistoryContext` validates the
supplied canonical DAILY population against the full governed grid. Namespace,
instrument, unique session membership, exact open/close intervals and actual row
count must match. Each caller certificate expects one normalized daily row and
observed0or1 must agree with its actual presence. None requires every slot absent.
Null close stays a present row with unavailable fields; it is never zero-filled.
Certificates preserve caller completeness assertions; no provider completeness is
inferred from whole-frame counts, rows or files. Unknown source coverage remains
unknown. Existing HistoryContext binds sessions/certificates/anchor/action evidence.

A complete later finite window can recover while an earlier missing slot still
blocks an anchored recursive calculation. Public synthetic integration with
closes(10,missing,30,40,50) independently yields SMA3=40 and anchored EMA unavailable;
prior_only two-slot request yields(30,40), whose baseline is35. A missing prefix
partition remains a terminal missing acquisition; callers may separately compose
explicitly collected partial evidence, never relabel it complete. Causal unknown
known-at remains unavailable; explicit reconstruction retains its separate reason/
identity. [Accepted history rules](https://github.com/atulsrivas1/equity-features/blob/main/docs/api/HISTORY.md) determine exact quality and arithmetic.

## Supplied reference intent and gaps

`ReferenceRequest(namespace,snapshot_id,instruments,fact_kinds,availability,
max_rows=10000)` declares one bounded canonical reference revision and C/K/E/mode.
`resolve_supplied_reference(request,batch=None)->ReferenceResolution` returns the
same owned canonical batch after structural/kind/namespace/revision/identity/fact/
count checks. None is unavailable with not_supplied. Supplied disposition preserves
effective bounds, reference IDs, exact coefficients and original known-at.
`evidence_gaps` reports whole-supplied-population incomplete coverage and unknown/
later knowledge under the request mode. These observations do not select relevant
facts, certify policy/feature readiness or remove future rows. Request/resolution
digests bind the exact intent and supplied content; hashes do not certify provider
truth or PIT. Pure action/classification admission selects effective facts and
enforces actual revision/cutoff/quality rules.

This API does not acquire vendor reference files, infer membership from a recent
sector snapshot, convert retained DOUBLE factors to certified exact ratios or
silently apply adjustments. Unsupported causal references remain explicit gaps.
Synthetic split and membership revisions exercise late knowledge versus explicit
reconstruction through unchanged public pure APIs. Real source support is qualified
under EQ055; no private population or golden is frozen here.

## Qualification boundary

Public tests use independently specified supplied calendar dates, exact UTC bounds,
hand values and temporary real DuckDB/Parquet files. Fictional DST/holiday/early-close
definitions are not exchange-calendar truth. Strict typing, full installed optional
suite, bothOS CI, core invariance, separate final-head review and actual main
artifact/publication readback precede Done. R4 conformance/private numerical
acceptance remain EQ054/055.
