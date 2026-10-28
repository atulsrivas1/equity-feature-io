# Coordinated pre-release bump: contracts a5, features a6 - October 28, 2026

Paired with the core PR (`docs/PRERELEASE_BUMP_A5_A6.md` there). Pre-release label move only: no tag, no publish, no release claim
(PO ruling `work/po-rulings-e1e2-followups-2026-10-28.md` item 1).

## Single source

`tools/_versions.py` is the table of versions for this repository's tools, tests and examples; `tools/verify_versions.py`
fails if any live place disagrees (package versions and exact pins, `__version__` constants, the duckdb adapter stamp, the
canonical-package constant `equity_feature_io_contracts.factories.CANONICAL_PACKAGE_VERSION`, and the bundles admission module
`packages/bundles/src/equity_feature_bundles/_versions.py`). The sinks and the SDK import the canonical constant from io-contracts
instead of repeating `"0.0.4a4"`. The two standalone example packages keep the literal on purpose (a third party declares what it supports).

## Packages moved (content changed since the last bump of that package)

| Package | From | To | Why |
| --- | --- | --- | --- |
| equity-feature-io-contracts | 0.1.0a2 | 0.1.0a3 | canonical package constant moved to the new contracts version |
| equity-feature-io-sdk | 0.1.0a2 | 0.1.0a3 | notional cells (#54), tape adapter (#41), publication fixes since the a2 bump; canonical constant |
| equity-feature-bundles | 0.1.0a1 | 0.1.0a2 | notional cells (#54), admitted versions (now core evidence 0.1.0a3 too); this is the version the compatibility note refers to |
| equity-feature-duckdb | 0.1.0a9 | 0.1.0a10 | 33 source commits since the a9 bump (EF2 to EF4 adapters, fail-closed fixes) |
| equity-feature-duckdb-sink | 0.1.0a0 | 0.1.0a1 | canonical constant, pins |
| equity-feature-parquet | 0.1.0a1 | 0.1.0a2 | canonical constant, pins |
| equity-feature-example-extensions (example) | 0.1.0a0 | 0.1.0a1 | declared canonical version |
| equity-feature-factory-fixture (example) | 0.1.0a1 | 0.1.0a2 | declared canonical version |

acquisition and files change only their exact pins on io-contracts and io-sdk and keep their versions.

## Regenerated golden fixtures (version-derived fields only)

Method as in #46: labels substituted, digests recomputed with hashlib (the publication goldens: `idempotency_key` is
SHA-256 of `efio-key1` NUL plus the identity JSON; the bundle oracle: member bytes with substituted labels, content and receipt
digests re-derived, ZIP re-packed by the test's stdlib packer, which was first checked to reproduce the old archive). The
`tests/ef1` packet files are byte-identical copies of the core oracles (same SHA-256 in core, io and workers).

| File | SHA-256 before | SHA-256 after |
| --- | --- | --- |
| `docs/EF1_SOURCE_EVOLUTION.json` | `bc8df4be02ac94c80888580641d5bed429793853a6381beec9d7e48f41104fa8` | `9f7679fc3790982c3cf8285b2bc4cd0ff47dfc2f8551bb78c9e03bec6895ba7b` |
| `tests/ef1/daily_observations_contract_packets.json` | `479948037cd6d2fca3901cdb9cf3fcbba6256acbbcb9440bcd68e0362d7688c5` | `eab22b6e2f5adf82e0437f1d3aaf845d4d4dcd66e5a561600a2ccb9172573ff2` |
| `tests/ef1/gap_endpoint_causal_contract_packets.json` | `698994acf9d324d3c94334b02f307b2997ce320eb397d7f7cb5f8ea359d4f239` | `ded050dc98f29a45d9f4bcbb47a3b3c0e415e93f381282500b3f1f8c72a1a0b5` |
| `tests/ef1/gap_endpoint_contract_packets.json` | `751cd98fd7951aa7c2d4394d9a5fee87e184d9d484d9f43d4de4983b7333f40f` | `ca32e6c890697a09d1ba6450748085a4b03d2bff2eb8e711d8c79371289aede3` |
| `tests/ef1/observable_contract_packets.json` | `d0fb7b4fafc2b824e8998dbf10c7f27d8443fdb1218be7588c674002a2dcfc3c` | `1b7c4190290071c9469cf4ef4176019189b310c716d32c5102c2968eb2b6c539` |
| `tests/ef1/observable_publication_packets.json` | `646e402e321eb97a171a2f8f64ce3c1ee399f7bcb81906fd929be4e6477170a6` | `8404a1871c7841abbca8551e6c6b31e52dc3c4fd0a16eefead826d38bac9c3aa` |
| `tests/ef1/period_phase_contract_packets.json` | `b4c78f03b3c1ec5100740803d4b853920f9aa28cb58d73446dea6b3f403db09c` | `298851f79f26da042fada31163c8384eb497f9769d9c3b38b1f51128ec8f93be` |
| `tests/ef1/reference_contract_packets.json` | `5160d91fc966137a1728c6c26dde15d6772ea35811efc4ea9832b2f7460a28f0` | `5b751632a5dba5bf53ac59cbf9602124ff2fb8f50e423a80f84a5346c107fa4e` |
| `tests/ef1/regular_bar_prices_contract_packets.json` | `05d5b4815df3fd621993037c84f9d897a32ee84c833715e6ca1f6c4e1473d030` | `70fcaff8038d416f8cbc00340c7084fa106944c85a8e1ec4088d3b4b5149db96` |
| `tests/ef1/regular_first_trade_price_contract_packets.json` | `e1835d416a09bd65fce59612323d23c241fe81dcb8493170002e2c3eadffe531` | `e4cd2ec2f97c43012884a7676d7bb6b81e3643ecbe88ebccb9ac251f9bcd6a44` |
| `tests/ef1/regular_first_trade_price_fixture_manifest.json` | `385171c5bc1a1491fb0da6a652844f1e14138a5dc95db6325fbb6834c59f6060` | `aabe816abfe36921a6c08e4240a66c11e0e0e38401f495464cc935d66706024d` |
| `tests/fixtures/bundle_oracle.json` | `da0e1728ec670f080a5329240b78c7785af7e4aaa2e28df35dea391a7ce6ca38` | `bb6d45f64c8de4e826996080f3ab9c1b15a805d315c15da5af797a089ea2deb0` |
| `tests/publication_goldens.json` | `67525e9cf53e840d436841b683839c52550e324ee60171d1d84146146168eec7` | `e86e6aa87f6e7726b7efce2957b074d3ac031d42a79d81e1effe3d8b5eb65f4f` |

`tools/check_extraction.py` still holds: the duckdb version marker substitution is now `0.1.0a7` to `0.1.0a10` in
`docs/EF1_SOURCE_EVOLUTION.json` (the only source changes to retained files are those markers).
Commit-pinned builders (`tools/build_*.py` with commit constants) read versions from the table but still name pre-bump
commits; re-pin them to the merged heads before their next run. `tools/build_matrix.py` and `tests/matrix/accepted_archives.json`
describe the accepted archive matrix at fixed historical commits and are left unchanged.

## Repeat-build equality (checklist 1.3)

All 27 packages of the three repositories (12 core, 8 io plus 2 example packages, 5 workers) were built twice from fresh copies with `SOURCE_DATE_EPOCH=1700000000` and the pinned `build 1.2.2.post1` / `setuptools 80.9.0`: wheels are byte-equal and sdists are equal after the repository's own normalization (`tools/build_explanations.py normalize`), 27 of 27. Not a release build: no tag, no publish.

## BLOCKING follow-up: re-pin the commit-pinned builders

`tools/build_*.py` with commit constants read the table but still name pre-bump commits; they are NOT executed end to end. Re-pin after the
three PRs merge and before any release claim or end-to-end run (PO ruling 2026-10-28).
