"""Synthetic consumer using installed public interfaces only; no registration."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from equity_feature_contracts.adapters import (
    AcquisitionRequest, AdapterBatch, AdapterCapabilities, Cancellation,
)
from equity_feature_contracts.inputs import (
    BatchMetadata, CanonicalBatch, Column, Coverage, DataKind, InputScope,
    PriceUnit, SourceBinding, schema_for,
)
from equity_feature_io_contracts import CredentialProvider, PublicConfig, SinkCapabilitiesView

__version__ = "0.1.0a0"


class SyntheticSource:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.acquisitions = 0

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities((DataKind.BAR,), (self.namespace,), (PriceUnit(0, "USD"),), max_batch_rows=4)

    def iter_batches(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        self.acquisitions += 1
        if cancellation.is_cancelled():
            return
        source = SourceBinding("synthetic-factory", request.snapshot_id, "mapping1", "factory-bars1")
        coverage = Coverage(0, 0, True)
        metadata = BatchMetadata(request.namespace, source, coverage, request.price_unit,
                                 scope=InputScope(request.start_ns, request.end_ns, "synthetic-v1"))
        batch = CanonicalBatch(DataKind.BAR, tuple(Column(field.name, ()) for field in schema_for(DataKind.BAR).fields), metadata)
        yield AdapterBatch(request.request_id, 0, True, source, coverage, coverage, batch)


@dataclass(frozen=True)
class SyntheticCapabilities:
    protocol_versions: tuple[str, ...] = ("1",)
    codec_versions: tuple[str, ...] = ("efio-json1",)
    identity_versions: tuple[str, ...] = ("efio-key1",)
    digest_versions: tuple[str, ...] = ("efio-content1",)
    canonical_package_versions: tuple[str, ...] = ("0.0.4a4",)
    canonical_schema_versions: tuple[str, ...] = ("1",)
    math_policy_versions: tuple[str, ...] = ("v1",)
    visibility: str = "manifest_last"
    writer_mode: str = "single_writer"
    supports_lookup: bool = True
    supports_abort: bool = True
    supports_read: bool = True
    reservation_retention_ns: int = 1000
    max_results: int = 2
    max_chunk_bytes: int = 4096
    max_total_bytes: int = 8192
    max_result_cells: int = 20
    max_evidence_rows: int = 20


class SyntheticSink:
    """Capability test candidate only; no production publication implementation."""
    def __init__(self, label: str) -> None:
        self.label = label
        self.writes = 0
        self.offered = SyntheticCapabilities()

    def capabilities(self) -> SinkCapabilitiesView:
        return self.offered

    def fixture_write(self) -> None:
        self.writes += 1


class SourceFactory:
    protocol_version = "1"

    def validate_config(self, config: PublicConfig) -> PublicConfig:
        if set(config) != {"namespace"} or type(config["namespace"]) is not str or not config["namespace"]:
            raise ValueError("synthetic source config rejected")
        return config

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> SyntheticSource:
        namespace = config["namespace"]
        if type(namespace) is not str:
            raise ValueError("synthetic namespace required")
        credentials.get("fixture")  # Explicit separate provider, never public config.
        return SyntheticSource(namespace)


class SinkFactory:
    protocol_version = "1"

    def validate_config(self, config: PublicConfig) -> PublicConfig:
        if set(config) != {"label"} or type(config["label"]) is not str or not config["label"]:
            raise ValueError("synthetic sink config rejected")
        return config

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> SyntheticSink:
        label = config["label"]
        if type(label) is not str:
            raise ValueError("synthetic label required")
        credentials.get("fixture")
        return SyntheticSink(label)
