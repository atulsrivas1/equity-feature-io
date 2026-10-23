"""Lossless supplied path-efficiency inputs; no efficiency, log, true-range or choppiness mathematics.

Maps SUPPLIED OHLCV bars (or close-only bars) on the R17 governed grid into the one nullable `bars` role of the
frozen EF4 path-efficiency contract (config `ef4.path_efficiency`, algorithm `ef4-path-efficiency-v1`, policy
`ef4-path1`; core docs/ef4/PATH_EFFICIENCY_CONTRACT_PROPOSAL.md), and builds its closed configuration envelope with
the same R17 context transport as the library codec. Nothing is derived, filled, bridged, sorted or inferred. Every
identity (instrument, session, start, end) comes from the caller's context, never from a constant in this module.
The library (`equity_features_intraday`) still performs every admission, decision and refusal, including the
config-stage order: shape, range and unit faults before the policy label, and the R17 mode coherence check.

Rulings pinned here (core docs/ef4/PATH_EFFICIENCY_IMPLEMENTATION.md, "Rulings to pin in the EF4 shared amendment"):
`governed_history` is capped at N <= 63 daily returns per context (one governed slot per session), and that
epoch profile uses the R17 `carry` context mode, while `session_reset` uses `reset`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage,
    DataKind, ErrorCode, InputScope, IntervalCoverage, Parameter, PriceUnit, SourceBinding, WindowSpec, validate_batch,
)
from equity_feature_contracts.inputs import Cell

from .relative_rv import CONTEXT_SCHEMA, IntradayContextSpec, IntradayRunSpec

ROLES = ("bars",)
_ORIGINS = frozenset(("supplied", "duckdb_backed_observed", "unavailable"))
MAPPING_VERSION = "ef4-path-map1"
CONFIG_IDENTITY = "ef4.path_efficiency"
ALGORITHM_VERSION = "ef4-path-efficiency-v1"
POLICY_VERSION = "ef4-path1"
EPOCH_PROFILES = {"session_reset": "reset", "governed_history": "carry"}  # profile -> required R17 context mode
WINDOW_MIN, WINDOW_MAX = 2, 4096
GOVERNED_WINDOW_MAX = 63
EVIDENCE_LIMIT_MAX = 10000
CHUNK_CHARS = 4096
# Output ids (lexical order) and their units, for the sink headers of the worker layer.
PATH_FEATURES: tuple[str, ...] = (
    "path.choppiness_fraction", "path.efficiency_ratio", "path.log_efficiency_ratio", "path.net_displacement",
    "path.path_length", "path.true_range_sum", "path.window_range",
)
PATH_UNITS: dict[str, str] = {
    "path.choppiness_fraction": "fraction", "path.efficiency_ratio": "fraction",
    "path.log_efficiency_ratio": "fraction", "path.net_displacement": "currency/share",
    "path.path_length": "currency/share", "path.true_range_sum": "currency/share",
    "path.window_range": "currency/share",
}
# Bar columns in canonical order; a delivery lists only the columns it supplies (close-only deliveries list close).
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
CLOSE_COLUMNS = ("close",)


def make_path_batch(column_order: tuple[str, ...], rows: tuple[tuple[Cell, ...], ...], *,
                    metadata: BatchMetadata) -> CanonicalBatch:
    """Convert exact supplied rectangular BAR cells, retaining order and metadata.

    No sorting, filtering, field filling, unit or basis conversion or timestamp inference occurs. Generic canonical
    validation may refuse an invalid original row first; admission belongs to the pure producer.
    """
    if (type(column_order) is not tuple or any(type(name) is not str for name in column_order)
            or type(rows) is not tuple
            or any(type(row) is not tuple or len(row) != len(column_order) for row in rows)
            or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied path bar rectangle required")
    result = CanonicalBatch(DataKind.BAR, tuple(Column(name, tuple(row[i] for row in rows))
                                                for i, name in enumerate(column_order)), metadata)
    validate_batch(result, required_fields=())
    return result


def make_slot_coverage(index: int, start_ns: int, end_ns: int, *, expected: int | None, observed: int,
                       complete: bool) -> IntervalCoverage:
    """Declare the per-slot coverage entry `slot:<index>` of one governed grid slot, as supplied."""
    if type(index) is not int or index < 0:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Nonnegative governed slot index required")
    return IntervalCoverage(f"slot:{index}", start_ns, end_ns, Coverage(expected, observed, complete))


def make_path_chunks(context: IntradayContextSpec, slots: Sequence[Any], *, input_id: str, source_id: str,
                     snapshot_id: str, namespace: str, price_unit: PriceUnit, adjustment: AdjustmentSpec,
                     columns: tuple[str, ...], eligibility_policy: str) -> tuple[CanonicalBatch, ...]:
    """BAR chunks over the governed slots of the context: one chunk per actual session, in context order.

    A slot entry is one of: "absent" (no row, no coverage), "gap" (no row, declared incomplete coverage), "empty"
    (no row, complete coverage of expected 0: a proven empty slot, never forward filled), or a mapping
    {"values": tuple, "known_at_ns": int | None} whose values align with `columns`. The identity columns
    (instrument, session, start, end) come from the context, never from this module; a supplied row is complete
    coverage of one row. Chunk k is `<input_id>-<k:03>`; each chunk's scope is its session's bounds.
    """
    if type(context) is not IntradayContextSpec or type(columns) is not tuple:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete context and column tuple required")
    bounds = [(run.session_id, run.start_ns + j * run.step_ns, run.start_ns + (j + 1) * run.step_ns)
              for run in context.runs for j in range(run.count)]
    if type(slots) not in (tuple, list) or len(slots) != len(bounds):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "One supplied entry per governed slot required")
    names = ("instrument_id", "session_id", "start_ns", "end_ns", *columns, "known_at_ns")
    chunks: list[CanonicalBatch] = []
    for session in context.sessions:
        members = [i for i, (sid, _, _) in enumerate(bounds) if sid == session.session_id]
        if not members:
            continue
        rows: list[tuple[Any, ...]] = []
        intervals: list[IntervalCoverage] = []
        for index in members:
            session_id, start, end = bounds[index]
            slot = slots[index]
            if slot == "absent":
                continue
            if slot == "gap":
                intervals.append(make_slot_coverage(index, start, end, expected=1, observed=0, complete=False))
            elif slot == "empty":
                intervals.append(make_slot_coverage(index, start, end, expected=0, observed=0, complete=True))
            elif (type(slot) is dict and set(slot) == {"values", "known_at_ns"} and type(slot["values"]) is tuple
                  and len(slot["values"]) == len(columns)):
                rows.append((context.instrument_id, session_id, start, end, *slot["values"], slot["known_at_ns"]))
                intervals.append(make_slot_coverage(index, start, end, expected=1, observed=1, complete=True))
            else:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Unknown supplied slot entry")
        scope = InputScope(session.open_ns, session.close_ns, eligibility_policy)
        metadata = BatchMetadata(namespace,
                                 SourceBinding(source_id, snapshot_id, MAPPING_VERSION,
                                               f"{input_id}-{len(chunks):03}"),
                                 Coverage(None, len(rows), False), price_unit, adjustment, "none", "shares",
                                 "declared", "reject", scope, tuple(intervals))
        chunks.append(make_path_batch(names, tuple(rows), metadata=metadata))
    return tuple(chunks)


@dataclass(frozen=True)
class PathEfficiencyInputs:
    """One nullable `bars` role holding the ordered BAR chunks of the governed grid.

    `bars=None` is missing delivery. Origins are explicit caller declarations, not capability or rights evidence.
    Nothing here orders, merges or repairs chunks.
    """
    bars: tuple[CanonicalBatch, ...] | None = None
    provenance: tuple[str, ...] = ("unavailable",)

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 1:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly one path origin required")
        origin = self.provenance[0]
        if type(origin) is not str or origin not in _ORIGINS or (self.bars is None) != (origin == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
        if self.bars is not None:
            if type(self.bars) is not tuple:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete tuple of BAR chunks required")
            for batch in self.bars:
                if type(batch) is not CanonicalBatch or batch.kind is not DataKind.BAR:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Path role requires BAR batches")
                validate_batch(batch, required_fields=())
            if len({b.metadata.source.input_id for b in self.bars}) != len(self.bars):
                raise ContractError(ErrorCode.DUPLICATE, "Distinct path chunk input IDs required")
            if len({b.metadata.namespace for b in self.bars}) > 1:
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One path namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return ROLES

    @property
    def slots(self) -> tuple[tuple[CanonicalBatch, ...] | None, ...]:
        return (self.bars,)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return () if self.bars is None else self.bars


def make_path_config(context: IntradayContextSpec, *, window: Any, epoch_profile: Any,
                     availability: AvailabilitySpec, adjustment: AdjustmentSpec, price_unit: PriceUnit | None,
                     evidence_limit: Any, policy_version: Any = POLICY_VERSION) -> ConfigSpec:
    """ef4.path_efficiency envelope over the accepted R17 context (same parameters, identity and algorithm as the library builder for the same context).

    Pure I/O checks only: types, the window range, the governed_history cap of 63 and the price unit presence. The
    library decodes every other value (evidence range, mode coherence, the policy label, adjustment, identities).
    """
    if price_unit is None:
        raise ContractError(ErrorCode.INVALID_UNIT, "Explicit price unit required")
    if type(context) is not IntradayContextSpec or type(availability) is not AvailabilitySpec \
            or type(adjustment) is not AdjustmentSpec or type(price_unit) is not PriceUnit:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Concrete context, timing, adjustment and unit required")
    if type(epoch_profile) is not str or epoch_profile not in EPOCH_PROFILES:
        raise ContractError(ErrorCode.INVALID_CONFIG, "epoch_profile must be session_reset or governed_history")
    if type(window) is not int or not WINDOW_MIN <= window <= WINDOW_MAX:
        raise ContractError(ErrorCode.INVALID_CONFIG, "window must be an integer in 2..4096")
    if epoch_profile == "governed_history" and window > GOVERNED_WINDOW_MAX:
        raise ContractError(ErrorCode.INVALID_CONFIG, "governed_history window is capped at 63 daily returns")
    text = context.to_json()
    chunks = tuple(text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS))
    params: list[Parameter] = [
        Parameter("policy_version", policy_version), Parameter("window", window),
        Parameter("epoch_profile", epoch_profile), Parameter("evidence_limit", evidence_limit),
        Parameter("context_schema", CONTEXT_SCHEMA), Parameter("context_sha256", context.digest),
        Parameter("context_chunks", len(chunks)),
    ]
    params += [Parameter(f"context_{i:03}", chunk) for i, chunk in enumerate(chunks)]
    target = next(s for s in context.sessions if s.session_id == context.runs[-1].session_id)
    return ConfigSpec(CONFIG_IDENTITY, ALGORITHM_VERSION, tuple(params), target,
                      WindowSpec(len(context.sessions), target.session_id,
                                 tuple(s.session_id for s in context.sessions), "completed_eod"),
                      availability, adjustment, price_unit)


def make_path_context(instrument_id: str, *, calendar_id: str, grid_id: str, revision: str,
                      sessions: Sequence[Any], runs: Sequence[IntradayRunSpec], anchor_index: int,
                      target_index: int, epoch_profile: str) -> IntradayContextSpec:
    """The R17 context for one epoch profile; the mode is fixed by the profile (session_reset: reset,
    governed_history: carry). The library enforces the 64-session context cap and the mode consistency when it
    decodes the context, so this builder does not repeat those checks."""
    if type(epoch_profile) is not str or epoch_profile not in EPOCH_PROFILES:
        raise ContractError(ErrorCode.INVALID_CONFIG, "epoch_profile must be session_reset or governed_history")
    return IntradayContextSpec(instrument_id, calendar_id, grid_id, revision, tuple(sessions), tuple(runs),
                               anchor_index, target_index, EPOCH_PROFILES[epoch_profile])


__all__ = ["PathEfficiencyInputs", "make_path_batch", "make_path_chunks", "make_slot_coverage", "make_path_config",
           "make_path_context", "ROLES", "MAPPING_VERSION", "CONFIG_IDENTITY", "ALGORITHM_VERSION", "POLICY_VERSION",
           "EPOCH_PROFILES", "WINDOW_MIN", "WINDOW_MAX", "GOVERNED_WINDOW_MAX", "EVIDENCE_LIMIT_MAX", "PATH_FEATURES",
           "PATH_UNITS", "OHLCV_COLUMNS", "CLOSE_COLUMNS"]
