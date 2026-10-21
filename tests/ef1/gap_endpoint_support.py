"""Read-only independent endpoint literals; no expected result generation."""
import hashlib
import json
from pathlib import Path
from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, CanonicalBatch, Column, Coverage, DataKind,
    InputScope, IntervalCoverage, PriceUnit, SourceBinding,
)
from equity_feature_duckdb.gap_endpoint import GapEndpointInputs, make_gap_endpoint_batch

PACKET_SHA = "751cd98fd7951aa7c2d4394d9a5fee87e184d9d484d9f43d4de4983b7333f40f"


def packets():
    raw = Path(__file__).with_name("gap_endpoint_contract_packets.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKET_SHA
    return json.loads(raw)["packets"]


def original_batch(raw, *, convert=True):
    if raw is None:
        return None
    metadata = dict(raw["metadata"])
    for name, cls in (("source", SourceBinding), ("coverage", Coverage),
                      ("adjustment", AdjustmentSpec), ("price_unit", PriceUnit), ("scope", InputScope)):
        metadata[name] = None if metadata[name] is None else cls(**metadata[name])
    metadata["interval_coverage"] = tuple(
        IntervalCoverage(**{**v, "coverage": Coverage(**v["coverage"])})
        for v in metadata["interval_coverage"])
    metadata = BatchMetadata(**metadata)
    columns = raw["columns"]
    if not convert:
        return CanonicalBatch(DataKind(raw["kind"]),
            tuple(Column(c["name"], tuple(c["values"])) for c in columns), metadata)
    return make_gap_endpoint_batch(DataKind(raw["kind"]), tuple(c["name"] for c in columns),
        tuple(zip(*(c["values"] for c in columns))), metadata=metadata)


def packet_inputs(packet):
    slots = tuple(original_batch(slot["batch"]) for slot in packet["role_slots"])
    return GapEndpointInputs(*slots, tuple("unavailable" if b is None else "synthetic" for b in slots))


def causal_packets():
    # Root-approved two-quality-leaf correction; original bytes remain immutable.
    raw = Path(__file__).with_name("gap_endpoint_causal_contract_packets.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "698994acf9d324d3c94334b02f307b2997ce320eb397d7f7cb5f8ea359d4f239"
    return json.loads(raw)["packets"]
