"""Optional acquisition boundary; never imported by core calculations."""
from .resolver import (
    CatalogConfig, FilePin, ResolvedPartition, ResolvedSource,
    SourceSelection, resolve_source,
)

from .mapping import (MappingPolicy, RowOccurrence, PriceConversion, MappingReport,
                      MappedSource, map_columns, parse_utc_ns)

from .reader import (CoverageAssertion, ReadConfig, ReadMetrics, ReadResult,
                     DuckDBHistoricalAdapter)

from .governance import (GovernedCalendar, HistoryPlan, plan_history, make_history_context,
                         ReferenceRequest, ReferenceResolution, resolve_supplied_reference)
from .evidence import VerificationPolicy, FileEvidence, AcquisitionReceipt

__version__ = "0.1.0a8"
__all__ = [
    "CatalogConfig", "FilePin", "ResolvedPartition", "ResolvedSource",
    "SourceSelection", "resolve_source",
    "MappingPolicy", "RowOccurrence", "PriceConversion", "MappingReport",
    "MappedSource", "map_columns", "parse_utc_ns",
    "CoverageAssertion", "ReadConfig", "ReadMetrics", "ReadResult",
    "DuckDBHistoricalAdapter",
    "GovernedCalendar", "HistoryPlan", "plan_history", "make_history_context",
    "ReferenceRequest", "ReferenceResolution", "resolve_supplied_reference",
    "VerificationPolicy", "FileEvidence", "AcquisitionReceipt",
]
