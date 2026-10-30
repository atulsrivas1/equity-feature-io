## Unreleased - header cross-check against the catalogue (S5, RL-01-11)

Internal, synthetic, pre-release. New `tools/check_header_crosscheck.py` compares the catalogue output-view `algorithm_version` of every producer (32) with what the io code (and, with `--workers-root`, the workers code) declares as string literals; each mismatch is listed with file and line, and producers whose code does not state identity and version together are listed as NOT_DECLARED, never as OK. Result on io main 0dbe5f5 and workers main 1df482e: no mismatch; io OK 20, NOT_DECLARED 12; workers OK 10, NOT_DECLARED 22. Feature ids, dtype, unit and schema_version are not stated as literals next to the identities in the code and are not compared. `docs/contracts/IO_V1.md` gains one cross-reference line (no change to any rule, golden or hash; `tools/check_io_spec.py` passed before and after). No package change, no version bump, no catalogue file change.

## Unreleased - catalogue link layer in the io adapter API pages (S4 io part, RL-01-10)

Internal, synthetic, pre-release. Each of the 13 adapter API pages under `docs/api/` gains a "Contract catalogue" section linking every producer it covers (32 producers, EF1 to EF5) to its generated input and output catalogue pages, plus the catalogue INDEX and CATALOGUE.md. Docs only: no code, no catalogue file, no version change. The workers docs links are a separate change in the workers repository.

## Unreleased - catalogue families EF2 and EF1 (S2, RL-01-09)

Internal, synthetic, pre-release. The generated contract catalogue gains the frozen EF2 core contracts and the two frozen EF1 core contracts that have a producer table: 11 producers, 50 feature ids, 130 files in all (was 86). Producers touched (new): ef2.ichimoku, ef2.keltner, ef2.donchian, ef2.pivot_levels, ef2.band_width_percentile, ef2.bollinger_keltner_squeeze, intraday.momentum.v1, ef2.money_flow, ef2.retracement_level, ef1.reference_close, ef1.multivenue_status. The 21 EF3, EF4 and EF5 producer pages are unchanged byte for byte; only `index.json` and `INDEX.md` change besides the new pages. The EF1 and EF2 core files each use their own layout, so each gets one extraction map in the new `tools/catalogue_maps.py` (rename and regroup only; the generator gains a `map` hook, a per-producer adapter module and a "not catalogued" list). Unparsed keys: none. EF1 is partly present: `docs/ef1/CONTRACT.json`, `OBSERVABLE_CONTRACT_PROPOSAL.json`, `PATH_CONTRACT_PROPOSAL.json`, `PERIOD_PHASE_CONTRACT_PROPOSAL.json` and `REFERENCE_CONTRACT_PROPOSAL.json` state `proposed_not_frozen` and have no role or producer table; they are listed in `INDEX.md` and `index.json`, not extracted (PO to accept in writing or schedule). `check_input` now compares kinds without regard to case (core writes some in capitals) and judges no roles for a producer whose core file states none (the six ef2 channel producers). Package version: no bump (catalogue version stays 0.1.0a6; the coordinator assigns the next). Core contract bytes untouched.

## Unreleased - structural checks check_input and check_output (S8, RL-01-08)

Internal, synthetic, pre-release. `equity_feature_io_contracts.catalogue` gains `check_input(producer_id, roles)` and `check_output(producer_id, headers, reasons=())`, with result types `CheckResult` and `Finding` and the error `UnknownProducer`. They are structural checks only: roles, kinds and nullability against the input view; feature ids, header fields and reason names against the output view. They never look at values, never compute and never replace a library refusal; each finding cites the catalogue rule (`input.role.unknown`, `input.role.kind`, `input.role.required`, `output.header.field`, `output.feature_id.unknown`, `output.feature_id.duplicate`, `output.header.value`, `output.quality.reason`) and the catalogue page. The module imports only the standard library and the packaged data. Producers touched: none; the generated catalogue data are unchanged byte for byte. Package version: no bump in this PR (bump order S6, CV2, CAT-DV1 per RELEASE-MAP). Copy-paste example: [docs/contracts/CATALOGUE.md](docs/contracts/CATALOGUE.md).
## Unreleased - io-contracts 0.1.0a6 (first of the planned S6, CV2, CAT-DV1 bumps)

