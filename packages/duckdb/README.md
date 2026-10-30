# Experimental DuckDB adapter

`equity-feature-duckdb`0.1.0a12 is an unreleased candidate and stays outside both pure packages.
It resolves bounded catalog metadata and maps owned retained-source columns into
canonical schema1. Bounded original-Parquet historical reads use caller-supplied
sessions, explicit coverage policies and exact UTCns predicates. R4 is incomplete.

Callers declare snapshot, units, price interpretation/rounding, source clock,
instrument/session identity and trade eligibility evidence. Missing/null/zero,
unknown known-at, substitutions and unverified admission stay explicit. Hashes
bind bytes; they do not establish provider truth, rights, completeness or PIT.

See repository docs/api/DUCKDB_RESOLVER.md, docs/api/DUCKDB_MAPPING.md and
docs/api/DUCKDB_READER.md. Installed synthetic reports distinguish whole-read
costs, mapping/copy phases and native lifetime peaks; no hard process cap.
No provider downloads, credentials, scheduling, publication or live feed.


EQ051 clean installation additionally pins NumPy2.2.6 in the optional adapter
runtime. DuckDB1.5.6 create_function requires NumPy in the observed fresh environment;
the development environment had masked this dependency. Install DuckDB1.5.6 and
NumPy2.2.6 explicitly before --no-deps project archive installation. Core runtime
dependencies remain unchanged; NumPy's existing upstream notice/hash provenance
is recorded in [release integrity](https://github.com/atulsrivas1/equity-features/blob/main/docs/RELEASE_INTEGRITY.md). Both native installed forms must verify
this exact runtime. Null timestamps pass through the parser and fail closed, following
[DuckDB UDF null semantics](https://www.duckdb.org/docs/current/clients/python/function).


EQ052 adds caller-owned versioned calendar/history requests, actual daily slot
certificate validation and supplied reference intent with visible availability gaps.
Existing pure HistoryContext/WindowSpec/policy admission remains authoritative.
See repository docs/api/DUCKDB_GOVERNANCE.md; no calendar/reference fetching or
UTCdaily-to-RTH relabeling. Actual delivery gates remain on issue59.


Version0.1.0a5 returns acquisition1 receipts and bounded catalog/original stability observations with explicit VerificationPolicy. Supplied pins differ from observed hashes; optimized data remains unqueried. Raw real receipts contain private paths. See docs/api/DUCKDB_EVIDENCE.md for fields, identity upgrade, budgets and non-atomic/provider/PIT limits. Purecore remains unchanged.

Version0.1.0a6 adds installed synthetic SDK qualification with thirty actual DuckDB outcomes and sixteen independently expected numerical/unit/status/source-binding checks. See repository docs/api/DUCKDB_CONFORMANCE.md and examples/duckdb_conformance.py. Installed typing covers six adapter modules and that example. Source-only runs are developer evidence; private real-data and final delivery gates remain separate.

Version0.1.0a7 parses SQL UTCns with a connection-local native macro and exact HUGEINT arithmetic/guardedBIGINT, strict ASCII ISO/null/calendar/clock/fraction/bounds checks. Python mapping stays exact; undocumented Unicode clock/fraction digits reject consistently. Purecore/runtimepins unchanged; actual receipt stampa7. See docs/api/DUCKDB_REAL_QUALIFICATION.md; current installed/private/delivery gates remain.

EQ122 moves current implementation to equity-feature-io; existing distributions/imports and R4 behavior are preserved. Only adapter receipt/package version markers and repository metadata change. See [migration](../../docs/DUCKDB_MIGRATION.md) and [current API](../../docs/api/DUCKDB_READER.md). Historical a7 acquisition/receipt evidence is retained in canonical equity-features.

## EF1 anchor adapter source authoring

The additive `equity_feature_duckdb.ef1` module supplies explicit canonical
anchor-provenance mapping, original synthetic trade/actual-notional-bar fixtures
and source/output path separation. See [API](../../docs/api/EF1_ANCHOR_INPUTS.md).
EQ212#570 is In progress; source authoring is not test/artifact acceptance. The
candidate carries the reviewed source version bump0.1.0a9; no existing a8
artifact identity includes these changes. SDK/sink codecs and
accepted historical acquisition remain unchanged.

The same candidate also authors explicit supplied-calendar proof mapping and
original C01 clock source fixtures in `equity_feature_duckdb.ef1`. See
[clock source API](../../docs/api/EF1_CLOCK_INPUTS.md). Clock readback checks are
authored but unexecuted; status feed support and source qualification are not
implied by this addition.

The additive supplied current-state status conversion is documented in
[EF1 status inputs](../../docs/api/EF1_STATUS_INPUTS.md). Its four explicit local
slots retain missingness and original metadata; observed/synthetic provenance is
caller-declared per role. The candidate includes labelled S01/S02/S03 fixtures and
source-authored independent composition/readback tests, without executed
qualification or any provider/N: dataset admission.

Sampled gap/opening-drive: `equity_feature_duckdb.ef1.PathGapInputs`,
`PathDriveInputs`, `make_path_prior_close`, and G01/G02/G03/D01 synthetic fixture
and context helpers are additive source candidates. See
[the path input contract](../../docs/api/EF1_PATH_INPUTS.md). Original knowledge,
coverage and supplied invalid volume/OHLC are preserved; no acquisition or
feature mathematics is added. Validation remains unexecuted during the study hold.

Observable opening/seconds and physical status-history transport is documented in [EF1_OBSERVABLE_IO.md](../../docs/EF1_OBSERVABLE_IO.md). Fixed nullable `.slots` preserve absent source roles; the present-only `.batches` view is not pure observable input.

Daily observation variants add fixed six nullable REFERENCE roles and lossless supplied-schema conversion with explicit provenance. See [daily observations](../../docs/EF1_DAILY_OBSERVATIONS_IO.md) for the supported exact-integer profile, original synthetic252/current-week/prior-week examples and remaining source/release gates.

The additive supplied gap endpoint uses four fixed nullable roles, lossless canonical conversion and explicit synthetic trade/bar examples. See [gap endpoint input API](../../docs/api/EF1_GAP_ENDPOINT_INPUTS.md) and [actual source validation](../../docs/EF1_GAP_ENDPOINT_IO.md). Existing SDK/sink contracts and old path producers remain unchanged; observed-data and release qualification are separate.

Regular completed-BAR prices use `equity_feature_duckdb.regular_bar_prices`: fixed nullable calendar/bars/population-proof roles, lossless supplied conversion and explicit R01/R08 synthetic helpers. See [API](../../docs/api/EF1_REGULAR_BAR_PRICES_INPUTS.md) and [source validation](../../docs/EF1_REGULAR_BAR_PRICES_IO.md). No observed-source admission or release acceptance is implied.

Money flow and retracement level use `equity_feature_duckdb.money_flow` (nullable OHLCV `bars` role, slot coverage, config builder) and `equity_feature_duckdb.retracement` (two exact-extremum REFERENCE roles, `x1:` id encoder, config builder) with original M01 to M36 and T01 to T32 synthetic requests. See [API](../../docs/api/EF2_MONEY_FLOW_RETRACEMENT_INPUTS.md) and [source checkpoint](../../docs/EF2_MONEY_FLOW_RETRACEMENT_IO.md). All mathematics remains outside the adapter.

Momentum and trend (MACD, DMI/ADX, stochastic and Williams %R) use `equity_feature_duckdb.momentum`: a nullable OHLCV `bars` role, slot coverage, a family config builder and original synthetic requests keyed by the contract's 100 result fixture ids. See [API](../../docs/api/EF2_MOMENTUM_INPUTS.md) and [source checkpoint](../../docs/EF2_MOMENTUM_IO.md). All mathematics remains outside the adapter.

Ichimoku and price channels (Ichimoku, Keltner, Donchian, pivots, band-width percentile, Bollinger/Keltner squeeze) use `equity_feature_duckdb.channels`: a nullable OHLCV `bars` role (one chunk per governed session), slot coverage, a producer config builder and original synthetic requests keyed by the contract's 74 result fixture ids. See [API](../../docs/api/EF2_CHANNELS_INPUTS.md) and [source checkpoint](../../docs/EF2_CHANNELS_IO.md). All mathematics remains outside the adapter.

Relative statistics, daily log volatility and realized variance use `equity_feature_duckdb.relative_rv`: close-only daily roles and an OHLCV `bars` role on a local governed grid, and the three producer configuration envelopes. See [API](../../docs/api/EF3_RELATIVE_RV_INPUTS.md) and [source checkpoint](../../docs/EF3_RELATIVE_RV_IO.md). All mathematics remains outside the adapter.

Path efficiency and choppiness use `equity_feature_duckdb.path_efficiency`: a nullable OHLCV `bars` role per session chunk, the closed `ef4.path_efficiency` config builder over the R17 context and the seven output ids. See [API](../../docs/api/EF4_PATH_EFFICIENCY_INPUTS.md) and [source checkpoint](../../docs/EF4_PATH_EFFICIENCY_IO.md). All mathematics remains outside the adapter.

Multi-venue status uses `equity_feature_duckdb.venue_status`: five nullable population/seed/states/prefix/validity slots, lossless supplied rows, the `vp1`/`vs1`/`v1`/`vc1` id encoders, a config builder and original MV01 to MV44 synthetic requests. See [API](../../docs/api/EF1_VENUE_STATUS_INPUTS.md) and [source checkpoint](../../docs/EF1_VENUE_STATUS_IO.md). Population, precedence, counts and clocks remain outside the adapter.

Close reconciliation uses `equity_feature_duckdb.reference_close`: four nullable calendar/bars/population-proof/authoritative-close slots, lossless supplied cells, the `k1:` id encoder, a config builder and original C01 to C03 synthetic requests. See [API](../../docs/api/EF1_REFERENCE_CLOSE_INPUTS.md) and [source checkpoint](../../docs/EF1_CLOSE_RECONCILIATION_IO.md). BPS, tolerance and close selection remain outside the adapter.

Regular first eligible trade price uses `equity_feature_duckdb.regular_first_trade_price`: three nullable calendar/trades/population-proof slots, lossless supplied cells and original R001/R019 synthetic requests. See [API](../../docs/api/EF1_REGULAR_FIRST_TRADE_PRICE_INPUTS.md) and [source checks](../../docs/EF1_REGULAR_FIRST_TRADE_PRICE_IO.md). Proof generation, firstness and price mathematics remain outside the adapter. Composition, observed-source and release acceptance are separately gated.

EF5 price structures: `equity_feature_duckdb.price_structures` maps supplied bars to the candle, structure and technical producers (no mathematics; see docs/EF5_PRICE_STRUCTURES_IO.md).
