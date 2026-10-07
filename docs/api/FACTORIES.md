# Explicit source and sink composition

EQ124 / [canonical281](https://github.com/atulsrivas1/equity-features/issues/281), E19 / R4.1. Experimental io-contracts0.1.0a1 and io-sdk0.1.0a1; SDK depends exactly on contracts.a1 and canonicalcontracts0.0.4a4. DuckDB.a8 remains independently packaged, without this SDK dependency. [Frozen I/O v1 design](../contracts/IO_V1.md) supplies sink capability versions/meanings. Runtime publication types/codec/conformance are EQ125; storage/process guarantees are EQ126/127.

Create SourceRegistry[T] and SinkRegistry[T] explicitly for each run. Register already imported local ComponentFactory[T] objects. Each registry owns its mapping; source/sink namespaces are distinct and the same ID may be used in both. IDs match `[a-z][a-z0-9_.-]{0,63}`; duplicate, unknown and invalid IDs fail. There is no automatic module loading, plugin discovery, import-time registration or default mutable registry. Registries do not promise shared concurrent mutation; the caller owns startup configuration and instance lifetime.

Factories expose protocol_version='1', validate_config(PublicConfig)->PublicConfig and create(PublicConfig,CredentialProvider)->T. SDK accepts scalar string/int/finite float/bool/null mapping values, copies them to a read-only MappingProxyType, calls the extension validator, then revalidates/copies the returned scalar mapping before construction. Configuration keys match `[a-z][a-z0-9_]{0,63}`. Keys containing password/secret/credential/token/api_key and module/import/class_path/callable are rejected. Arbitrary nested objects/paths/containers, nonfinite floats and executable configuration are outside this v1 scalar configuration. A factory validates its own allowed key set, exact value types and backend-specific meaning. Caller credentials are never configuration entries.

CredentialProvider.get(name)->str|None is supplied separately; it may return no credential for a synthetic/public component. The SDK never reads credentials itself, stores the provider on a registry or formats it. Providers/factories/components are trusted local caller code; their own methods can perform arbitrary actions. This API does not sandbox construction/validation/capability methods or certify their truth. Future remote services must expose only server-selected registered objects and validated public configuration, never uploaded executables/module paths.

```python
from equity_feature_factory_fixture import SourceFactory, SinkFactory, SyntheticSource, SyntheticSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import SourceRegistry, SinkRegistry, admit_source, admit_sink

class NoCredentials:
    def get(self, name: str) -> str | None:
        return None

sources: SourceRegistry[SyntheticSource] = SourceRegistry()
sinks: SinkRegistry[SyntheticSink] = SinkRegistry()
sources.register("custom.basic", SourceFactory())
sinks.register("custom.basic", SinkFactory())
# request is a caller-supplied canonical AcquisitionRequest.
source = sources.resolve("custom.basic", {"namespace": "synthetic"}, NoCredentials(), request)
sink = sinks.resolve("custom.basic", {"label": "output"}, NoCredentials(), SinkRequirements())
direct_source = admit_source(SyntheticSource("synthetic"), request)
direct_sink = admit_sink(SyntheticSink("output"), SinkRequirements())
```

The separately installed synthetic fixture illustrates factory admission only; its sink has no production publication implementation. Admission itself calls neither source acquisition nor sink writes. A SourceRegistry preserves its generic returned type; historical/live method selection is explicit with live=False/True. Source admission reuses canonical require_adapter_capability and requires the selected iter_batches/stream_batches method to be callable. Unknown source schema/precision or incompatible mode/kind/namespace/unit/basis/sampling/batch bound fails before the consumer begins acquisition. No live provider is delivered.

SinkCandidate/SinkCapabilitiesView are structural startup views, not the full operational sink protocol. SinkRequirements supplies exact versions from I/O v1 plus optional required visibility/writer mode, minimum reservation retention and requested result/chunk/total byte/cell/evidence bounds. All requested versions must equal the SDK's admitted frozen version tuple. Capabilities must offer those versions in unique nonempty tuples, declare a supported mode, supports_lookup/abort/read exactlyTrue and consistent exact int64 bounds at least as large as requested. Visibility/writer guarantees are declarations requiring actual conformance/backend evidence; passing admission does not establish durable storage, transactions, process safety or exactly-once execution. EQ125 supplies full sink methods/types and reusable operational conformance. Direct and factory paths use the same admission helper.

FactoryError has a stable FactoryErrorCode and a fixed message. SDK suppresses raw validator/constructor/provider/capability exception text/context in rendered diagnostics and never prints config/provider/component values. Factory version is checked at registration and resolution; caller mutation cannot silently upgrade the admitted protocol. Codes: invalid_id, duplicate_id, unknown_id, incompatible_version, invalid_config, construction_failed, unsupported_capability. Runtime schema/version/type errors remain canonical or later sink errors; these factory errors describe startup selection. Do not wrap a typed failure as a successful default component. Redaction does not prevent a trusted extension from logging its own secrets; the SDK makes no such external-code guarantee.

[Synthetic consumer](../../examples/factory_consumer/README.md), tests/test_factories.py and the fresh-form builder qualify public installed factories, direct equivalence, negative capability/schema/version/configuration, redacted failure, registry isolation/import behavior and external typing. Core-without-I/O bytes/imports and independent numerical goldens remain separate checks. Accepted worker.a0 still binds its old SDK.a0 pair; current release composition alignment is EQ129, not an untested mixed-pair promise. Supported CPython3.12x64 Windows/Linux, no registry release/stable tag or worker commands.

## Current operational pair

EQ125 matchingcontracts/SDK.a2 retain this exactfactory protocol1 behavior and add concreteSinkCapabilities/ResultSink/publication codec/lifecycle/conformance: [public API](PUBLICATION.md). The original EQ124.a1 receipt above is historical; backends require separate actualqualification.
