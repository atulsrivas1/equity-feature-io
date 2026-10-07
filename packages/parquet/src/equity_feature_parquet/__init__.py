"""Optional local Parquet generation backend; no registration or commands."""
from .sink import ParquetSink
from .factory import ParquetSinkFactory

__version__ = "0.1.0a1"
__all__ = ["ParquetSink", "ParquetSinkFactory", "__version__"]
