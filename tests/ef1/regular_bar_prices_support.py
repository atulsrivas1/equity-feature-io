"""Read-only independent regular BAR literals; no expected result generation."""
import hashlib
import json
from pathlib import Path
from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, CanonicalBatch, Column, ContractError, Coverage, DataKind, ErrorCode,
    InputScope, IntervalCoverage, PriceUnit, SourceBinding,
)
from equity_feature_duckdb.regular_bar_prices import RegularBarPriceInputs, make_regular_bar_price_batch

PACKET_SHA = "05d5b4815df3fd621993037c84f9d897a32ee84c833715e6ca1f6c4e1473d030"


def packets():
    raw = Path(__file__).with_name("regular_bar_prices_contract_packets.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKET_SHA
    return json.loads(raw)["packets"]


def original_batch(raw, *, convert=True):
    if raw is None:
        return None
    assert raw["schema_version"] == "1"
    metadata = dict(raw["metadata"])
    for name, cls in (("source", SourceBinding), ("coverage", Coverage),
                      ("adjustment", AdjustmentSpec), ("price_unit", PriceUnit), ("scope", InputScope)):
        metadata[name] = None if metadata[name] is None else cls(**metadata[name])
    metadata["interval_coverage"] = tuple(
        IntervalCoverage(**{**v, "coverage": Coverage(**v["coverage"])})
        for v in metadata["interval_coverage"])
    metadata = BatchMetadata(**metadata)
    columns = raw["columns"]
    if len({len(c["values"]) for c in columns}) > 1:
        raise AssertionError("Original input columns are not rectangular")
    if not convert:
        return CanonicalBatch(DataKind(raw["kind"]),
            tuple(Column(c["name"], tuple(c["values"])) for c in columns), metadata)
    return make_regular_bar_price_batch(DataKind(raw["kind"]), tuple(c["name"] for c in columns),
        tuple(zip(*(c["values"] for c in columns))), metadata=metadata)


def packet_inputs(packet):
    if len(packet["role_slots"]) != 3:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly three declared roles required")
    slots = tuple(original_batch(slot["batch"]) for slot in packet["role_slots"])
    return RegularBarPriceInputs(*slots, tuple("unavailable" if b is None else "synthetic" for b in slots))
