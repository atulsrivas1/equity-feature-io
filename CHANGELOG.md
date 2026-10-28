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
