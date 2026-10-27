# Equity Feature Bundles

Optional `equity-feature-bundles==0.1.0a1` provides data-only, deterministic byte
archives for a fixed `session.compute_trades.v1` request. It requires contracts
0.0.4a4 and evidence0.1.0a2. The explicit `replay` extra additionally requires
features0.0.4a5. CPython3.12; Apache-2.0. No registry publication is implied.

`write_bundle(receipt, configuration, result, inputs, publication)` accepts
immutable supplied facts. `inputs` is a tuple of role/CanonicalBatch pairs for
the embedded subset. Omitted receipt inputs remain explicit unavailable
references. `read_bundle(raw_bytes)` returns a `ReproductionBundle`; neither
operation executes a calculator. Every stored configuration, output and
available input is checked against complete content fingerprints and metadata.

```python
from equity_feature_bundles import PublicationDeclaration, write_bundle, read_bundle
from equity_feature_bundles.replay import replay_bundle

declaration = PublicationDeclaration('synthetic', 'Caller-created synthetic example', 'caller_owned')
raw = write_bundle(receipt, configuration, result, (('trades', batch),), declaration)
bundle = read_bundle(raw)
report = replay_bundle(bundle)
assert report.status == 'matched'
```

The last step requires the extra in a trusted installed environment. Replay
resolves only explicitly supplied missing inputs, validates all content and
request bounds, and invokes one fixed calculator. No network, resolver, plugin,
uploaded code or installation is selected by archive content. Unavailable data,
incompatible installations and cancellation before entry make zero calls.
The five-second **after-return acceptance gate** does not interrupt an active
synchronous calculation. Over-gate results withhold comparison. Full canonical
bytes decide parity, including metadata, quality, signed zero and float64 hex;
there is no approximate match, retry or global safety score.

The closed format uses ZIP_STORED, fixed ASCII entry names and canonical JSON.
It rejects aliases, links, extra members, compression/encryption/ZIP64,
descriptors, comments, padding and inconsistent CRC/hash/header metadata.
The reader validates all headers and bounded names before copying members,
then shared lexical size/node/depth/token limits before typed reconstruction.
Archive<=35MiB, payload<=34MiB, typed graphs collectively<=32MiB/1million JSON
nodes, <=68members; replay<=10000trade rows/64intervals/256governed sessions.
These bound application work and copies, not OS memory or physical deadlines.

The API takes bytes and creates no filesystem entries. A caller that persists
bytes owns directory permissions, retention and nofollow cleanup. The required
publication declaration is a caller assertion, not proof of data rights. A
receipt or replay match authenticates neither original execution/environment
nor source truth. Malformed/conflicting content raises payload-free BundleError;
it never becomes valid unavailable data. Unexpected replay exceptions propagate.
No pickle, reflection-based reconstruction or source/credential/path/URL hooks.

Unknown versions refuse. Future dependency/format migration requires an explicit
version and renewed qualification; do not replace exact pins with latest.
See the canonical EQ-098 plan for the complete schema, report matrix, lexical
limits, threat model and delivery requirements. The independent pre-code
fixture is tests/fixtures/bundle_oracle.json in the companion repository.

The fixed registry admits result schema1/math policyv1 only. A content-consistent
receipt with another mathematical policy is rejected before any calculator
call; mismatch describes returned disagreement under the supported policy.

The fixed eligibility_policy parameter must be an exact string with nonempty
`.strip()`, including in a zero-input missing-result bundle. Generic ConfigSpec
validity or a newly consistent receipt cannot defer this static request check
until calculator invocation. Unsupported requests refuse before execution.
