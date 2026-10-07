"""Explicit experimental composition interfaces; no storage operations."""

from .factories import (
    ComponentFactory, ConfigValue, CredentialProvider, FactoryError, FactoryErrorCode, PublicConfig, SinkCandidate, SinkCapabilitiesView, SinkRequirements, SourceCandidate
)

__version__ = "0.1.0a1"
__all__ = ['__version__', 'ComponentFactory', 'ConfigValue', 'CredentialProvider', 'FactoryError', 'FactoryErrorCode', 'PublicConfig', 'SinkCandidate', 'SinkCapabilitiesView', 'SinkRequirements', 'SourceCandidate']
