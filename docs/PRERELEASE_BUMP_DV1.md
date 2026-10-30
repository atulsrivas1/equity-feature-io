# Coordinated pre-release bump DV1-4 (I3): contracts a5 to a6, features a6 to a7 - October 30, 2026

Paired with core #762 (merge commit 967d13df5cc080ef85c5bdeb96b1bca983836561, `docs/PRERELEASE_BUMP_DV1.md` there; PO rulings D2, D4, D5). Internal, synthetic, pre-release. Pre-release label move only: no tag, no publish, no release claim, no performance claim. Numeric results unchanged; version labels moved and digests changed by construction. The workers PR follows this one.

## Packages moved (this repository)

| Package | From | To | Why |
| --- | --- | --- | --- |
| equity-feature-io-contracts | 0.1.0a4 | 0.1.0a5 | canonical package constant `CANONICAL_PACKAGE_VERSION` moves to contracts 0.0.4a6; the packaged catalogue bytes carry the package version (regenerated: `index.json` and `INDEX.md` change in the version string only; D5) |
| equity-feature-bundles | 0.1.0a2 | 0.1.0a3 | `_versions.py` decides which contracts, evidence and features versions a bundle accepts, and the oracle archive, manifest and digests move (D4 allows pin-only only when no digest differs; the A5/A6 bump moved bundles for the same reason) |
| equity-feature-duckdb | 0.1.0a11 | 0.1.0a12 | `__version__` and the receipt `adapter_version` default; pin on contracts 0.0.4a6 |

Pin-only, versions unchanged (D4): io-sdk 0.1.0a3, acquisition 0.1.0a0, files 0.1.0a0, duckdb-sink 0.1.0a1, parquet 0.1.0a2 (the bundles pins and admission module `_versions.py` move to contracts a6, evidence a4, features a7; the bundle manifest `versions` block in the oracle carries them). Examples: third_party and factory_consumer declare canonical 0.0.4a6; `bundles_consumer.py` declares contracts a6, features a7.

Core pins: contracts 0.0.4a6, features 0.0.4a7, evidence 0.1.0a4 (`tools/_versions.py`, which `tools/verify_versions.py` checks against every pyproject, `__version__`, README pin, the canonical constant and the bundles admission module).

## Regenerated version-derived files

