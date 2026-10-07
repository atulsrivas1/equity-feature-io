"""Explicit per-run construction and direct-instance capability admission."""
from __future__ import annotations

from collections.abc import Mapping
import math
import re
from types import MappingProxyType
from typing import Generic, TypeVar

from equity_feature_contracts.adapters import AcquisitionRequest, require_adapter_capability
from equity_feature_contracts.inputs import I64_MAX
from equity_feature_io_contracts import (
    ComponentFactory, ConfigValue, CredentialProvider, FactoryError, FactoryErrorCode,
    PublicConfig, SinkCandidate, SinkRequirements, SourceCandidate,
)

_T = TypeVar("_T")
_S = TypeVar("_S", bound=SourceCandidate)
_K = TypeVar("_K", bound=SinkCandidate)


def _config(config: PublicConfig) -> PublicConfig:
    if not isinstance(config, Mapping):
        raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
    result: dict[str, ConfigValue] = {}
    try:
        for key, value in config.items():
            if type(key) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) is None:
                raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
            if any(part in key for part in ("password", "secret", "credential", "token", "api_key")) or key in ("module", "import", "class_path", "callable"):
                raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
            if type(value) not in (str, int, float, bool, type(None)) or (type(value) is float and not math.isfinite(value)):
                raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
            if key in result:
                raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
            result[key] = value
    except Exception:
        raise FactoryError(FactoryErrorCode.INVALID_CONFIG) from None
    return MappingProxyType(result)


def _identifier(identifier: str) -> None:
    if type(identifier) is not str or re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", identifier) is None:
        raise FactoryError(FactoryErrorCode.INVALID_ID)


class _Registry(Generic[_T]):
    def __init__(self) -> None:
        self._factories: dict[str, ComponentFactory[_T]] = {}

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def __repr__(self) -> str:
        return type(self).__name__ + repr(self.ids)

    def register(self, identifier: str, factory: ComponentFactory[_T]) -> None:
        _identifier(identifier)
        if identifier in self._factories:
            raise FactoryError(FactoryErrorCode.DUPLICATE)
        try:
            version = factory.protocol_version
        except Exception:
            raise FactoryError(FactoryErrorCode.INCOMPATIBLE_VERSION) from None
        if type(version) is not str or version != "1":
            raise FactoryError(FactoryErrorCode.INCOMPATIBLE_VERSION)
        self._factories[identifier] = factory

    def _create(self, identifier: str, config: PublicConfig, credentials: CredentialProvider) -> _T:
        _identifier(identifier)
        if identifier not in self._factories:
            raise FactoryError(FactoryErrorCode.UNKNOWN)
        factory = self._factories[identifier]
        # Recheck mutable caller-owned factory metadata on each resolution.
        try:
            if type(factory.protocol_version) is not str or factory.protocol_version != "1":
                raise FactoryError(FactoryErrorCode.INCOMPATIBLE_VERSION)
        except Exception:
            raise FactoryError(FactoryErrorCode.INCOMPATIBLE_VERSION) from None
        supplied = _config(config)
        try:
            validated = _config(factory.validate_config(supplied))
        except Exception:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG) from None
        try:
            return factory.create(validated, credentials)
        except Exception:
            raise FactoryError(FactoryErrorCode.CONSTRUCTION_FAILED) from None


def admit_source(instance: _S, request: AcquisitionRequest, *, live: bool = False) -> _S:
    try:
        require_adapter_capability(instance.capabilities(), request, live=live)
        operation = getattr(instance, "stream_batches" if live else "iter_batches", None)
        if not callable(operation):
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
    except Exception:
        raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY) from None
    return instance


def admit_sink(instance: _K, requirements: SinkRequirements) -> _K:
    if type(requirements) is not SinkRequirements:
        raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
    # Frozen v1 compatibility admission; backend semantics need conformance.
    supported = ("1", "efio-json1", "efio-key1", "efio-content1", "0.0.4a4", "1", "v1")
    requested = (requirements.protocol_version, requirements.codec_version,
                 requirements.identity_version, requirements.digest_version,
                 requirements.canonical_package_version, requirements.canonical_schema_version,
                 requirements.math_policy_version)
    if requested != supported:
        raise FactoryError(FactoryErrorCode.INCOMPATIBLE_VERSION)
    try:
        caps = instance.capabilities()
        versions = (caps.protocol_versions, caps.codec_versions, caps.identity_versions,
                    caps.digest_versions, caps.canonical_package_versions,
                    caps.canonical_schema_versions, caps.math_policy_versions)
        for offered, wanted in zip(versions, requested, strict=True):
            if type(offered) is not tuple or not offered or any(type(x) is not str or not x.strip() for x in offered) or len(set(offered)) != len(offered) or wanted not in offered:
                raise FactoryError(FactoryErrorCode.INCOMPATIBLE_VERSION)
        if type(caps.visibility) is not str or type(caps.writer_mode) is not str or caps.visibility not in ("manifest_last", "transactional") or caps.writer_mode not in ("single_writer", "serialized_writer", "conflict_safe_multi_writer"):
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
        if requirements.visibility is not None and caps.visibility != requirements.visibility:
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
        if requirements.writer_mode is not None and caps.writer_mode != requirements.writer_mode:
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
        if any(type(flag) is not bool or not flag for flag in (caps.supports_lookup, caps.supports_abort, caps.supports_read)):
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
        positive = (caps.reservation_retention_ns, caps.max_results, caps.max_chunk_bytes, caps.max_total_bytes)
        nonnegative = (caps.max_result_cells, caps.max_evidence_rows)
        if any(type(x) is not int or not 1 <= x <= I64_MAX for x in positive) or any(type(x) is not int or not 0 <= x <= I64_MAX for x in nonnegative):
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
        if caps.max_chunk_bytes > caps.max_total_bytes:
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
        minimums = (requirements.reservation_retention_ns, requirements.max_results,
                    requirements.max_chunk_bytes, requirements.max_total_bytes,
                    requirements.max_result_cells, requirements.max_evidence_rows)
        if any(offered < wanted for offered, wanted in zip(positive + nonnegative, minimums, strict=True)):
            raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY)
    except FactoryError as error:
        raise FactoryError(error.code) from None
    except Exception:
        raise FactoryError(FactoryErrorCode.UNSUPPORTED_CAPABILITY) from None
    return instance


class SourceRegistry(_Registry[_S]):
    def resolve(self, identifier: str, config: PublicConfig, credentials: CredentialProvider,
                request: AcquisitionRequest, *, live: bool = False) -> _S:
        return admit_source(self._create(identifier, config, credentials), request, live=live)


class SinkRegistry(_Registry[_K]):
    def resolve(self, identifier: str, config: PublicConfig, credentials: CredentialProvider,
                requirements: SinkRequirements) -> _K:
        return admit_sink(self._create(identifier, config, credentials), requirements)
