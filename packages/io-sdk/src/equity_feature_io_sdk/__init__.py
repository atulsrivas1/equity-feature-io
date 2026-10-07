"""Explicit experimental composition interfaces; no storage operations."""

from .factories import (
    SinkRegistry, SourceRegistry, admit_sink, admit_source
)

from .codec import (
    content_digest, decode_envelope, decode_receipt, decode_result, descriptor, encode_envelope, encode_receipt, encode_result, idempotency_key
)
from .conformance import ConformanceCase, SinkConformanceReport, qualify_sink
from .publication import Cancellation, envelope_requirements, prepare_publication, publish, verify_content, verify_receipt

__version__ = "0.1.0a2"
__all__ = ['__version__', 'SinkRegistry', 'SourceRegistry', 'admit_sink', 'admit_source', 'content_digest', 'decode_envelope', 'decode_receipt', 'decode_result', 'descriptor', 'encode_envelope', 'encode_receipt', 'encode_result', 'idempotency_key', 'ConformanceCase', 'SinkConformanceReport', 'qualify_sink', 'Cancellation', 'envelope_requirements', 'prepare_publication', 'publish', 'verify_content', 'verify_receipt']
