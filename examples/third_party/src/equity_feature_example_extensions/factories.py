"""Explicit public factories; config is scalar and credentials are separate."""
from equity_feature_io_contracts import CredentialProvider, PublicConfig
from .source import ExampleSource
from .sink import ExampleSink


class SourceFactory:
    protocol_version = "1"

    def validate_config(self, config: PublicConfig) -> PublicConfig:
        if set(config) != {"namespace"} or config["namespace"] != "demo":
            raise ValueError("unsupported synthetic source config")
        return config

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> ExampleSource:
        self.validate_config(config)
        return ExampleSource()


class SinkFactory:
    protocol_version = "1"

    def validate_config(self, config: PublicConfig) -> PublicConfig:
        if set(config) != {"destination_scope"} or config["destination_scope"] != "synthetic-conformance":
            raise ValueError("unsupported synthetic sink config")
        return config

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> ExampleSink:
        self.validate_config(config)
        return ExampleSink()