The nine `tests/ef1/*_packets.json` files are byte copies of the core files at 967d13d (identical SHA-256, checked against the core table). `tests/publication_goldens.json`: `canonical_package_version` 0.0.4a5 to 0.0.4a6 in each `key_ascii`, `idempotency_key` recomputed as SHA-256 of `efio-key1` NUL plus the identity JSON (old method first reproduced the four old keys; content SHA-256 unchanged). `tests/fixtures/bundle_oracle.json`: member labels substituted (`contracts_version`, `backend_version`, manifest `versions`), manifest `versions.bundle` 0.1.0a2 to 0.1.0a3, content digests recomputed (configuration, canonical batch `2f774eee...` equal to core's batch fingerprint, result, receipt, manifest), ZIP re-packed with the test's stdlib packer layout; `config_digest` is unchanged (65ca8bb1...). Pins in tests/ef1 supports and `tests/bundles/test_bundles.py` follow.

| File | SHA-256 before (main 1ac4d7e) | SHA-256 after |
| --- | --- | --- |
| `docs/EF1_SOURCE_EVOLUTION.json` | `48d00779f0b9c556df87543014fcc649cd4918157956f628f038d83d3509688d` | `47ad05a21c899c4baa0ac4f968fa39dc4da6141edda80120f7bed2233e75ba49` |
| `tests/ef1/daily_observations_contract_packets.json` | `eab22b6e2f5adf82e0437f1d3aaf845d4d4dcd66e5a561600a2ccb9172573ff2` | `50257a0d648809c7987ce49d710812afdd5f1ff6dd4ddf1c65c0fafb8c121f15` |
| `tests/ef1/gap_endpoint_causal_contract_packets.json` | `ded050dc98f29a45d9f4bcbb47a3b3c0e415e93f381282500b3f1f8c72a1a0b5` | `8ff3cce116c71dbe50c8e3e8d455dd4203acddfcc9604bbc092aa85e2ca2b781` |
| `tests/ef1/gap_endpoint_contract_packets.json` | `ca32e6c890697a09d1ba6450748085a4b03d2bff2eb8e711d8c79371289aede3` | `22d23e4c57fe1382c25b30aba50bde70eff002d85a9a4dc27f96b13df6b210b2` |
| `tests/ef1/observable_contract_packets.json` | `1b7c4190290071c9469cf4ef4176019189b310c716d32c5102c2968eb2b6c539` | `1d883a4d7d61593c0e8d9d2c8c0423933d07f3ff386e3775ccafe1aab0a0d2fd` |
| `tests/ef1/observable_publication_packets.json` | `8404a1871c7841abbca8551e6c6b31e52dc3c4fd0a16eefead826d38bac9c3aa` | `7e21d4eb997cd75c100d2f1da0af74fe59ed8d45262c470bdd9d5344443cd8b4` |
| `tests/ef1/period_phase_contract_packets.json` | `298851f79f26da042fada31163c8384eb497f9769d9c3b38b1f51128ec8f93be` | `81ac55769bdd21074aacf83c8df8955a501979d22e813ccfeba55b9e5e9f9204` |
| `tests/ef1/reference_contract_packets.json` | `5b751632a5dba5bf53ac59cbf9602124ff2fb8f50e423a80f84a5346c107fa4e` | `7eb97ec61eb1a945d39be9551c5937b3e86c7647d854b1aa507d0a8f32728a1d` |
| `tests/ef1/regular_bar_prices_contract_packets.json` | `70fcaff8038d416f8cbc00340c7084fa106944c85a8e1ec4088d3b4b5149db96` | `bd057b4042e1274ae46a8653debae90e275087f6448780f491c33a2a691bbaf0` |
| `tests/ef1/regular_first_trade_price_contract_packets.json` | `e4cd2ec2f97c43012884a7676d7bb6b81e3643ecbe88ebccb9ac251f9bcd6a44` | `b57ac7221508310cdc812f718b19287c9e23604fddcab6a676cb4407bfdd9997` |
| `tests/ef1/regular_first_trade_price_fixture_manifest.json` | `aabe816abfe36921a6c08e4240a66c11e0e0e38401f495464cc935d66706024d` | `8b5c07cd19251394c43e9f441473746182ca0aaf073fd8b72d112c992e6f9e50` |
| `tests/fixtures/bundle_oracle.json` | `bb6d45f64c8de4e826996080f3ab9c1b15a805d315c15da5af797a089ea2deb0` | `48b6730e534ff5101d4a714d3c3b3502598fba6efaf69d9f2387e9ce7685a68c` |
| `tests/publication_goldens.json` | `e86e6aa87f6e7726b7efce2957b074d3ac031d42a79d81e1effe3d8b5eb65f4f` | `cc2df892a4937e5f80cfc0f3c4cc0b750e3d8fd138d50dcf9e7cc35e2c6b3d3d` |

`docs/EF1_SOURCE_EVOLUTION.json` changes the version markers only (0.1.0a11 to 0.1.0a12, four places); no tracked retained source file, additive package file or sha declaration changed; `tools/check_extraction.py` passes.

## range_over_open in output lists

The bar and trade fixtures that enumerate the `session.price` outputs gain `session.price.range_over_open` (independent expected values `5/100` and `5/10`, from H, L and the session open of each fixture): `tests/extensions`, `tests/matrix` (value dicts and the 12 to 13 cell counts). The sink and parquet tests assert named cells only and needed no change. `tests/probe_foundation.py` moves its version asserts and its built-in count 39 to 40.

## Catalogue (D5)

`tools/check_contract_catalogue.py --core-ref 967d13d` found drift in `INDEX.md` and `index.json` only (the version string 0.1.0a4 to 0.1.0a5, from `tools/_versions.py`). No per-page file, source sha or provenance field changed: the core EF3/EF4/EF5 contract files are unchanged by #762. Regenerated; docs copy, package data and regeneration are equal; `verify_contract_catalogue` passes. The io-contracts bump a4 to a5 carries it. The planned CAT-DV1 catalogue pages (D3, `dv1.session_range_over_open`) change the packaged bytes again and need their own bump (a5 to a6).

## Builder pins

`CORE`/`CORE_COMMIT`/`CORE_HEAD` of build_foundation, build_acquisition, build_files and build_bundles name core 967d13d. `build_duckdb` is retired and keeps its historical pin.

## Gates (clean non-editable venv, CPython 3.12.10, core wheels built from 967d13d sources; core checkout 967d13d)

verify_versions, check_extraction, check_io_spec, check_bundles, check_daily_source, check_first_trade_source, verify_typed_refusal, verify_ef4_notional_cells, verify_ef5_io (89 fixtures, 534 runs, 59 refusals), check_contract_catalogue, verify_contract_catalogue pass; mypy 1.15.0 --strict clean on the eight packages. Unit suites: ef1 176, bundles 29, duckdb 94, duckdb-sink 27, parquet 28, acquisition 32, extensions 12, root 48 pass. Environment-only failures, not caused by this change: 10 files tests fail (7 ModuleNotFoundError for the optional `databento_dbn` codec, 3 SourceError), identical on main; one matrix test (`test_actual_installed_versions_workers_version_only`) also fails on main because the deferred `tools/build_matrix.py:24` holds a4/a5 and workers is not installed.

Builders, each run end to end with repeat-archive equality: build_foundation, build_duckdb_sink, build_parquet, build_extensions, build_bundles (core checkout at 967d13d), build_acquisition and build_files PASS. The installed-file invariant of acquisition and files moved 123 to 130 (the seven additional installed files of core a6/a7). build_duckdb stays retired, build_matrix deferred. `check_compatibility` NOT run (needs an old-version environment); open.

## Workers needs (addendum)

Workers pins `equity-feature-bundles` too: move it to 0.1.0a3 wherever it is pinned (mcp evidence extra, tools/_versions.py siblings, any bundles-bearing fixture).

## Re-run after the bundles bump (a2 to a3)

build_bundles (core checkout 967d13d), build_extensions and build_foundation re-run end to end and PASS from the final head; verify_versions, check_bundles, check_extraction, bundles unit tests (29), root tests (48) and mypy strict on bundles pass. build_acquisition, build_files, build_duckdb_sink and build_parquet do not read the bundles version and were not re-run after this change.
