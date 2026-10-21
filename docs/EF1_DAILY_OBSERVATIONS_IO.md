# EF1 daily observations I/O — EQ212 supporting EQ166

`equity_feature_duckdb.ef1.DailyObservationsInputs` retains six named nullable
roles, in order: `calendar_manifest`, `calendar_slots`, `observation_coverage`,
`raw_observations`, `common_observations`, `basis_provenance`. Pass `.slots` to
`compute_ef1`; generic supplied-input transport receives `.batches`, the present
batch tuple in role order. A present empty batch remains present. Per-slot
`provenance` is exactly `synthetic`, `duckdb_backed_observed` or `unavailable`;
only absent roles use unavailable. The frozen container retains batch identity.

`make_daily_observations_batch(column_order, rows, *, metadata)` converts the
caller's eight-column REFERENCE schema into canonical columns. It preserves
original row and column order, identifiers, JSON text, known-at/null values,
source snapshots, units, adjustment, scope and coverage. Caller metadata is
mandatory. It does not choose observations, validate daily admission mathematics,
normalize prices, derive basis factors or manufacture calendar/coverage proofs.
The pure producer owns the closed JSON grammar, calendar joins, selection,
causality, exact arithmetic and readiness. Legacy DAILY/BAR zero-volume validation
is unchanged. Raw daily volume zero is representable in REFERENCE JSON and is
admitted only through the new producer's explicit numerical profile.

The supported supplied profile is `exact_integer_price_units_v1`, context
`ef1-daily-context2`, mapping `ef1-daily-map2`, algorithm `daily-observations-v2`.
Global mathematical policy stays v1; generic SDK, sink, codec and source extractor
are unchanged. Original binary64, inferred adjustment and nanounit rounding routes
remain unsupported. This implementation does not establish source parity.

Three original synthetic fixture/config helpers are available:

- `V235-literal-last252`: last252 admitted pre-target observations.
- `V201-observed-not-scheduled`: current civil week with explicit dataset absence.
- `V223-prior-skips-invalid-populated-period`: latest admitted populated prior week.

Use `synthetic_daily_observations_fixture(case_id)` and
`synthetic_daily_observations_config(case_id)`. These return detached literal
fixtures/configs and contain supplied synthetic calendar and basis assertions.
[Runnable example](../examples/ef1_daily_observations.py) computes the actual
producer result. No market data or source paths occur in these public examples.

Tests use the exact original synthetic conformance whitelist (119 packets,
91 full result goldens and28 real semantic refusal cases). The fixture is bound
by SHA256 `479948037cd6d2fca3901cdb9cf3fcbba6256acbbcb9440bcd68e0362d7688c5`.
Conversion tests compare every supplied cell and metadata field. Composition
checks require actual producer results, unchanged SDK publication, a fresh output
DuckDB, identical retry, close/reopen and complete stored-result readback.
Authored tests are separate from executed evidence in SESSION_HANDOFF.md.

No N-drive market rows were queried. Metadata-only inspection of four catalogs
and18 schemas provides partial capability discovery; original record identities,
order, known-at, complete calendars, notional, lineage and rights remain
unqualified. Synthetic provenance must not silently become observed provenance.
Full EQ164 source audit, independent review, installed Windows/Linux four-form
qualification, integrated worker/browser/release gates and original EQ166 source
obligations remain open. This subset does not complete EF1 or EQ166.

V3A1 corrects only the `V318-raw_observations-none` literal quality fence:
without raw admission operands, lastN cannot prove a stopping suffix and uses
all three supplied historical coverage assertions (expected3/observed3). Feature
values/status/reasons/metadata/evidence and all119 inputs/configs stay unchanged;
118 complete packets and all28 pure refusals are byte-equivalent in content.
The earlier publicV3 corpus remains preserved in coordinator records. For
`X212-duplicate-record`, the direct pure error is `duplicate`; generic worker
metadata admission reports `RESULT_IDENTITY_MISMATCH` earlier because physical
row count contradicts declared observed count. Tests preserve both actual stages.

The bounded author Windows source run now passes actual91computed-result SDK/
fresh-DuckDB publication, identical retry, close/reopen and complete stored
canonical readback comparisons. A separate corrected semantic test passes all28
actual direct pure invocations; final9adapter tests pass. See SESSION_HANDOFF.md
for exact run boundaries, retained initial stage-probe failure and pending exact-
commit independent/installed/integration/browser/release gates. These results
are source-level author evidence; whole-story completion is not inferred.
