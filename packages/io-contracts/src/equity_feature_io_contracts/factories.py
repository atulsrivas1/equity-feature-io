"""Pure typed composition interfaces; no acquisition/publication operations."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias, TypeVar

from equity_feature_contracts.adapters import AdapterCapabilities
from equity_feature_contracts.inputs import I64_MAX

ConfigValue: TypeAlias = str | int | float | bool | None
PublicConfig: TypeAlias = Mapping[str, ConfigValue]
_T_co = TypeVar("_T_co", covariant=True)


class CredentialProvider(Protocol):
    def get(self, name: str) -> str | None: ...


class ComponentFactory(Protocol[_T_co]):
    @property
    def protocol_version(self) -> str: ...

    def validate_config(self, config: PublicConfig) -> PublicConfig: ...

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> _T_co: ...


class SourceCandidate(Protocol):
    def capabilities(self) -> AdapterCapabilities: ...


class SinkCapabilitiesView(Protocol):
    @property
    def protocol_versions(self) -> tuple[str, ...]: ...
    @property
    def codec_versions(self) -> tuple[str, ...]: ...
    @property
    def identity_versions(self) -> tuple[str, ...]: ...
    @property
    def digest_versions(self) -> tuple[str, ...]: ...
    @property
    def canonical_package_versions(self) -> tuple[str, ...]: ...
    @property
    def canonical_schema_versions(self) -> tuple[str, ...]: ...
    @property
    def math_policy_versions(self) -> tuple[str, ...]: ...
    @property
    def visibility(self) -> str: ...
    @property
    def writer_mode(self) -> str: ...
    @property
    def supports_lookup(self) -> bool: ...
    @property
    def supports_abort(self) -> bool: ...
    @property
    def supports_read(self) -> bool: ...
    @property
    def reservation_retention_ns(self) -> int: ...
    @property
    def max_results(self) -> int: ...
    @property
    def max_chunk_bytes(self) -> int: ...
    @property
    def max_total_bytes(self) -> int: ...
    @property
    def max_result_cells(self) -> int: ...
    @property
    def max_evidence_rows(self) -> int: ...


class SinkCandidate(Protocol):
    def capabilities(self) -> SinkCapabilitiesView: ...


class FactoryErrorCode(StrEnum):
    INVALID_ID = "invalid_id"
    DUPLICATE = "duplicate_id"
    UNKNOWN = "unknown_id"
    INCOMPATIBLE_VERSION = "incompatible_version"
    INVALID_CONFIG = "invalid_config"
    CONSTRUCTION_FAILED = "construction_failed"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


class FactoryError(ValueError):
    """Fixed diagnostics never include supplied config, credentials or exceptions."""
    def __init__(self, code: FactoryErrorCode) -> None:
        if type(code) is not FactoryErrorCode:
            raise TypeError("typed factory error code required")
        self.code = code
        super().__init__("Component selection failed: " + code.value)


@dataclass(frozen=True)
class SinkRequirements:
    protocol_version: str = "1"
    codec_version: str = "efio-json1"
    identity_version: str = "efio-key1"
    digest_version: str = "efio-content1"
    canonical_package_version: str = "0.0.4a4"
    canonical_schema_version: str = "1"
    math_policy_version: str = "v1"
    visibility: str | None = None
    writer_mode: str | None = None
    reservation_retention_ns: int = 1
    max_results: int = 1
    max_chunk_bytes: int = 1024
    max_total_bytes: int = 1024
    max_result_cells: int = 0
    max_evidence_rows: int = 0

    def __post_init__(self) -> None:
        for version in (self.protocol_version, self.codec_version, self.identity_version,
                        self.digest_version, self.canonical_package_version,
                        self.canonical_schema_version, self.math_policy_version):
            if type(version) is not str or not version.strip():
                raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        if (self.visibility is not None and type(self.visibility) is not str) or (self.writer_mode is not None and type(self.writer_mode) is not str):
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        if self.visibility not in (None, "manifest_last", "transactional") or self.writer_mode not in (None, "single_writer", "serialized_writer", "conflict_safe_multi_writer"):
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        for value in (self.reservation_retention_ns, self.max_results, self.max_chunk_bytes, self.max_total_bytes):
            if type(value) is not int or not 1 <= value <= I64_MAX:
                raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        for value in (self.max_result_cells, self.max_evidence_rows):
            if type(value) is not int or not 0 <= value <= I64_MAX:
                raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        if self.max_chunk_bytes > self.max_total_bytes:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
