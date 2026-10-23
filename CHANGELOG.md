## Unreleased - EF1 supplied regular first-trade I/O

Adds exact three nullable roles, lossless supplied TRADE/REFERENCE conversion and original synthetic R001/R019 requests under EQ212#570. See [API](docs/api/EF1_REGULAR_FIRST_TRADE_PRICE_INPUTS.md) and [source checkpoint](docs/EF1_REGULAR_FIRST_TRADE_PRICE_IO.md). No producer mathematics, observed-source admission, sink/SDK/schema/version change or release acceptance.

## Unreleased - EF1 supplied gap endpoint I/O

Adds four nullable source roles, lossless supplied proof/row conversion and explicit original synthetic trade/bar helpers under EQ212 #570. See [API](docs/api/EF1_GAP_ENDPOINT_INPUTS.md) and [source validation](docs/EF1_GAP_ENDPOINT_IO.md). No observed-source, installed-artifact or release acceptance. Existing generic SDK/sink schemas and versions unchanged.

## EQ098 bundles0.1.0a1 candidate — October15,2026

New packages/bundles implements the canonical reviewed data-only bundle and explicit trusted replay contract, with no extraction/source/resolver/code hooks. [API/format/limits](packages/bundles/README.md), [actual synthetic consumer](examples/bundles_consumer.py), [fixed dependency qualification](tools/build_bundles.py). Source candidate only; current bothOS/freshforms/paired-main delivery and canonical198 acceptance remain pending. Existing I/O packages and unrelated provider drafts15/16 unchanged.

# BUG-005 — Parquet 0.1.0a1 under qualification

Correct completion/reservation observation during cooperating first-publication and retries; preserve stable corruption detection, replay/conflicts and storage/math formats. Canonical issue301 records review/CI/install/current-main delivery; no completion claimed by this source note. Other component versions unchanged. Matrix repeat-build equality remains required for unchanged distributions; changed Parquet archives receive fresh qualification, not historical .a0 hash claims.

# Changelog

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
