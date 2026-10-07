"""Explicit experimental composition interfaces; no storage operations."""

from .factories import (
    ComponentFactory, ConfigValue, CredentialProvider, FactoryError, FactoryErrorCode, PublicConfig, SinkCandidate, SinkCapabilitiesView, SinkRequirements, SourceCandidate
)

from .publication import (
    AbortOutcome, ArtifactReference, CompletionReceipt, FeatureHeader, PublicationEnvelope, PublicationIdentity, PublicationState, PublicationStatus, ResultDescriptor, ResultSink, SinkCapabilities, SinkError, SinkErrorCode, WriteSession
)

__version__ = "0.1.0a2"
__all__ = ['__version__', 'ComponentFactory', 'ConfigValue', 'CredentialProvider', 'FactoryError', 'FactoryErrorCode', 'PublicConfig', 'SinkCandidate', 'SinkCapabilitiesView', 'SinkRequirements', 'SourceCandidate', 'AbortOutcome', 'ArtifactReference', 'CompletionReceipt', 'FeatureHeader', 'PublicationEnvelope', 'PublicationIdentity', 'PublicationState', 'PublicationStatus', 'ResultDescriptor', 'ResultSink', 'SinkCapabilities', 'SinkError', 'SinkErrorCode', 'WriteSession']
