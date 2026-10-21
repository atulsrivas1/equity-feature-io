"""Explicit canonical-result -> existing sink -> verified readback command.

This command writes only when explicitly invoked. No numerical calculation or
source DB query occurs. Request a resource window before qualification runs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from equity_feature_duckdb.ef1 import separate_output_path
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import decode_result, encode_result, prepare_publication, publish


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="Existing canonical SDK result bytes")
    parser.add_argument("output", type=Path, help="New separate local output DuckDB")
    parser.add_argument("--source-path", type=Path, action="append", default=[],
                        help="Every actual input database/file path, for alias refusal")
    parser.add_argument("--destination-scope", required=True)
    parser.add_argument("--generation-id", required=True, help="Reuse unchanged for retries")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--partition-id", required=True)
    args = parser.parse_args()
    # Include the result input itself: it must never be bootstrapped as a sink.
    output = separate_output_path(args.output, (args.result.resolve(), *args.source_path))
    maximum = 1048576
    with args.result.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        parser.error("Canonical result exceeds example bound")
    result = decode_result(data)
    limits = SinkRequirements(max_results=1, max_chunk_bytes=maximum,
        max_total_bytes=maximum, max_result_cells=3, max_evidence_rows=128)
    envelope = prepare_publication((result,), destination_scope=args.destination_scope,
        generation_id=args.generation_id, job_id=args.job_id, partition_id=args.partition_id,
        limits=limits)
    with DuckDBSink(output, args.destination_scope, limits=limits) as sink:
        receipt = publish(sink, envelope, (result,))
        restored = sink.read(receipt)
        if len(restored) != 1 or encode_result(restored[0]) != encode_result(result):
            raise RuntimeError("Canonical result readback mismatch")
    print("Verified canonical result", receipt.idempotency_key, receipt.content_sha256)


if __name__ == "__main__":
    main()
