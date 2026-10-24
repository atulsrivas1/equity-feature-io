"""Optional DuckDB sink publication of EF4-I2 projection results.

Not imported by `ef4_projections`. Optional dependencies, imported lazily inside `publish_results` only:
`equity-feature-io-contracts`, `equity-feature-io-sdk` and `equity-feature-duckdb-sink` (this repository's packages).
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any


def publish_results(results: Sequence[Any], output_path: Any, *, destination_scope: str, generation_id: str,
                    job_id: str, partition_id: str) -> Any:
    """Publish one complete result per generation to a local DuckDB sink through the SDK publication path and return
    the receipt. The caller reads it back with `DuckDBSink.read(receipt)`; this function computes nothing."""
    from equity_feature_duckdb_sink import DuckDBSink
    from equity_feature_io_contracts import SinkRequirements
    from equity_feature_io_sdk import prepare_publication, publish

    limits = SinkRequirements(max_results=len(results), max_chunk_bytes=1048576, max_total_bytes=10485760,
                              max_result_cells=100000, max_evidence_rows=100000)
    envelope = prepare_publication(tuple(results), destination_scope=destination_scope, generation_id=generation_id,
                                   job_id=job_id, partition_id=partition_id, limits=limits)
    with DuckDBSink(Path(output_path), destination_scope, limits=limits) as sink:
        return publish(sink, envelope, tuple(results))


__all__ = ["publish_results"]
