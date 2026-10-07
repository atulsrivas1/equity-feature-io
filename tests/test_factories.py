"""Independent synthetic consumer expectations, reused from installed forms."""
import dataclasses
import importlib
import importlib.abc
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import traceback
import unittest

from equity_feature_contracts.adapters import AcquisitionRequest, validate_delivery
from equity_feature_contracts.inputs import DataKind, PriceUnit
from equity_feature_contracts.specs import AvailabilitySpec
from equity_feature_factory_fixture import (
    SinkFactory, SourceFactory, SyntheticCapabilities, SyntheticSink, SyntheticSource,
)
from equity_feature_io_contracts import FactoryError, FactoryErrorCode, SinkRequirements
from equity_feature_io_sdk import SinkRegistry, SourceRegistry, admit_sink, admit_source

SENSITIVE = "synthetic_sensitive_fixture_marker"


class Credentials:
    def get(self, name):
        return SENSITIVE

    def __repr__(self):
        raise AssertionError("provider repr must never be used")


class Cancellation:
    def is_cancelled(self):
        return False


def request(**changes):
    r = AcquisitionRequest("req1", DataKind.BAR, "synthetic", ("I",), ("S",), 0, 10,
                           "snapshot1", PriceUnit(0, "USD"), AvailabilitySpec(10, 10, 10),
                           max_batch_rows=4, selection="completed_intervals")
    return dataclasses.replace(r, **changes)


