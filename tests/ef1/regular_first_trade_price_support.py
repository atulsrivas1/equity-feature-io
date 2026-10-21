"""Read-only independent regular first-trade literals; no expected result generation."""
import hashlib
import json
from pathlib import Path
from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, CanonicalBatch, Column, ContractError, Coverage, DataKind, ErrorCode,
    InputScope, IntervalCoverage, PriceUnit, SourceBinding,
)
from equity_feature_duckdb.regular_first_trade_price import RegularFirstTradePriceInputs, make_regular_first_trade_price_batch

PACKET_SHA = "e1835d416a09bd65fce59612323d23c241fe81dcb8493170002e2c3eadffe531"


def packets():
    raw = Path(__file__).with_name("regular_first_trade_price_contract_packets.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKET_SHA
    oracle = json.loads(raw)
    return oracle["outcome_cases"] + oracle["refusal_cases"]


def original_batch(raw, *, convert=True, trace=None):
    if raw is None:
        return None
    if trace is not None: trace.append('transport_schema_admission')
    if raw["schema_version"] != "1":
        raise ContractError(ErrorCode.INCOMPATIBLE_VERSION, "Original transport schema mismatch")
    metadata = dict(raw["metadata"])
    for name, cls in (("source", SourceBinding), ("coverage", Coverage),
                      ("adjustment", AdjustmentSpec), ("price_unit", PriceUnit), ("scope", InputScope)):
        if trace is not None: trace.append(cls.__name__ + '_constructor')
        metadata[name] = None if metadata[name] is None else cls(**metadata[name])
    metadata["interval_coverage"] = tuple(
        IntervalCoverage(**{**v, "coverage": Coverage(**v["coverage"])})
        for v in metadata["interval_coverage"])
    if trace is not None: trace.append('BatchMetadata_constructor')
    metadata = BatchMetadata(**metadata)
    columns = raw["columns"]
    if len({len(c["values"]) for c in columns}) > 1:
        raise AssertionError("Original input columns are not rectangular")
    if not convert:
        if trace is not None: trace.append('CanonicalBatch_constructor')
        return CanonicalBatch(DataKind(raw["kind"]),
            tuple(Column(c["name"], tuple(c["values"])) for c in columns), metadata)
    return make_regular_first_trade_price_batch(DataKind(raw["kind"]), tuple(c["name"] for c in columns),
        tuple(zip(*(c["values"] for c in columns))), metadata=metadata)


def packet_inputs(packet):
    packet = packet["request"]
    if len(packet["role_slots"]) != 3:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly three declared roles required")
    slots = tuple(original_batch(slot["batch"]) for slot in packet["role_slots"])
    return RegularFirstTradePriceInputs(*slots, tuple("unavailable" if b is None else "synthetic" for b in slots))
