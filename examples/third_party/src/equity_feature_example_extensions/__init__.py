"""Trusted local synthetic extensions; importing creates no registry or instance."""
from .source import ExampleSource, example_request
from .sink import ExampleSink
from .factories import SourceFactory, SinkFactory

__version__ = "0.1.0a0"
__all__ = ["__version__", "ExampleSource", "ExampleSink", "SourceFactory", "SinkFactory", "example_request"]