class Factories(unittest.TestCase):
    def setUp(self):
        self.sources = SourceRegistry()
        self.sinks = SinkRegistry()
        self.credentials = Credentials()
        self.sources.register("custom.basic", SourceFactory())
        self.sinks.register("custom.basic", SinkFactory())

    def reject(self, code, operation):
        try:
            operation()
        except FactoryError as error:
            self.assertEqual(error.code, code)
            diagnostic = "".join(traceback.format_exception(error))
            self.assertNotIn(SENSITIVE, diagnostic)
            self.assertNotIn(SENSITIVE, str(error))
            self.assertNotIn(SENSITIVE, repr(error))
        else:
            self.fail("expected typed rejection")

    def test_direct_factory_source_equivalence_before_acquisition(self):
        direct = admit_source(SyntheticSource("synthetic"), request())
        built = self.sources.resolve("custom.basic", {"namespace": "synthetic"}, self.credentials, request())
        self.assertEqual(direct.capabilities(), built.capabilities())
        self.assertEqual((direct.acquisitions, built.acquisitions), (0, 0))
        a = tuple(direct.iter_batches(request(), Cancellation()))
        b = tuple(built.iter_batches(request(), Cancellation()))
        self.assertEqual(a, b)
        self.assertEqual(a[0].batch.row_count, 0)
        self.assertTrue(a[0].source_coverage.complete)
        validate_delivery(request(), built.capabilities(), b)
        self.assertEqual((direct.acquisitions, built.acquisitions), (1, 1))

    def test_direct_factory_sink_equivalence_without_publication(self):
        direct = admit_sink(SyntheticSink("target"), SinkRequirements())
        built = self.sinks.resolve("custom.basic", {"label": "target"}, self.credentials, SinkRequirements())
        self.assertEqual(direct.capabilities(), built.capabilities())
        self.assertEqual((direct.label, built.label, direct.writes, built.writes), ("target", "target", 0, 0))

    def test_namespaces_and_per_run_isolation(self):
        self.assertEqual(self.sources.ids, self.sinks.ids)
        isolated = SourceRegistry()
        self.assertEqual(isolated.ids, ())
        self.reject(FactoryErrorCode.UNKNOWN, lambda: isolated.resolve("custom.basic", {}, self.credentials, request()))

    def test_duplicate_unknown_and_invalid_ids(self):
        self.reject(FactoryErrorCode.DUPLICATE, lambda: self.sources.register("custom.basic", SourceFactory()))
        self.reject(FactoryErrorCode.UNKNOWN, lambda: self.sinks.resolve("unknown", {}, self.credentials, SinkRequirements()))
        for identifier in ("plugin://unsafe", "../module", "UPPER", "", SENSITIVE + "\n"):
            with self.subTest(identifier=identifier):
                self.reject(FactoryErrorCode.INVALID_ID, lambda: self.sources.register(identifier, SourceFactory()))

    def test_unknown_configuration_key(self):
        self.reject(FactoryErrorCode.INVALID_CONFIG, lambda: self.sources.resolve("custom.basic", {"namespace": "synthetic", "extra": SENSITIVE}, self.credentials, request()))

    def test_secret_module_and_invalid_scalar_config(self):
        for config in ({"token": SENSITIVE}, {"module": "arbitrary_module"}, {"namespace": object()},
                       {"namespace": float("nan")}, {"namespace": float("inf")}, {"namespace": ["synthetic"]}):
            with self.subTest(config_keys=tuple(config)):
                self.reject(FactoryErrorCode.INVALID_CONFIG, lambda: self.sources.resolve("custom.basic", config, self.credentials, request()))

    def test_validator_receives_owned_immutable_copy(self):
        original = {"namespace": "synthetic"}
        class Mutating(SourceFactory):
            def validate_config(self, config):
                config["namespace"] = SENSITIVE
                return config
        self.sources.register("mutating", Mutating())
        self.reject(FactoryErrorCode.INVALID_CONFIG, lambda: self.sources.resolve("mutating", original, self.credentials, request()))
        self.assertEqual(original, {"namespace": "synthetic"})

    def test_validator_output_revalidated(self):
        class InvalidOutput(SourceFactory):
            def validate_config(self, config):
                return {"token": SENSITIVE}
        self.sources.register("invalid_output", InvalidOutput())
        self.reject(FactoryErrorCode.INVALID_CONFIG, lambda: self.sources.resolve("invalid_output", {}, self.credentials, request()))

    def test_validation_failure_redacted(self):
        class Bad(SourceFactory):
            def validate_config(self, config):
                raise RuntimeError(SENSITIVE)
        self.sources.register("bad", Bad())
        self.reject(FactoryErrorCode.INVALID_CONFIG, lambda: self.sources.resolve("bad", {}, self.credentials, request()))

    def test_construction_and_provider_failure_redacted(self):
        class Bad(SourceFactory):
            def create(self, config, credentials):
                raise RuntimeError(credentials.get("fixture"))
        self.sources.register("bad", Bad())
        self.reject(FactoryErrorCode.CONSTRUCTION_FAILED, lambda: self.sources.resolve("bad", {"namespace": "synthetic"}, self.credentials, request()))
        class BadProvider(Credentials):
            def get(self, name):
                raise RuntimeError(SENSITIVE)
        self.reject(FactoryErrorCode.CONSTRUCTION_FAILED, lambda: self.sources.resolve("custom.basic", {"namespace": "synthetic"}, BadProvider(), request()))

    def test_factory_version_rejected_and_rechecked(self):
        factory = SourceFactory()
        factory.protocol_version = "2"
        self.reject(FactoryErrorCode.INCOMPATIBLE_VERSION, lambda: self.sources.register("new", factory))
        factory.protocol_version = "1"
        self.sources.register("new", factory)
        factory.protocol_version = "2"
        self.reject(FactoryErrorCode.INCOMPATIBLE_VERSION, lambda: self.sources.resolve("new", {}, self.credentials, request()))

    def test_factory_version_property_failure_redacted(self):
        class Bad:
            @property
            def protocol_version(self):
                raise RuntimeError(SENSITIVE)
        self.reject(FactoryErrorCode.INCOMPATIBLE_VERSION, lambda: self.sources.register("new", Bad()))

    def test_source_capability_failure_before_acquisition(self):
        source = SyntheticSource("synthetic")
        for r in (request(namespace="other"), request(max_batch_rows=5), request(price_unit=PriceUnit(1, "USD"))):
            self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_source(source, r))
        self.assertEqual(source.acquisitions, 0)
        self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_source(source, request(), live=True))

    def test_source_schema_and_capability_exception_redacted(self):
        class Bad(SyntheticSource):
            def capabilities(self):
                raise RuntimeError(SENSITIVE)
        source = Bad("synthetic")
        self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_source(source, request()))
        self.assertEqual(source.acquisitions, 0)
        class BadSchema(SyntheticSource):
            def capabilities(self):
                return dataclasses.replace(super().capabilities(), schema_version="2")
        source = BadSchema("synthetic")
        self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_source(source, request()))
        self.assertEqual(source.acquisitions, 0)

    def test_source_operation_missing(self):
        class Incomplete:
            def capabilities(self):
                return SyntheticSource("synthetic").capabilities()
        self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_source(Incomplete(), request()))

    def test_sink_exact_version_rejection(self):
        for field, changed in (('protocol_version', '2'), ('codec_version', 'unknown'), ('canonical_package_version', '0.0.5')):
            requirements = dataclasses.replace(SinkRequirements(), **{field: changed})
            self.reject(FactoryErrorCode.INCOMPATIBLE_VERSION, lambda: admit_sink(SyntheticSink("target"), requirements))
        sink = SyntheticSink("target")
        sink.offered = dataclasses.replace(sink.offered, codec_versions=("unknown",))
        self.reject(FactoryErrorCode.INCOMPATIBLE_VERSION, lambda: admit_sink(sink, SinkRequirements()))
        self.assertEqual(sink.writes, 0)

    def test_sink_invalid_version_declarations(self):
        sink = SyntheticSink("target")
        for offered in (("1", ""), ("1", "1"), ["1"], (True,), ()):
            sink.offered = dataclasses.replace(SyntheticCapabilities(), protocol_versions=offered)
            self.reject(FactoryErrorCode.INCOMPATIBLE_VERSION, lambda: admit_sink(sink, SinkRequirements()))
        self.assertEqual(sink.writes, 0)

    def test_sink_required_mode_flags_limits(self):
        sink = SyntheticSink("target")
        for requirements in (SinkRequirements(visibility="transactional"), SinkRequirements(writer_mode="serialized_writer"),
                             SinkRequirements(max_results=3), SinkRequirements(max_evidence_rows=21),
                             SinkRequirements(reservation_retention_ns=1001)):
            self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_sink(sink, requirements))
        for field, changed in (('supports_read', False), ('supports_lookup', 1), ('max_results', True), ('max_total_bytes', 1)):
            sink.offered = dataclasses.replace(SyntheticCapabilities(), **{field: changed})
            self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_sink(sink, SinkRequirements()))
        self.assertEqual(sink.writes, 0)

    def test_sink_capability_failure_redacted(self):
        class Bad(SyntheticSink):
            def capabilities(self):
                raise RuntimeError(SENSITIVE)
        sink = Bad("target")
        self.reject(FactoryErrorCode.UNSUPPORTED_CAPABILITY, lambda: admit_sink(sink, SinkRequirements()))
        self.assertEqual(sink.writes, 0)

    def test_invalid_requirements(self):
        for change in ({"max_results": True}, {"max_chunk_bytes": 2048}, {"max_evidence_rows": -1}, {"writer_mode": "unsafe"}):
            self.reject(FactoryErrorCode.INVALID_CONFIG, lambda: SinkRequirements(**change))

    def test_import_has_no_discovery_or_global_registry(self):
        class Deny(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in ('duckdb', 'pyarrow', 'numpy', 'requests', 'httpx', 'arbitrary_module'):
                    raise AssertionError("unexpected backend/discovery import")
        deny = Deny()
        sys.meta_path.insert(0, deny)
        try:
            module = importlib.reload(importlib.import_module('equity_feature_io_sdk.factories'))
            self.assertEqual(module.SourceRegistry().ids, ())
            self.assertEqual(module.SinkRegistry().ids, ())
            self.assertFalse(any(isinstance(value, module._Registry) for value in vars(module).values()))
        finally:
            sys.meta_path.remove(deny)


if __name__ == '__main__':
    report = None
    if '--report-json' in sys.argv:
        index = sys.argv.index('--report-json')
        report = Path(sys.argv[index + 1])
        del sys.argv[index:index + 2]
    installed = '--installed' in sys.argv
    if '--installed' in sys.argv:
        sys.argv.remove('--installed')
        for name in ('equity_feature_io_contracts', 'equity_feature_io_sdk', 'equity_feature_factory_fixture'):
            module = importlib.import_module(name)
            assert 'site-packages' in Path(module.__file__).resolve().parts
    program = unittest.main(exit=False)
    if not program.result.wasSuccessful():
        sys.exit(1)
    if report is not None:
        report.write_text(json.dumps({
            'schema': 'factory-installed1',
            'synthetic_factory_tests': program.result.testsRun,
            'installed_public_execution': installed,
            'test_suite_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'io_contracts': version('equity-feature-io-contracts'),
            'io_sdk': version('equity-feature-io-sdk'),
            'consumer': version('equity-feature-factory-fixture'),
            'backend_or_private_certification': False,
        }, sort_keys=True, indent=2) + '\n', encoding='utf-8')
