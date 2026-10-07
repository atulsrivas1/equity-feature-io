# Implement and qualify a public source and sink

Experimental `equity-feature-example-extensions0.1.0a0` is an independently installable Apache-2.0 example using canonical contracts0.0.4a4 and matching I/O contracts/SDK0.1.0a2. It implements public historical acquisition and ResultSink protocols. Importing it creates no registry/instance, reads no credentials and imports no calculation or backend library. The numerical demonstration explicitly adds equity-features0.0.4a4. Acceptance and actual native build artifacts are linked from [canonical EQ128](https://github.com/atulsrivas1/equity-features/issues/285) / [companion PR8](https://github.com/atulsrivas1/equity-feature-io/pull/8); a published plan or green development test is not release acceptance.

## Run from published artifacts

Use CPython3.12x64 and a fresh virtual environment. Download the qualified `extensions-COMMIT-windows-latest` or `extensions-COMMIT-ubuntu-24.04` bundle from the actual accepted CI run linked in the canonical issue. Check its manifest/archive SHA256 and finite expiration. Main source plus finite30day GitHubCI artifacts is the experimental channel; no package registry or stabletag is published. Native qualification covers the recorded Windows/Linux runtimes, not every OS/Python patch.

Replace BUNDLE with the downloaded directory. Install the matching distributions without using a registry:

```text
python -m pip install --no-index --find-links BUNDLE equity-feature-contracts==0.0.4a4 equity-features==0.0.4a4 equity-feature-io-contracts==0.1.0a2 equity-feature-io-sdk==0.1.0a2 equity-feature-example-extensions==0.1.0a0
python -m pip check
python -m equity_feature_example_extensions.demo --mode both
```

Both direct and factory modes preserve every complete result/quality/metadata/evidence byte. Literal synthetic BAR volumes200+300=500 shares, actual notionals20300+30900=51200 at USD scale0, and close-weighted price(102*200+103*300)/500=102.6 USD. The weighted price is the existing proxy calculation, not an actual-notional VWAP. Previous-session data is absent: overnight gap and close-close return remain null/MISSING_INPUT with ABSENT_INPUT. All12 existing session features are returned, including exact integer notional coefficient, available statuses, units and source binding.

## Source and factories

`ExampleSource` supports only `example_request()`: req1, historical BAR/demo, instrumentA/sessionS, snapshot1, [100,200), raw adjustment/no sampling, completed_intervals, scale0 USD, AvailabilitySpec(200,210,210), max_batch_rows2/max_rows2/max_batches1. It emits one terminal ordinal0 batch with SourceBinding(synthetic,snapshot1,map1,bars1), complete2/2source+deliverycoverage, declared ordering/rejectduplicates and InputScope(100,200,example-v1). Two rows have start100/150, end150/200 and known_at150/210. Unsupported request variants fail rather than inventing rows; cancellation before emission yields no batch. A consumer must handle cancellation separately from completed delivery validation; an empty tuple does not certify a complete observed-empty input.

`SourceFactory` accepts only namespace=demo. `SinkFactory` accepts only destination_scope=synthetic-conformance, which also matches SDK qualify_sink scope. Create fresh SourceRegistry/SinkRegistry objects and explicitly register already imported factory objects. The installed demo shows both factory resolution and direct admit_source/admit_sink. Credentials are a separate caller object and never requested by these synthetic factories. SDK scalar/config/secret/executable-key validation and capability checks remain mandatory. Passing a trusted factory instance is local execution, not sandboxing, remote uploaded-code admission or proof arbitrary extension code never logs credentials. Construction errors are redacted by SDK; runtime source errors propagate truthfully, never become fabricated complete results.

## Sink lifecycle, content and limits

`ExampleSink` stores canonical encoded bytes independently in a caller-owned Python instance. It is single_writer/transactional within that instance under sequential caller access only. It has no OS lease, file/backend I/O, concurrent-call qualification, process restart, disk persistence or power-loss guarantee. Preserve the instance to preserve reservations/receipts; deleting/restarting it loses all state. Reservation_retention_ns=1 is a minimum in-instance lifetime declaration, not a durable or elapsed-time test. Committed-at is null because the sink does not fabricate a timestamp.

Capabilities are exact protocol1/efio-json1/efio-key1/efio-content1/canonical0.0.4a4/schema1/mathv1 with lookup/abort/read. Logical ceilings100results/1MiBwhole-unit/10MiBtotal/100000cells/100000evidence per publication. Complete ordered writes check descriptor/uniqueness/bounds. Commit verifies the full content, then makes original receipt/results visible together. Same-key same-content replay returns that original verified receipt; different content conflicts, including after abort. Abort removes staged bytes while retaining the content binding; retry creates a new exclusive handle and invalidates old handles. A new generation leaves old complete results intact. Lookup/read/replay verify retained bytes and reject corrupt or tampered data. Zero results has no artifact; one observed-empty result has one real complete-unit artifact. Artifact references bind per-result bytes, not a mutable container hash.

SDK publish checks cancellation before writes/commit after begin. A pre-existing cancellation may leave an ABORTED reservation without writes; cancellation after verified commitment cannot retract the receipt. Exceptions never certify a successful fallback. No automatic eviction occurs; accumulated retained generations consume caller-owned memory. Logical serialized admission limits are not a hard process RSS cap, storage quota, speedup or latency promise. User implementations own their backend/process/rights/retention qualification.

## Implement your own extension

Copy the installed `equity_feature_example_extensions.protocol_stubs.SourceStub` and `SinkStub` method signatures into your own package; each placeholder deliberately raises NotImplementedError. Implement capabilities and the full historical delivery or begin/write/commit/abort/lookup/read lifecycle. Use canonical contracts and public I/O helpers; do not modify core/SDK or import these examples' private reservation classes. Type assignments to HistoricalAdapter and ResultSink and registry generic parameters verify public interfaces. Choose explicit IDs/scalar config and separate credential provider. Complete result transport includes nulls/quality/evidence/source/availability/units/schema/algorithm, not values only.

For your custom sink, prepare independent complete synthetic facts and run public `qualify_sink(your_factory, results, limits)`, where each factory call returns an isolated destination. This example's test harness uses18accepted complete synthetic records and all21actual SDK cases. Conformance checks contract behavior; it does not certify backend durability or source truth. Define literal source coverage/identities/units/timing/result expectations in addition to round-trip equality, and test negative versions/capabilities/config, redacted construction failure, runtime failures and cancellation.

To reproduce this tutorial's qualification from a clean committed checkout with the matching core checkout:

```text
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --no-build-isolation -e ../core/packages/contracts -e ../core/packages/features -e packages/io-contracts -e packages/io-sdk -e examples/factory_consumer -e examples/third_party
python -m mypy --strict examples/third_party/src
python tests/extensions/test_extensions.py --report-json work/extensions.json
python tools/build_extensions.py --core-root ../core
```

Create work before the development report, freeze/commit scoped source, and use a fresh dist-extensions directory. The repeat builder materializes committed Git archives, checks exact metadata/source hashes, repeats actual wheel/sdist builds, creates fresh standalone installs without the calculation library/testfixture/backends, then fresh calculation consumers with both public injection paths,12independent methods/21cases, installed/external typing/two rejected calls and pure package byte invariance. Only tests install the factory fixture.a1; it is absent from extension runtime dependencies. Tests are synthetic; no private/provider data, worker execution or historical generation is included.
