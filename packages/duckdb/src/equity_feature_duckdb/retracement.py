"""Lossless supplied prior-extrema inputs for the retracement level; no retracement mathematics.

Maps the EXACT integer extremum coefficients (never a rounded float64) of an upstream
extrema owner into the two REFERENCE roles prior_high and prior_low of the frozen
ef2-retrace1 contract (core docs/ef2/MONEYFLOW_RETRACEMENT_CONTRACT_PROPOSAL.md). No level,
range, ratio reduction or default is computed or injected.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError,
    Coverage, DataKind, ErrorCode, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec,
    validate_batch,
)
from equity_feature_contracts.inputs import Cell

ROLES = ("prior_high", "prior_low")
_ORIGINS = frozenset(("synthetic", "duckdb_backed_observed", "unavailable"))
_FACT_KINDS = ("ef2.extremum.high", "ef2.extremum.low")
EXTREMUM_COLUMNS = ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns",
                    "effective_end_ns", "text", "price", "factor_num", "factor_den", "known_at_ns")
MAPPING_VERSION = "ef2-retracement-map1"
POLICY_VERSION = "ef2-retrace1"
ALGORITHM_VERSION = "ef2-retracement-level-v1"
CONFIG_IDENTITY = "ef2.retracement_level"
FEATURE_ID = "retracement.level"


def make_extremum_reference_id(window_set_id: str) -> str:
    """Encode the supplied upstream window-set identity as x1:B(window_set_id).

    B is reversible unpadded base64url of UTF8. Only the supplied identity is encoded; the
    128 codepoint limit and equality across both roles belong to the pure producer.
    """
    if type(window_set_id) is not str or not window_set_id:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Nonempty supplied window set identity required")
    return "x1:" + base64.urlsafe_b64encode(window_set_id.encode("utf-8", errors="surrogatepass")).decode("ascii").rstrip("=")


def make_extremum_batch(rows: tuple[Mapping[str, Cell], ...], *, metadata: BatchMetadata) -> CanonicalBatch:
    """Convert supplied extremum rows (normally exactly one), all eleven original cells each.

    price is the exact integer coefficient at the config PriceUnit scale; factor_num and
    factor_den are the observed slots and required window length of the upstream extremum,
    or null. Nothing is rescaled, converted, rounded, parsed from a float, filled, defaulted
    or checked here; text/snapshot binding, row count, role kind, factor all-or-none and
    the shortfall rules belong to the pure producer. Generic canonical validation may
    refuse an invalid original row first. A zero-row batch is present-empty.
    """
    if (type(rows) is not tuple or type(metadata) is not BatchMetadata
            or any(not isinstance(r, Mapping) or set(r) != set(EXTREMUM_COLUMNS) for r in rows)):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "All eleven original extremum cells required")
    batch = CanonicalBatch(DataKind.REFERENCE, tuple(Column(n, tuple(r[n] for r in rows)) for n in EXTREMUM_COLUMNS),
                           metadata)
    validate_batch(batch, required_fields=())
    return batch


def make_retracement_config(*, direction: str, ratio_num: int, ratio_den: int, session: SessionSpec,
                            availability: AvailabilitySpec,
                            adjustment: AdjustmentSpec, price_unit: PriceUnit, evidence_limit: int = 0,
                            policy_version: str = POLICY_VERSION) -> ConfigSpec:
    """Build the ef2.retracement_level ConfigSpec from the caller's explicit direction and ratio.

    Envelope (the contract lists the five parameters but not their wire layout; verified byte-identical
    to the library build_retracement_config): five flat scalar parameters policy_version, direction, ratio_num, ratio_den, evidence_limit. There is
    no default ratio and no reduction here; reducedness, 0 <= ratio <= 1, direction vocabulary
    and the evidence bound are the pure decoder's (invalid_config), so malformed values pass through.
    """
    return ConfigSpec(CONFIG_IDENTITY, ALGORITHM_VERSION, (
        Parameter("policy_version", policy_version), Parameter("direction", direction),
        Parameter("ratio_num", ratio_num), Parameter("ratio_den", ratio_den),
        Parameter("evidence_limit", evidence_limit)), session,
                      WindowSpec(1, session.session_id, (session.session_id,), "completed_eod"),
                      availability, adjustment, price_unit)


@dataclass(frozen=True)
class RetracementInputs:
    """Two fixed nullable REFERENCE slots, prior_high then prior_low, one extremum row each.

    Origins are explicit caller declarations, not capability or rights evidence. A
    caller-computed or float64-derived extremum must never replace a missing one; deliver
    None (unavailable) instead.
    """
    prior_high: CanonicalBatch | None = None
    prior_low: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable",) * 2

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 2:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly two retracement origins required")
        for batch, origin in zip(self.slots, self.provenance):
            if type(origin) is not str or origin not in _ORIGINS or (batch is None) != (origin == "unavailable"):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
            if batch is not None:
                if type(batch) is not CanonicalBatch or batch.kind is not DataKind.REFERENCE:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Retracement role requires REFERENCE batches")
                validate_batch(batch, required_fields=())
        if len({b.metadata.source.input_id for b in self.batches}) != len(self.batches):
            raise ContractError(ErrorCode.DUPLICATE, "Distinct retracement input IDs required")
        if len({b.metadata.namespace for b in self.batches}) > 1:
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One retracement namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.prior_high, self.prior_low)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(b for b in self.slots if b is not None)


__all__ = ["RetracementInputs", "make_extremum_reference_id", "make_extremum_batch",
           "make_retracement_config", "EXTREMUM_COLUMNS", "FEATURE_ID", "MAPPING_VERSION",
           "POLICY_VERSION", "ALGORITHM_VERSION", "CONFIG_IDENTITY"]


# Original synthetic supplied extrema keyed by the contract's own fixture ids (inputs only:
# no expected values). Sides are [state, price, known_at, [factor_num, factor_den] or null]; the
# compact states are priced, null_price, insufficient, unknown, future, gap, empty_batch, absent.
_SYNTHETIC = json.loads('''{
    "T01": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T02": {"scale":2,"direction":"from_low","ratio":[1,2],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T03": {"scale":2,"direction":"from_high","ratio":[0,1],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T04": {"scale":2,"direction":"from_high","ratio":[1,1],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T05": {"scale":2,"direction":"from_low","ratio":[0,1],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T06": {"scale":2,"direction":"from_low","ratio":[1,1],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T07": {"scale":2,"direction":"from_high","ratio":[1,3],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T08": {"scale":2,"direction":"from_low","ratio":[2,3],"high":["priced",12000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T09": {"scale":2,"direction":"from_high","ratio":[309,500],"high":["priced",10100,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T10": {"scale":0,"direction":"from_high","ratio":[1,4],"high":["priced",120,50,[20,20]],"low":["priced",100,50,[20,20]]},
    "T11": {"scale":6,"direction":"from_low","ratio":[1,2],"high":["priced",100001000,50,[20,20]],"low":["priced",100000000,50,[20,20]]},
    "T12": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",9223372036854775807,50,[20,20]],"low":["priced",1,50,[20,20]]},
    "T13": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",10001,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T14": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",10000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T15": {"scale":2,"direction":"from_low","ratio":[0,1],"high":["priced",10000,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T16": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",10000,50,[20,20]],"low":["priced",12000,50,[20,20]]},
    "T17": {"scale":2,"direction":"from_low","ratio":[1,2],"high":["priced",9999,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T18": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",12000,50,[20,20]],"low":["priced",0,50,[20,20]]},
    "T19": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",-5,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T20": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["absent",null,50,null],"low":["priced",10000,50,[20,20]]},
    "T21": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",12000,50,[20,20]],"low":["absent",null,50,null]},
    "T22": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["absent",null,50,null],"low":["absent",null,50,null]},
    "T23": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["empty_batch",null,50,null],"low":["priced",10000,50,[20,20]]},
    "T24": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["insufficient",null,50,[7,20]],"low":["priced",10000,50,[20,20]]},
    "T25": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["null_price",null,50,[20,20]],"low":["priced",10000,50,[20,20]]},
    "T32": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["null_price",null,50,null],"low":["priced",10000,50,[20,20]]},
    "T26": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["priced",12000,50,[20,20]],"low":["unknown",10000,null,null]},
    "T27": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["future",12000,150,null],"low":["priced",10000,50,[20,20]]},
    "T28": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["gap",12000,50,null],"low":["priced",10000,50,[20,20]]},
    "T29": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["absent",null,50,null],"low":["insufficient",null,50,[3,20]]},
    "T30": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["gap",12000,50,null],"low":["insufficient",null,50,[3,20]]},
    "T31": {"scale":2,"direction":"from_high","ratio":[1,2],"high":["future",5000,150,null],"low":["priced",10000,50,[20,20]]}
}''')
SYNTHETIC_RETRACEMENT_CASES = tuple(_SYNTHETIC)
_CUTOFF_NS = 100  # the contract's K
_WINDOW_SET_ID = "synthetic-window-set"


def _case(case_id: str) -> dict[str, Any]:
    if type(case_id) is not str or case_id not in _SYNTHETIC:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic retracement case")
    return cast(dict[str, Any], _SYNTHETIC[case_id])


def synthetic_retracement_config(case_id: str) -> ConfigSpec:
    """Detached synthetic ef2.retracement_level config for a contract fixture.

    Entity X/S in namespace SYN, session [0, 100), K = evaluation = 100, raw basis, USD at the
    fixture scale, evidence_limit 2 (not contract-specified; both witness rows are cited).
    """
    case = _case(case_id)
    return make_retracement_config(
        direction=case["direction"], ratio_num=case["ratio"][0], ratio_den=case["ratio"][1],
        session=SessionSpec("SYN", "S", 0, 100, "UTC"),
        availability=AvailabilitySpec(_CUTOFF_NS, _CUTOFF_NS, _CUTOFF_NS), adjustment=AdjustmentSpec(),
        price_unit=PriceUnit(case["scale"], "USD"), evidence_limit=2)


def _side(role: int, side: list[Any], scale: int) -> CanonicalBatch | None:
    state, price, known, factor = side
    if state == "absent":
        return None
    metadata_kw: dict[str, Any] = dict(
        price_unit=PriceUnit(scale, "USD"))
    source = SourceBinding("SYN-EXTREMA", "snap1", MAPPING_VERSION, ROLES[role])
    if state == "empty_batch":
        return make_extremum_batch((), metadata=BatchMetadata("SYN", source, Coverage(0, 0, True), **metadata_kw))
    row = {"instrument_id": "X", "session_id": "S", "reference_id": make_extremum_reference_id(_WINDOW_SET_ID),
           "fact_kind": _FACT_KINDS[role], "effective_start_ns": 0, "effective_end_ns": None, "text": "snap1",
           "price": price, "factor_num": None if factor is None else factor[0],
           "factor_den": None if factor is None else factor[1], "known_at_ns": known}
    coverage = Coverage(None, 1, False) if state == "gap" else Coverage(1, 1, True)
    return make_extremum_batch((row,), metadata=BatchMetadata("SYN", source, coverage, **metadata_kw))


def synthetic_retracement_fixture(case_id: str) -> RetracementInputs:
    """Original synthetic extremum rows of one contract fixture; nothing is computed.

    priced, null_price (null price, optional factors), insufficient (null price, partial factor),
    unknown (known_at null), future (known_at 150) and gap (row present, declared incomplete
    coverage, expected unknown) are one-row batches carrying the compact price and factors
    unchanged; empty_batch is a complete zero-row batch; absent is missing delivery (None).
    Effective instants (0, null) and the window set id are unspecified evidence-only choices.
    """
    case = _case(case_id)
    high, low = (_side(i, case[key], case["scale"]) for i, key in enumerate(("high", "low")))
    return RetracementInputs(high, low, tuple("unavailable" if b is None else "synthetic" for b in (high, low)))


__all__ += ["SYNTHETIC_RETRACEMENT_CASES", "synthetic_retracement_config", "synthetic_retracement_fixture"]