Internal, synthetic, pre-release. New version string: `equity-feature-io-contracts` 0.1.0a6 (prerelease bump from 0.1.0a5, as announced for RL-01-07 in #68; bump order S6, then CV2, then CAT-DV1). Moved together: `tools/_versions.py`, the io-contracts `pyproject.toml`, `__version__`, the README catalogue heading, the pins `equity-feature-io-contracts==0.1.0a6` in io-sdk and acquisition (their own versions stay, pin-only) and `tests/probe_foundation.py`. The catalogue version is the package version, so the generated data moved with `tools/gen_contract_catalogue.py` (`docs/contracts/catalogue/` and the packaged copy: `index.json` and `INDEX.md` only; the 21 producers and their contract versions are unchanged). Canonical core pins stay contracts 0.0.4a6, features 0.0.4a7, evidence 0.1.0a4. Downstream pins in equity-feature-workers follow in a separate re-pin PR. No tag, no publish.

## Unreleased - catalogue lookups in io-contracts (S6 part 2, RL-01-07)

Internal, synthetic, pre-release. New module `equity_feature_io_contracts.catalogue` with `producers()`, `by_feature_id(feature_id)` and `version()` over the packaged catalogue data (catalogue rulings A and G). Producers touched: none; the generated catalogue data (21 producers, EF3, EF4, EF5) are unchanged byte for byte. The module imports only the standard library and the packaged data, no core or workers code (ruling J). Package version: no bump in this PR; a minor pre-release bump is announced here and the coordinator assigns the version string (a bump also moves the catalogue version in the generated data, which is regenerated with `tools/gen_contract_catalogue.py`, never hand-edited). Format and use: [docs/contracts/CATALOGUE.md](docs/contracts/CATALOGUE.md).

Verified: wheel built from `packages/io-contracts` and installed with `--no-deps` into a fresh venv over core contracts 0.0.4a4 (local checkout), run isolated (`python -I`) from outside the repo: 21 producers, `by_feature_id("tape.window.count")` is `ef4.tape_window_sign`, `version()` is `0.1.0a5` with 21 producer versions, an unknown id raises `UnknownFeatureId`. `mypy --strict` clean on the module. `tools/verify_versions.py` OK. `tools/check_contract_catalogue.py` OK (86 files, docs == package == regeneration from core origin/main, unparsed keys none). `tools/check_extraction.py` exit 0. Core `check_boundary.py` passes; frozen core bytes untouched (no core change). Windows, CPython 3.12.10.

Not verified: no Linux run; the installed check used core contracts 0.0.4a4, not the a6 pin (the a6 wheel was not built locally); no hosted CI (none by decision); the a5 to next-version bump itself (coordinator).

## Unreleased - coordinated pre-release bump DV1-4 (I3): contracts 0.0.4a6, features 0.0.4a7

Internal, synthetic, pre-release. io-contracts 0.1.0a5 (canonical package constant and the packaged catalogue version string), bundles 0.1.0a3 (admission versions), duckdb 0.1.0a12 (adapter stamp); pins on core contracts 0.0.4a6, features 0.0.4a7, evidence 0.1.0a4 (bundles, duckdb, io-contracts, examples); io-sdk, acquisition, files, duckdb-sink and parquet keep their versions (pin-only). Version labels moved and digests changed by construction; numeric results unchanged. `session.price.range_over_open` joins every bar and trade output list that enumerates the `session.price` outputs. Record: [docs/PRERELEASE_BUMP_DV1.md](docs/PRERELEASE_BUMP_DV1.md).

## Unreleased - contract catalogue S1 (EF3, EF4, EF5) and io-contracts 0.1.0a4

Internal, synthetic, pre-release. New generated catalogue of the per-producer input and output views, schema `ef-contract-catalogue1`, at `docs/contracts/catalogue/` and as packaged data in `equity-feature-io-contracts` 0.1.0a4 (prerelease bump from 0.1.0a3; the catalogue version is the package version). Format and use: [docs/contracts/CATALOGUE.md](docs/contracts/CATALOGUE.md). Authority: core frozen contract; on conflict core wins and the gate fails. Tools: `tools/gen_contract_catalogue.py` (writes both copies from core), `tools/check_contract_catalogue.py` (one drift gate: docs copy == package data == regeneration from core), `tools/verify_contract_catalogue.py` (wording, markers, provenance, no provider names). Producers touched (21, 126 feature ids): ef3.relative_stats, ef3.daily_log_volatility, ef3.intraday_realized_variance, ef3.robust_history, ef3.volume_pace_robust, ef3.volume_ratio_mean, ef3.session_breadth, ef3.observed_breadth, ef3.adaptive_volume, ef4.tape_window_sign, ef4.trade_top_k_notional, ef4.quote_dynamics, ef4.vwap_path, ef4.path_efficiency, ef4.session_projection, ef4.bar_projection, ef4.relative_excess, ef4.rate_projection, ef5.candle, ef5.structure, ef5.technical. EF1 and EF2 are not present yet. No Python lookup module ships in this version. Pins that follow: io-sdk and acquisition now require `equity-feature-io-contracts==0.1.0a4` (their own versions are unchanged). No tracked EF1 source file changed; no tag, no publish.

## Unreleased - builder retirement

`tools/build_duckdb.py` is retired (the adapter moved out of core); `tools/build_matrix.py` is deferred. See docs/RETIRED_BUILDERS.md.

## Unreleased - coordinated pre-release bump for the EF5 layers

duckdb 0.1.0a11 (EF5 price_structures adapter). Record: [docs/PRERELEASE_BUMP_EF5.md](docs/PRERELEASE_BUMP_EF5.md).

## Unreleased - EF4 C3: recorded Parquet round trip for notional cells

`tools/verify_ef4_notional_cells.py` now also publishes a `tape.top_k_notional` result through `ParquetSink`, reads it back, and checks the stored `cells.parquet` cell wire and `evidence.parquet` rows are in notional order (a, b, c; size order would be b, a, c). Run on io main `106897a` with core main `3af2d99`, CPython 3.12.10, pyarrow 20.0.0, Windows: OK. Tool only; no package source changed.

## Unreleased - EF5 supplied price-structure inputs (candle, structure, technical)

`equity_feature_duckdb.price_structures` maps supplied bars to the EF5 `bars` role and builds the closed `ef5.*` configuration envelopes with no defaults; rows without declared coverage are refused at the adapter (E2). Gate `tools/verify_ef5_io.py`: 89 result fixtures and 59 refusals match the contract. Notes: [docs/EF5_PRICE_STRUCTURES_IO.md](docs/EF5_PRICE_STRUCTURES_IO.md). No package version bump.

## Unreleased - Compatibility note: notional cells under the same version string

Bundles written under the same version string can now hold notional cells (`tape.top_k_notional`); the bundles typed decoder and the io-sdk codec accept them. The older bundles typed decoder refuses such a bundle fail-closed with `invalid_order`. (The old io-sdk codec before io #54 decoded notional cells through an `object.__new__` workaround, so this refusal is the typed decoder only.) Bundles written before this change are internal and regenerable; no cross-version read is promised. Full `write_bundle` archives are locked by `shape()` to `session.compute_trades.v1` and cannot carry `tape.top_k_notional` results: only the typed decoder accepts notional cells. Documented EF4 limit (carried as a C-item): in the equity-feature-workers remote client, `convert_result` refuses a notional cell with `Failure(contract, invalid_conversion)` because `_cell` rebuilds `TopKTrades` with the default size ranking and has no feature id (it fails closed); the service codec decode path is not tested. This blocks the EF5 workers layer merge until the decode path carries feature context, or EF5 documents the same limit with an owner-visible note. A coordinated version bump is mandatory before EF4 is ACCEPTED.

## Unreleased - EF4 PO rulings E1 and E2: notional top-K cells and fail-closed tape coverage

The bundles typed decoder and the io-sdk codec rebuild `tape.top_k_notional` cells through the public rank-aware `TopKTrades(k, rows, ranking="notional")` constructor of core (the `object.__new__` workaround in the io-sdk codec is removed; the bundles decoder no longer refuses notional cells). Only that feature id is notional ranked; every other TopKTrades feature keeps the size rank. The tape adapter no longer defaults a missing `TradeSupply.coverage` to complete: rows without coverage keep `INVALID_SCHEMA` (io #51), no rows without coverage is `INVALID_CONFIG`. `tools/verify_ef4_notional_cells.py` records the bundles, codec and Arrow round trip. Package versions and `_versions.py` are unchanged (coordinated a5 bump is a separate change).

## Unreleased - coordinated pre-release bump for contracts 0.0.4a5 and features 0.0.4a6

io-contracts 0.1.0a3, io-sdk 0.1.0a3, bundles 0.1.0a2, duckdb 0.1.0a10, duckdb-sink 0.1.0a1 and parquet 0.1.0a2 (plus the two example packages); acquisition and files follow the pins. The canonical package version is one constant in io-contracts; versions for tools and tests come from `tools/_versions.py`, checked by `tools/verify_versions.py`. Goldens that embed versions are regenerated with version-only differences (hashes in [docs/PRERELEASE_BUMP_A5_A6.md](docs/PRERELEASE_BUMP_A5_A6.md)). Bundles written under bundles 0.1.0a1 are internal and regenerable; no cross-version reads are promised. No tag, no publish.

## Unreleased - EF3 adapters carry per-fact known_at (R5 end to end)

The EF3 D/E/F supplied-input adapters no longer default `known_at` (`KNOWN_AT_DEFAULT`, `ka` falling back to the event time are removed): each fact carries the value supplied for it, null when absent (the library reports `unknown_availability`), and a malformed value is a typed `INVALID_SCHEMA` refusal. Namespace, population id, record-set id and session identity are explicit parameters (`Frame` in `breadth_adaptive`, `namespace`/`population_id` elsewhere); the `SYN` values remain only as documented demo defaults. Breaking for callers that relied on the old defaults (including `relative_rv.close_batch`/`intraday_batch` `known_default`, now `None` instead of 50, and `Cell.known_at` is validated in `daily_batch`/`bars_batch`): pass `known_at` explicitly (`session(bounds_known_at=)`, `parse_cell(token, known_at=)`, `grid_batch(known_at=)`, `population_batch(known_at=)`, row `ka`). The 36 core E-A2 fixtures (KA01 to KA48) run through the builders with 0 differences.

## Unreleased - EF4-H supplied quote dynamics and VWAP path I/O

Adds the quote, trade, bar, declared-gap, grid, prepared-proof and bounds roles with explicit coverage declarations, and request assembly for ef4.quote_dynamics (ef4-quote1) and ef4.vwap_path (ef4-vwap1) under EQ-159 and EQ-160. Original fixture-derived requests cover all 69 result and 80 refusal contract fixture ids through a scratch runner; the 69 joint results round-trip through the DuckDB sink. See [API](docs/api/EF4_QUOTE_VWAP_INPUTS.md) and [source checkpoint](docs/EF4_QUOTE_VWAP_IO.md). No quote, spread, microprice, VWAP, slope or extremum mathematics, observed-source admission, sink/SDK/version change or release acceptance.
## Unreleased - EF4-G supplied tape trades and notional top-K I/O

Adds the TRADE, optional `ef4.tick.seed` REFERENCE and notional top-K partition roles and the configuration envelopes for `ef4.tape_window_sign` (`ef4-tape1`) and `ef4.trade_top_k_notional` (`ef4-notional1`) under EQ-158 and EQ-162. The io-sdk codec reads a stored notional-ordered top-K cell from its fields when the size-ranked constructor refuses it (`INVALID_ORDER`); other cells keep the constructor path. All 82 result fixtures under two identity bindings and G01 to G03 round-trip through the DuckDB sink (227 of 227 results); 73 of 75 refusal recipes raise the contract code. See [API](docs/api/EF4_TAPE_INPUTS.md) and [source checkpoint](docs/EF4_TAPE_IO.md). No tick, window, notional or rank mathematics, no worker, no release acceptance and no package version change.
## Unreleased - EF4 supplied projections I/O (EQ-172)

Adds the supplied-input adapter for the EF4 I2 projections (`ef4-proj1`, `ef4-rel1`, `ef4-rate1`): session and bar projections, relative excess and rate projection, mapped to canonical batches and the core builders under EF4-IO #613. All 111 result fixtures round trip through the DuckDB sink; all 114 refusal recipes raise the recorded code. See [source checkpoint](docs/EF4_PROJECTIONS_IO.md). No mathematics or version change.

## Unreleased - EF3 supplied breadth and adaptive volume I/O

Adds the nine declared, four observed and one adaptive nullable REFERENCE roles and the configuration envelopes for `ef3.session_breadth` (`ef3-breadth1`), `ef3.observed_breadth` (`ef3-obsbreadth1`) and `ef3.adaptive_volume` (`ef3-adaptive1`) under EF3-IO #611. Original fixture-derived requests cover all 99 result, 7 prefix and 62 refusal contract fixture ids through a scratch harness. See [API](docs/api/EF3_BREADTH_ADAPTIVE_INPUTS.md) and [source checkpoint](docs/EF3_BREADTH_ADAPTIVE_IO.md). No count, ratio, proximity, rate, rank or float mathematics, observed-source admission, sink/SDK/version change or release acceptance.

## Unreleased - EF3 supplied robust-history, volume-pace and mean-ratio I/O

Adds the nullable `series`, `sessions`, `population`, `cohort_values`, `grid` and `bars` roles and the configuration envelopes for `ef3.robust_history` (`ef3-robust1`), `ef3.volume_pace_robust` (`ef3-pace1`) and `ef3.volume_ratio_mean` (`ef3-mean1`) under EF3-IO #611. Original fixture-derived requests cover all 124 result and 48 refusal contract fixture ids through a scratch harness. See [API](docs/api/EF3_ROBUST_PACE_INPUTS.md) and [source checkpoint](docs/EF3_ROBUST_PACE_IO.md). No median, MAD, quantile, rank, ratio, z-score or mean mathematics, observed-source admission, sink/SDK/version change or release acceptance. Also corrects the declared digest of `relative_rv.py` in `EF1_SOURCE_EVOLUTION.json`.

## Unreleased - EF1 supplied regular first-trade I/O

Adds exact three nullable roles, lossless supplied TRADE/REFERENCE conversion and original synthetic R001/R019 requests under EQ212#570. See [API](docs/api/EF1_REGULAR_FIRST_TRADE_PRICE_INPUTS.md) and [source checkpoint](docs/EF1_REGULAR_FIRST_TRADE_PRICE_IO.md). No producer mathematics, observed-source admission, sink/SDK/schema/version change or release acceptance.

## Unreleased - EF1 supplied gap endpoint I/O

Adds four nullable source roles, lossless supplied proof/row conversion and explicit original synthetic trade/bar helpers under EQ212 #570. See [API](docs/api/EF1_GAP_ENDPOINT_INPUTS.md) and [source validation](docs/EF1_GAP_ENDPOINT_IO.md). No observed-source, installed-artifact or release acceptance. Existing generic SDK/sink schemas and versions unchanged.

## EQ098 bundles0.1.0a1 candidate — October15,2026

New packages/bundles implements the canonical reviewed data-only bundle and explicit trusted replay contract, with no extraction/source/resolver/code hooks. [API/format/limits](packages/bundles/README.md), [actual synthetic consumer](examples/bundles_consumer.py), [fixed dependency qualification](tools/build_bundles.py). Source candidate only; current bothOS/freshforms/paired-main delivery and canonical198 acceptance remain pending. Existing I/O packages and unrelated provider drafts15/16 unchanged.

# BUG-005 — Parquet 0.1.0a1 under qualification

Correct completion/reservation observation during cooperating first-publication and retries; preserve stable corruption detection, replay/conflicts and storage/math formats. Canonical issue301 records review/CI/install/current-main delivery; no completion claimed by this source note. Other component versions unchanged. Matrix repeat-build equality remains required for unchanged distributions; changed Parquet archives receive fresh qualification, not historical .a0 hash claims.

# Changelog

## Unreleased - EF4 supplied path-efficiency and choppiness I/O

Adds the nullable `bars` role (OHLCV or close-only, one chunk per actual session), a closed `ef4.path_efficiency` configuration builder over the R17 context (`ef4-path1`, `ef4-path-efficiency-v1`) with the N <= 63 cap of `governed_history` and the reset/carry mode pairing, and an example. See [API](docs/api/EF4_PATH_EFFICIENCY_INPUTS.md) and [source checkpoint](docs/EF4_PATH_EFFICIENCY_IO.md). No efficiency, log, true-range or choppiness mathematics, observed-source admission, sink/SDK/version change or release acceptance.

## Unreleased - EF3 supplied relative-statistics, daily log-volatility and realized-variance I/O

Adds the close-only daily roles (`instrument`, `benchmark`, `daily`) and the regular-session OHLCV `bars` role on a local governed grid, and the configuration envelopes for `ef3.relative_stats` (`ef3-rel1`), `ef3.daily_log_volatility` (`ef3-dlv1`) and `ef3.intraday_realized_variance` (`ef3-rv1`) under EF3-IO #611. Original fixture-derived requests cover all 62 result, 3 prefix and 48 refusal contract fixture ids through a scratch harness. See [API](docs/api/EF3_RELATIVE_RV_INPUTS.md) and [source checkpoint](docs/EF3_RELATIVE_RV_IO.md). No return, beta, correlation, logarithm, variance or annualization mathematics, observed-source admission, sink/SDK/version change or release acceptance.

## Unreleased - EF2 supplied Ichimoku and price-channel I/O

Adds the nullable `bars` role (OHLCV, one chunk per governed session), config builder for `ef2.<producer>` (`ef2-channels-v1`) and original synthetic requests keyed by all 74 contract result fixture ids (including ICH-17 and the prefix fixtures) under EF2-IO #609. See [API](docs/api/EF2_CHANNELS_INPUTS.md) and [source checkpoint](docs/EF2_CHANNELS_IO.md). No indicator mathematics, observed-source admission, sink/SDK/version change or release acceptance.

## Unreleased - EF2 supplied momentum and trend I/O

Adds the nullable `bars` role (OHLCV, one chunk per actual session), config builder for `intraday.momentum.v1` (`ef2-conv1`) and original synthetic requests keyed by all 100 contract result fixture ids (including D04 with Amendment 1 prices, D22 and the prefix fixtures P01 to P03) under EF2-IO #609. See [API](docs/api/EF2_MOMENTUM_INPUTS.md) and [source checkpoint](docs/EF2_MOMENTUM_IO.md). No indicator mathematics, observed-source admission, sink/SDK/version change or release acceptance.

## Unreleased - EF2 supplied money-flow and retracement I/O

Adds the nullable `bars` role (OHLCV with volume), the two nullable exact-extremum REFERENCE roles, id encoder, config builders and original synthetic M01..M36 and T01..T32 requests under EF2-IO #609. See [API](docs/api/EF2_MONEY_FLOW_RETRACEMENT_INPUTS.md) and [source checkpoint](docs/EF2_MONEY_FLOW_RETRACEMENT_IO.md). No indicator or retracement mathematics, observed-source admission, sink/SDK/version change or release acceptance.

## Unreleased - EF1 supplied multi-venue status I/O

Adds exact five nullable roles, lossless venue-row conversion, the four reference-id encoders, config builder and original synthetic MV01 to MV44 requests under EQ212#570 for EQ165#505. See [API](docs/api/EF1_VENUE_STATUS_INPUTS.md) and [source checkpoint](docs/EF1_VENUE_STATUS_IO.md). No population, precedence, count or clock mathematics, sink/SDK/schema/version change or release acceptance.

## Unreleased - EF1 supplied close-reconciliation I/O

Adds exact four nullable roles, lossless authoritative-close conversion, the reference-id encoder, config builder and original synthetic C01 to C03 requests under EQ212#570 for EQ168#508. See [API](docs/api/EF1_REFERENCE_CLOSE_INPUTS.md) and [source checkpoint](docs/EF1_CLOSE_RECONCILIATION_IO.md). No BPS or comparison mathematics, sink/SDK/schema/version change or release acceptance.

## 0.1.0a0 — EQ121, unreleased foundations

Typed independently buildable foundation packages, inward metadata dependencies, canonical issue authority and repeat-build/fresh-form checks. Version markers only; no formulas, acquisition, sink publication, factory registration or worker commands. Actual delivery acceptance is linked from canonical EQ121 after publication.

## DuckDB0.1.0a8 — EQ122, unreleased extraction

Existing distribution/import/API/source behavior preserved; adapter/receipt implementation stamp and repository metadata updated. Source/evidence precision/availability/R4 limitations remain unchanged. Actual reviewed installed/native/main publication gates under canonical279.

EQ098 corrected candidate qualification: both OS current artifacts/four fresh forms/29-method cohorts independently audited; final publication remains gated. Full maps: canonical docs/stories/EQ-098_VALIDATION.json. Both source P2 findings and delivery-tooling corrections retained.

## Unreleased — EF1 anchor I/O source authoring

- Adds the reviewed clock subset's actual c1 calendar-provenance REFERENCE
  factory, explicit source/missing packet and original small C01 fixture;
  independent mapping and prospective clock-to-existing-sink checks are authored,
  unexecuted. Existing anchor scope and unreleased adaptera9 are retained.

- EQ212 adds explicit canonical anchor-provenance mapping, labelled original
  synthetic trade/actual-notional-bar fixtures and source/output alias refusal.
- Adds unexecuted independent anchor input/composition/readback checks and an
  explicit existing-sink publication example. No source DB acquisition, feature
  math or sink codec changes are claimed. New source candidate0.1.0a9 is distinct
  from accepted a8 artifacts; coordinated build/CI and qualification remain pending.

## Unreleased — EF1 supplied current-state status source authoring

- Adds exact canonical state/certificate conversion, explicit four-position
  StatusInputs with per-role provenance and original S01/S02/S03 synthetic helpers.
  Unknown/future knowledge, partial missingness and covered-empty populations stay
  explicit; no status inference, source acquisition or adapter calculations.
- Authors independent direct library composition, literal quality/witness fixtures
  and existing-sink full canonical readback/replay checks. Source only: no local
  execution under EQ142, no numerical/artifact/release acceptance claimed.
- Existing anchor/clock behavior, versions, original19 guards and sink codecs are
  preserved. See docs/api/EF1_STATUS_INPUTS.md; full EF1 audit/residual gates remain.

### EF1 sampled path source authoring — unreleased

- Add present-only gap/drive input packets, explicit DAILY prior converter and
  original public synthetic G01/G02/G03/D01 fixtures/context against the reviewed
  frozen amendment. Supplied fields, coverage and knowledge remain original.
- Author independent literal result and full-result existing-sink readback tests;
  no local execution under the protected EQ142 study reservation.
- Carry forward the coordinator's inherited status-fixture tuple type annotation
  correction; no status source values or numerical behavior changed.
- No schema/version/codec change, private-source qualification, legacy numerical
  parity, completed full EF1 audit or release claim.

EF1 source candidate (unreleased): exact nullable supplied classification/action input roles, retained original reference proof conversion, synthetic R01/R02/R03 fixtures and prospective full-result sink cases. Runtime qualification pending; package versions unchanged.

## EF1 daily observations source candidate — October21,2026

EQ212 supporting EQ166 adds lossless six-slot daily REFERENCE transport, explicit provenance and original synthetic fixed252/current-week/latest-prior examples. [API and limits](docs/EF1_DAILY_OBSERVATIONS_IO.md). Legacy DAILY/BAR, SDK/sink/codec and package versions remain unchanged. Full source qualification, independent review, integrated runtime/artifact/browser/release gates remain open.

## Unreleased - EF1 supplied regular completed-BAR prices

Adds lossless three-role supplied BAR/proof conversion, per-role provenance and original synthetic R01/R08 examples under EQ212 #570. [API](docs/api/EF1_REGULAR_BAR_PRICES_INPUTS.md) and [author evidence](docs/EF1_REGULAR_BAR_PRICES_IO.md). Existing SDK/sink schemas, versions and old producers remain unchanged; full EF1 release gates remain open.
