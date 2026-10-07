"""Explicit experimental composition interfaces; no storage operations."""

from .factories import (
    SinkRegistry, SourceRegistry, admit_sink, admit_source
)

__version__ = "0.1.0a1"
__all__ = ['__version__', 'SinkRegistry', 'SourceRegistry', 'admit_sink', 'admit_source']
