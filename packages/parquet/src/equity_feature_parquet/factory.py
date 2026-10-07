"""Explicit local configuration; no discovery, credential consumption or registration."""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from equity_feature_io_contracts import (
    ConfigValue, CredentialProvider, FactoryError, FactoryErrorCode, PublicConfig, SinkRequirements,
)

from .sink import DEFAULT_LIMITS, ParquetSink

_BOUNDS = ("max_results", "max_chunk_bytes", "max_total_bytes", "max_result_cells", "max_evidence_rows")


class ParquetSinkFactory:
    @property
    def protocol_version(self) -> str:
        return "1"

    def validate_config(self, config: PublicConfig) -> PublicConfig:
        try:
            allowed = {"root", "destination_scope", "max_physical_bytes", "max_control_bytes", "caller_committed_at_ns", *_BOUNDS}
            if set(config) - allowed or type(config.get("root")) is not str or type(config.get("destination_scope")) is not str:
                raise ValueError("invalid configuration")
            root = config["root"]
            scope = config["destination_scope"]
            assert isinstance(root, str) and isinstance(scope, str)
            if not root.strip() or "://" in root or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in root):
                raise ValueError("invalid root")
            validated: dict[str, ConfigValue] = dict(config)
            self._create(validated)  # Constructor validates only; no namespace creation or credential access.
            return MappingProxyType(validated)
        except Exception:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG) from None

    @staticmethod
    def _int(config: PublicConfig, name: str, default: int) -> int:
        value = config.get(name, default)
        if type(value) is not int:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        return value

    def _create(self, config: PublicConfig) -> ParquetSink:
        root, scope = config["root"], config["destination_scope"]
        if type(root) is not str or type(scope) is not str:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        bounds = {name: self._int(config, name, getattr(DEFAULT_LIMITS, name)) for name in _BOUNDS}
        commit_time = config.get("caller_committed_at_ns")
        if commit_time is not None and type(commit_time) is not int:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        limits = SinkRequirements(max_results=bounds["max_results"], max_chunk_bytes=bounds["max_chunk_bytes"],
                                  max_total_bytes=bounds["max_total_bytes"], max_result_cells=bounds["max_result_cells"],
                                  max_evidence_rows=bounds["max_evidence_rows"])
        return ParquetSink(Path(root), scope, limits=limits,
                           max_physical_bytes=self._int(config, "max_physical_bytes", 67108864),
                           max_control_bytes=self._int(config, "max_control_bytes", 33554432),
                           caller_committed_at_ns=commit_time)

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> ParquetSink:
        return self._create(self.validate_config(config))
