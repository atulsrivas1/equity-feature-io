"""Lossless supplied money-flow inputs; no multiplier, OBV, A/D line or CMF mathematics.

Maps SUPPLIED OHLCV bars (volume in the config's declared adjustment basis) into the R17
governed-grid BAR delivery of the frozen ef2-mf1 contract (core
docs/ef2/MONEYFLOW_RETRACEMENT_CONTRACT_PROPOSAL.md). Nothing is derived, filled or inferred.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, cast

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec,
    ContractError, Coverage, DataKind, ErrorCode, InputScope, IntervalCoverage, Parameter,
    PriceUnit, SessionSpec, SourceBinding, WindowSpec, validate_batch,
)
from equity_feature_contracts.inputs import Cell

ROLES = ("bars",)
_ORIGINS = frozenset(("synthetic", "duckdb_backed_observed", "unavailable"))
MAPPING_VERSION = "ef2-money-flow-map1"
POLICY_VERSION = "ef2-mf1"
ALGORITHM_VERSION = "ef2-money-flow-v1"
CONFIG_IDENTITY = "ef2.money_flow"
CONTEXT_SCHEMA = "equity-features.intraday-context.v1"  # the accepted R17 context codec, unchanged
FEATURE_IDS = ("intraday.ad_line", "intraday.cmf", "intraday.obv")
# Columns of a supplied bar row; open is not part of the money-flow contract and is never invented.
BAR_COLUMNS = ("instrument_id", "session_id", "start_ns", "end_ns", "high", "low", "close",
               "volume", "known_at_ns")


def make_money_flow_batch(column_order: tuple[str, ...], rows: tuple[tuple[Cell, ...], ...], *,
                          metadata: BatchMetadata) -> CanonicalBatch:
    """Convert exact supplied rectangular BAR cells (volume included), retaining order and metadata.

    No sorting, filtering, field filling, unit or basis conversion, volume inference or
    timestamp inference occurs. Admission (grid, order, duplicates, cutoff, readiness) belongs
    to the pure producer; generic canonical validation may refuse an invalid original row first.
    """
    if (type(column_order) is not tuple or any(type(name) is not str for name in column_order)
            or type(rows) is not tuple
            or any(type(row) is not tuple or len(row) != len(column_order) for row in rows)
            or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied money-flow bar rectangle required")
    result = CanonicalBatch(DataKind.BAR, tuple(Column(name, tuple(row[i] for row in rows))
                                                for i, name in enumerate(column_order)), metadata)
    validate_batch(result, required_fields=())
    return result


def make_slot_coverage(index: int, start_ns: int, end_ns: int, *, expected: int | None,
                       observed: int, complete: bool) -> IntervalCoverage:
    """Declare the per-slot coverage entry `slot:<index>` of one governed grid slot, as supplied."""
    if type(index) is not int or index < 0:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Nonnegative governed slot index required")
    return IntervalCoverage(f"slot:{index}", start_ns, end_ns, Coverage(expected, observed, complete))


def make_money_flow_config(*, instrument_id: str, calendar_id: str, grid_id: str, revision: str,
                           sessions: Sequence[SessionSpec], runs: Sequence[tuple[str, int, int, int]],
                           anchor_index: int, target_index: int, mode: str,
                           availability: AvailabilitySpec, adjustment: AdjustmentSpec,
                           price_unit: PriceUnit, cmf_period: int | None = None,
                           evidence_limit: int = 0, policy_version: str = POLICY_VERSION) -> ConfigSpec:
    """Build the ef2.money_flow ConfigSpec from explicit caller-supplied selection.

    Envelope (the contract names the parameters but not their wire layout; verified byte-identical to the
    library build_money_flow_config): the R17
    intraday envelope unchanged (closed canonical context chunks, sha256, schema) plus
    policy_version, evidence_limit and, only when supplied, cmf_period. There is no default
    period or evidence limit. Every range, mode, anchor/target and vocabulary check
    (invalid_config, incompatible_version) belongs to the pure decoder, so malformed values
    pass through unchanged. runs are (session_id, start_ns, step_ns, count).
    """
    if (type(sessions) not in (tuple, list) or any(type(s) is not SessionSpec for s in sessions) or not sessions
            or type(runs) not in (tuple, list) or any(type(r) is not tuple or len(r) != 4 for r in runs)
            or not runs or (cmf_period is not None and type(cmf_period) is not int)):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Explicit sessions, runs and integer parameters required")
    context = json.dumps({
        "schema": CONTEXT_SCHEMA, "instrument_id": instrument_id, "calendar_id": calendar_id,
        "grid_id": grid_id, "revision": revision, "sessions": [asdict(s) for s in sessions],
        "runs": [{"session_id": r[0], "start_ns": r[1], "step_ns": r[2], "count": r[3]} for r in runs],
        "anchor_index": anchor_index, "target_index": target_index, "mode": mode,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    chunks = tuple(context[i:i + 4096] for i in range(0, len(context), 4096))
    params = [Parameter("policy_version", policy_version), Parameter("evidence_limit", evidence_limit),
              Parameter("context_schema", CONTEXT_SCHEMA),
              Parameter("context_sha256", hashlib.sha256(context.encode("ascii")).hexdigest()),
              Parameter("context_chunks", len(chunks))]
    params += [Parameter(f"context_{i:03}", chunk) for i, chunk in enumerate(chunks)]
    if cmf_period is not None:
        params.append(Parameter("cmf_period", cmf_period))
    target_id = runs[-1][0]
    target = next((s for s in sessions if s.session_id == target_id), sessions[-1])
    return ConfigSpec(CONFIG_IDENTITY, ALGORITHM_VERSION, tuple(params), target,
                      WindowSpec(len(sessions), target.session_id, tuple(s.session_id for s in sessions),
                                 "completed_eod"), availability, adjustment, price_unit)


@dataclass(frozen=True)
class MoneyFlowInputs:
    """One nullable `bars` role holding the ordered BAR chunks of the governed grid.

    `bars=None` is missing delivery. Origins are explicit caller declarations, not
    capability or rights evidence. Nothing here orders, merges or repairs chunks.
    """
    bars: tuple[CanonicalBatch, ...] | None = None
    provenance: tuple[str, ...] = ("unavailable",)

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 1:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly one money-flow origin required")
        origin = self.provenance[0]
        if type(origin) is not str or origin not in _ORIGINS or (self.bars is None) != (origin == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
        if self.bars is not None:
            if type(self.bars) is not tuple:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete tuple of BAR chunks required")
            for batch in self.bars:
                if type(batch) is not CanonicalBatch or batch.kind is not DataKind.BAR:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Money-flow role requires BAR batches")
                validate_batch(batch, required_fields=())
            if len({b.metadata.source.input_id for b in self.bars}) != len(self.bars):
                raise ContractError(ErrorCode.DUPLICATE, "Distinct money-flow chunk input IDs required")
            if len({b.metadata.namespace for b in self.bars}) > 1:
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One money-flow namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return ROLES

    @property
    def slots(self) -> tuple[tuple[CanonicalBatch, ...] | None, ...]:
        return (self.bars,)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return () if self.bars is None else self.bars


__all__ = ["MoneyFlowInputs", "make_money_flow_batch", "make_slot_coverage", "make_money_flow_config",
           "BAR_COLUMNS", "FEATURE_IDS", "MAPPING_VERSION", "POLICY_VERSION", "ALGORITHM_VERSION",
           "CONFIG_IDENTITY", "CONTEXT_SCHEMA"]


# Original synthetic supplied slots keyed by the contract's own fixture ids (inputs only: no
# expected values). Slot rows are [state, close, high, low, volume, known_at]; the compact
# states are priced, empty, absent, gap, unknown, future and null_volume. features is the
# selected output subset of the fixture (the contract's M34 selects two).
_SYNTHETIC = json.loads('''{
    "M01": {"n":1,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1050,1100,1000,200,50]]},
    "M02": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1050,1100,1000,200,50]]},
    "M03": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1100,900,100,50],["priced",1010,1050,1000,50,50]]},
    "M04": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1100,900,100,50],["priced",1010,1050,1000,50,50],["priced",1020,1080,1010,70,50]]},
    "M05": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["priced",1010,1020,1000,20,50],["priced",1005,1015,1000,30,50],["priced",1005,1010,1000,40,50],["priced",1007,1012,1003,50,50]]},
    "M06": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,100,50],["priced",1000,1010,990,100,50],["priced",1000,1010,990,100,50],["priced",1000,1010,990,100,50]]},
    "M07": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1005,985,100,50],["priced",1001,1006,986,200,50],["priced",1002,1007,987,300,50],["priced",1003,1008,988,400,50]]},
    "M08": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1015,995,100,50],["priced",999,1014,994,200,50],["priced",998,1013,993,300,50],["priced",997,1012,992,400,50]]},
    "M09": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,1,50],["priced",1010,1020,1000,2,50],["priced",1010,1030,1000,4,50],["priced",1000,1010,990,8,50]]},
    "M10": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1100,1100,1000,100,50],["priced",1000,1100,1000,100,50]]},
    "M11": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1100,1100,1000,30,50],["priced",1100,1100,1000,70,50]]},
    "M12": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1100,1000,30,50],["priced",1000,1100,1000,70,50]]},
    "M13": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1100,1100,1000,100,50],["priced",1050,1050,1050,100,50],["priced",1100,1100,1000,100,50]]},
    "M14": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1000,1000,5,50],["priced",1001,1001,1001,6,50],["priced",1001,1001,1001,7,50]]},
    "M15": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1010,1030,1000,7,50],["priced",1010,1030,1000,11,50],["priced",1020,1030,1000,13,50]]},
    "M16": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1010,1030,1000,9223372036854775807,50],["priced",1020,1030,1000,9223372036854775803,50],["priced",1010,1030,1000,999999999999999989,50]]},
    "M17": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["empty",null,null,null,null,50],["priced",1010,1030,1000,30,50]]},
    "M18": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["empty",null,null,null,null,50],["priced",1000,1010,990,10,50],["priced",1010,1030,1000,30,50]]},
    "M19": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["empty",null,null,null,null,50],["empty",null,null,null,null,50],["empty",null,null,null,null,50]]},
    "M20": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["empty",null,null,null,null,50],["empty",null,null,null,null,50],["empty",null,null,null,null,50]]},
    "M21": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1050,1100,900,10,50],["empty",null,null,null,null,50],["priced",1050,1100,1000,30,50],["empty",null,null,null,null,50]]},
    "M22": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1100,900,1000,50],["priced",1100,1100,1000,10,50],["priced",1000,1100,1000,20,50],["priced",1050,1100,1000,30,50]]},
    "M23": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,500,50],["priced",1010,1020,1000,20,50],["priced",1005,1015,1000,30,50]]},
    "M24": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["absent",null,null,null,null,null],["priced",1010,1020,1000,30,50],["priced",1012,1030,1002,40,50]]},
    "M25": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["absent",null,null,null,null,null],["priced",1010,1020,1000,30,50]]},
    "M26": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["gap",null,null,null,null,null],["priced",1010,1020,1000,30,50]]},
    "M27": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["unknown",null,null,null,null,null],["priced",1010,1020,1000,30,50]]},
    "M28": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["future",null,null,null,null,150],["priced",1010,1020,1000,30,50]]},
    "M29": {"n":4,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["absent",null,null,null,null,null],["future",null,null,null,null,150],["gap",null,null,null,null,null]]},
    "M30": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["gap",null,null,null,null,null],["priced",1000,1010,990,10,50]]},
    "M31": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["future",null,null,null,null,150],["priced",1000,1010,990,10,50],["priced",1015,1020,1000,20,50]]},
    "M32": {"n":1,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,1,50],["priced",1001,1021,991,9223372036854775807,50]]},
    "M33": {"n":1,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,1,50],["priced",999,1019,989,9223372036854775807,50],["priced",998,1018,988,1,50]]},
    "M34": {"n":1,"features":["intraday.ad_line","intraday.cmf"],"slots":[["priced",1000,1010,990,1,50],["priced",1001,1021,991,9223372036854775807,50],["priced",1002,1022,992,1,50]]},
    "M36": {"n":3,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,10,50],["null_volume",null,null,null,null,null],["priced",1010,1030,1000,30,50]]},
    "M35": {"n":2,"features":["intraday.ad_line","intraday.cmf","intraday.obv"],"slots":[["priced",1000,1010,990,1,50],["priced",1001,1011,991,9223372036854775807,50],["priced",1002,1012,992,9223372036854775807,50],["priced",1001,1011,991,9223372036854775807,50],["priced",1000,1010,990,9223372036854775807,50]]}
}''')
SYNTHETIC_MONEY_FLOW_CASES = tuple(_SYNTHETIC)
_STEP_NS = 10
_SCALE = 2
_CUTOFF_NS = 100  # the contract's K


def _case(case_id: str) -> dict[str, Any]:
    if type(case_id) is not str or case_id not in _SYNTHETIC:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic money-flow case")
    return cast(dict[str, Any], _SYNTHETIC[case_id])


def synthetic_money_flow_features(case_id: str) -> tuple[str, ...]:
    """The output subset the contract fixture selects (a selection, not an expected value)."""
    return tuple(_case(case_id)["features"])


def synthetic_money_flow_config(case_id: str) -> ConfigSpec:
    """Detached synthetic ef2.money_flow config for a contract fixture (reset epoch, anchor slot 0).

    Entity X/S in namespace SYN, session [0, 100), ten-ns grid of t+1 slots, K = evaluation = 100,
    raw basis, USD scale 2. cmf_period is the fixture N and is present only when intraday.cmf is
    selected. These grid and entity choices are not contract-specified (listed for the worker).
    """
    case = _case(case_id)
    count = len(case["slots"])
    return make_money_flow_config(
        instrument_id="X", calendar_id="synthetic-calendar", grid_id="ten-ns-grid", revision="revision1",
        sessions=(SessionSpec("SYN", "S", 0, 100, "UTC"),), runs=(("S", 0, _STEP_NS, count),),
        anchor_index=0, target_index=count - 1, mode="reset",
        availability=AvailabilitySpec(_CUTOFF_NS, _CUTOFF_NS, _CUTOFF_NS), adjustment=AdjustmentSpec(),
        price_unit=PriceUnit(_SCALE, "USD"),
        cmf_period=case["n"] if "intraday.cmf" in case["features"] else None)


def synthetic_money_flow_fixture(case_id: str, *, empty_form: str = "row") -> MoneyFlowInputs:
    """Original synthetic OHLCV slots of one contract fixture as one BAR chunk; nothing is computed.

    empty (coverage-proven zero volume) is delivered as a zero-volume row with null OHLC and
    complete per-slot coverage (empty_form="row", default) or as complete per-slot coverage of
    expected 0 without a row (empty_form="coverage"); the contract allows both for M17 to M21.
    unknown and future slots carry a zero-volume null-OHLC row with known_at null or 150 (the
    contract gives no prices for them); null_volume is a null-OHLC row with null volume known at 50
    (the compact null known_at there only means unstated). gap is a declared incomplete slot
    without a row; absent has neither row nor coverage entry.
    """
    if empty_form not in ("row", "coverage"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "empty_form must be row or coverage")
    case = _case(case_id)
    slots = case["slots"]
    rows: list[tuple[Cell, ...]] = []
    entries: list[IntervalCoverage] = []
    for index, (state, close, high, low, volume, known) in enumerate(slots):
        start, end = index * _STEP_NS, (index + 1) * _STEP_NS
        if state == "priced":
            rows.append(("X", "S", start, end, high, low, close, volume, known))
            entries.append(make_slot_coverage(index, start, end, expected=1, observed=1, complete=True))
        elif state == "empty" and empty_form == "coverage":
            entries.append(make_slot_coverage(index, start, end, expected=0, observed=0, complete=True))
        elif state in ("empty", "unknown", "future"):
            rows.append(("X", "S", start, end, None, None, None, 0, known))
            entries.append(make_slot_coverage(index, start, end, expected=1, observed=1, complete=True))
        elif state == "null_volume":
            rows.append(("X", "S", start, end, None, None, None, None, 50))
            entries.append(make_slot_coverage(index, start, end, expected=1, observed=1, complete=True))
        elif state == "gap":
            entries.append(make_slot_coverage(index, start, end, expected=1, observed=0, complete=False))
        elif state != "absent":
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Unknown compact slot state")
    count = len(slots)
    if len(entries) == count:
        expected = sum(cast(int, e.coverage.expected) for e in entries)
        coverage = Coverage(expected, len(rows), all(e.coverage.complete for e in entries) and expected == len(rows))
    else:
        coverage = Coverage(count, len(rows), False)
    metadata = BatchMetadata(
        "SYN", SourceBinding("SYN-BARS", "snap1", MAPPING_VERSION, "bars-000"), coverage,
        PriceUnit(_SCALE, "USD"), scope=InputScope(0, count * _STEP_NS, "synthetic-v1"),
        interval_coverage=tuple(entries))
    batch = make_money_flow_batch(BAR_COLUMNS, tuple(rows), metadata=metadata)
    return MoneyFlowInputs((batch,), ("synthetic",))


__all__ += ["SYNTHETIC_MONEY_FLOW_CASES", "synthetic_money_flow_features",
            "synthetic_money_flow_config", "synthetic_money_flow_fixture"]
