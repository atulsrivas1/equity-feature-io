# EQ129 composed repository compatibility

Canonical [EQ129#286](https://github.com/atulsrivas1/equity-features/issues/286),
component PR9/core PR299/workers PR2. Plans were published before implementation.
The current matrix builds exact committed sources from three repositories and
repeats every wheel/sdist, using epoch1700000000. Per native Windows/Linux producer,
18 current archives represent nine distributions; eight additional historical
archives provide complete offline candidates for two deliberate dependency conflicts.
Hashes are per platform; cross-platform byte equality is not promised.

| Distribution | Exact version | Runtime dependency |
| --- | --- | --- |
| equity-feature-contracts | 0.0.4a4 | None; optional columnar extras unchanged |
| equity-features | 0.0.4a4 | Canonical contracts.a4 |
| equity-feature-io-contracts | 0.1.0a2 | Canonical contracts.a4 |
| equity-feature-io-sdk | 0.1.0a2 | IO contracts.a2 |
| equity-feature-duckdb | 0.1.0a8 | Canonical contracts.a4/DuckDB1.5.6/NumPy2.2.6 |
| equity-feature-parquet | 0.1.0a0 | SDK.a2/PyArrow20.0.0 |
| equity-feature-duckdb-sink | 0.1.0a0 | SDK.a2/DuckDB1.5.6 |
| equity-feature-example-extensions | 0.1.0a0 | Canonical contracts.a4/SDK.a2 |
| equity-feature-workers | 0.1.0a1 | SDK.a2; version-only skeleton |

Each actual fresh wheel/sdist form runs core-only absence/import denial/calculation,
dependency-light extensions without calculation/fixture/backends, and full composed
installs with exact engines and pip check. Installed public typing includes an external
source/three-sink consumer and three invalid calls. Six meaningful composed tests
exercise nine source-result-sink routes, complete12 values/quality/source/timing/units/
evidence/null metadata and exact canonical result bytes/readback/replay. The custom
direct/factory source yields500/51200/102.6; accepted standalone minute source yields
volume8/weighted11.625/notionalnull/MISSING_INPUT, with independent literal facts.
Catalog/original/optimized Parquet files remain identical; WAL is absent before/after.
This does not qualify a WAL-present source. Unsupported codecs/writer modes and source/
partial-write failures are checked; no successful receipt after failed publication.

Actual offline resolver rejection and fresh forced-install pip check cover workers.a0
with SDK.a2 and IO contracts.a1 with SDK.a2, with all requested transitive candidates.
Other untested versions/platforms remain unqualified. No runtime compatibility promise
is inferred from matching numbers. All unchanged nonworker archives must equal accepted
EQ128 native artifacts. Core file fingerprints before/after composition remain identical.

Build pins: core45d0fb292234060f8196ba6569ce7805dd921846; worker implementation
8ee8719eda773efef838805475173f2b474488df; accepted IO395beba80b3bcb2e9db344c6a9d2bcab085be1a6.
Current I/O head is captured in its own report. Historical candidates come from actual
workerb2f13c9a167cf099b080408bb35147cefdefb87a, IO8461ee52a2631ac8aa1be52f6cf222ac7a14b87b
and IO8f3208d53da095bcf730cdf95f65a749028af2d6. Committed snapshots, scoped source/end guards,
source/fixture/manifest hashes and accepted archive identities exclude caller changes.

Run `python tools/build_matrix.py --core-root <core-checkout> --worker-root <worker-checkout>`
with full source history/pinned requirements and a fresh dist-matrix. Declared release
channel is successful actualmain `matrix-<commit>-<OS>` finite30day Actions artifacts,
alongside current component bundles. Verify actual manifest/archive/source/ZIP hashes and
expiry. In a clean CPython3.12 x64 environment install the selected nine wheels with
`pip install --no-index --no-deps <nine-wheels>` after exact backend engines above, then
`pip check`. For nine sdists, install setuptools80.9.0 first and use --no-build-isolation.
Never install deliberate incompatible historical candidates into the supported environment.
The committed synthetic consumer can be run against the actual installed packages with
`python tests/matrix/test_composition.py --installed --report-json <output.json>`.

Development validation: six tests passed after correcting a fixture's nonexistent IO
source-error enum to public TRANSPORT plus a safe message; this was test preparation,
not a package defect. Worker repeat/fresh forms passed locally. Separate final-head review,
current native matrix/artifact/source-owner/actualmain publication acceptance remain pending.
No package math/source/SDK/backend/extension behavior changed, no private rerun; accepted
private immutable bindings remain scoped. No new performance/durability/concurrency/rights/
hosted/human-review claim. Existing storage/resource/retention limitations remain in EQ126/
127/128. Workers exports only version, no R5 execution. EQ130 final audit follows; STOP
before R5/providers/services/registry/stable tags/private generation.
