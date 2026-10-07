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

## EQ129 source qualification / final documentation review

Canonical286 Test6032051791. Source IOdfea32211edef36178d91f35723a8aac8deb96ba / worker8ee8719eda773efef838805475173f2b474488df / core778c5980b13a4fb6a2f0e339230dc80c1c479f6f completed separate local automated reviews6032044565/6032045184/6032045794, no unresolved findings. Actual local repeat/current native/fresh forms and all source CI passed. Receipt SHA256 83f2a9889b445018aa50650ab5a7e69cf9b6222f086340a4d4d97a36f88c28c1 verifies146 archive files/sixteen actual ZIP digests/all202 downloaded files/current source/probe/harness/report identities/Atul ownership/all three public blob trees/finite expiry. Counts include repeated current dependencies and16 historical candidate archives, not146 unique packages. Source receipt is qualification, not actualmain release acceptance.

Four fresh native matrix forms each six meaningful methods/nine full source-result-sink routes, installed9package/exact3engine versions, core-only absence/deny/calculation, dependency-light extension without calculation/fixture/backends, full composed imports/public external typing/three invalidcalls/two real offline resolver conflicts plus two fresh forcedpipcheck conflicts and exact pure package fingerprints pass. Four aligned worker freshforms/public versions/typing/provenance/coregoldens pass. Nonworker matrix archives equal accepted EQ128 native artifacts; Windows allmatrix/current+historical and worker archives equal local committed repeats. Baseline core633/factory21/publication25/source94+30SDK16numerical/Parquet17physical8process/DuckDBsink18physical9process/extensions12methods21cases18facts stay separately qualified current. Actual report runtimes: matrix: Linux CPython3.12.15, Windows CPython3.12.10; worker: Linux CPython3.12.14, Windows CPython3.12.10; core: Linux CPython3.12.14, Windows CPython3.12.10. No runtime extrapolation between producers.

Custom source500/51200/102.6 remains distinct from minute source8/11.625/notionalnull/MISSING_INPUT. All12 complete facts/readback metadata/quality/UTCns/units/nulls/evidence and source catalog/original/optimized Parquet byte invariance pass; source WAL absent before/after only. Worker.a1 changes version/dependency/build/probe metadata, exports version only; no commands/jobs/claims/scheduling/catalog/generation. Pure/source/SDK/backend/extension runtime/math unchanged; accepted private immutable bindings retained without execution. No new performance/rights/remote safety/processdurability/hardRSS/human/hosted claim.

Next freeze these final documentation heads, renewed exact-head separate review/current CI/current146archives/16ZIP202files source/channel guards, exacthead publication/successful actualmain artifact equality/sourceowner/report/expiry readback before Released/postreadDone. EQ130 final audit follows; STOP before R5/providers/services/registry/stabletags/privategeneration. Earlier snapshots below remain historical; live Project is authority.

## EQ129 Windows process qualification rework / In progress

Canonical286 returned Test -> In progress in [6032201654](https://github.com/atulsrivas1/equity-features/issues/286#issuecomment-6032201654). Required PR DuckDB sink run [37579927602](https://github.com/atulsrivas1/equity-feature-io/actions/runs/37579927602) failed three installed Windows recovery cases: lookup remained BUSY after the harness terminated/waited the venv launcher. Successful push37579924006 does not clear that failed gate. Earlier source receipt83f2a9889b445018aa50650ab5a7e69cf9b6222f086340a4d4d97a36f88c28c1 and metadata readbackd1915f91d0f24bf28e724fff2937e5fc5e02c06f13451020461ab7e283e7132d remain historical qualification of their stated heads, not acceptance of the corrected harness or release evidence.

Separate local automated reviewer /root/eq121_component_review independently reproduced the harness assumption with twelve disposable Windows venv children: every launcher PID differed from its interpreter PID; every actual runtime handle remained nonsignaled immediately after launcher termination/wait; the byte lock remained held in two of twelve probes. Waiting the actual runtime handle established lock reacquisition in all twelve. The author separately observed differing wrapper/runtime PIDs and WAIT_TIMEOUT after wrapper exit. These are test-owned diagnostics, not a backend defect demonstration or universal failure rate. CPython's [3.12 venv launcher source](https://github.com/python/cpython/blob/v3.12.10/PC/venvlauncher.c) distinguishes launcher and interpreter processes.

Correction is confined to the two DuckDB sink process test fixture files. Review found a further pre-checkpoint timeout/cleanup gap; it was corrected before source freeze. A generated per-child ownership nonce and actual interpreter PID are emitted in a startup handshake before backend imports/storage. The parent validates ownership and retains the actual Windows process handle before sending the required startup acknowledgement; EOF before acknowledgement cannot resume SQL. Phase checkpoints, including source_wal, must match that same owner. Termination requires the retained runtime handle to signal exit before recovery/storage observation, then waits the launcher; nested cleanup closes owned handles/pipes and attempts every child. The reviewer independently injected a malformed phase nonce in an owned temporary fixture: rejection, actual owner exit, all pipe closure, STAGING lookup and full result recovery passed in5.896s. This diagnostic covers the working refinement, not final-head/native acceptance. Existing live-owner BUSY, five interrupted recovery boundaries, receipt/full-result bytes, two-writer conflict/replay and source database-plus-WAL invariance assertions remain. All nine local development tests passed in39.451s before renewed review; native fresh wheel/sdist qualification is pending. No sink/source/SDK/pure/extension/worker runtime, mathematics, package version or accepted private binding changes; no private execution.

Next freeze corrected source and continuity, renew separate exact-head review, enter Test and require every current PR check plus actual native fresh artifacts/source guards. Record new qualification separately, renew final metadata/head review, then exact-head publication and successful actual-main artifacts/readbacks before Released/Done. EQ130 follows accepted129. One active story; stop before R5/providers/services/registry/stable tags/private generation. Earlier snapshots below preserve history; the live Project is status authority.
