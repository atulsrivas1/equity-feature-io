"""Lossless supplied EF3 relative-statistics, daily log-volatility and realized-variance inputs.

Maps SUPPLIED close-only daily BARs (relative statistics, daily log volatility) and SUPPLIED regular-session
OHLCV bars (realized variance) into canonical batches on a local governed grid, and builds the three producer
configurations with the same closed envelopes as the core library (core `docs/ef3/RELATIVE_RV_CONTRACT_PROPOSAL.md`,
contract `ef3-rel1`, `ef3-dlv1`, `ef3-rv1`, Amendment 1). Nothing is derived, filled, bridged, rescaled, sorted or
inferred; no return, beta, correlation, logarithm, variance or annualization mathematics lives here. The library
(`equity_features.ef3`, `equity_features_intraday`) still performs every admission, decision and refusal.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage,
    DataKind, ErrorCode, InputScope, IntervalCoverage, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec,
    validate_batch,
)

GRID_SCHEMA = "equity-features.ef3-daily-grid.v1"
CONTEXT_SCHEMA = "equity-features.intraday-context.v1"  # the accepted R17 context codec, unchanged
MAPPING_VERSION = "ef3-map1"
NAMESPACE = "SYN"
CURRENCY = "USD"
RELATIVE_IDENTITY, RELATIVE_ALGORITHM, RELATIVE_POLICY = "ef3.relative_stats", "ef3-relative-stats-v1", "ef3-rel1"
RELATIVE_FEATURES = ("relative.beta", "relative.correlation", "relative.residual_return")
LOG_VOL_IDENTITY, LOG_VOL_ALGORITHM, LOG_VOL_POLICY = "ef3.daily_log_volatility", "ef3-daily-log-vol-v1", "ef3-dlv1"
LOG_VOL_FEATURE = "history.log_return_volatility"
RV_IDENTITY, RV_ALGORITHM, RV_POLICY = "ef3.intraday_realized_variance", "ef3-realized-variance-v1", "ef3-rv1"
RV_FEATURES = ("intraday.realized_variance", "intraday.realized_volatility")
RV_SAMPLING = "every_governed_slot"
KNOWLEDGE_CUTOFF_DEFAULT = 100  # the fixtures' K; a caller may pass any cutoff
# Closed slot-state vocabulary of the compact contract notation (daily roles use the first six, intraday all seven).
DAILY_STATES = ("priced", "absent", "gap", "unknown", "future", "null")
INTRADAY_STATES = ("priced", "absent", "gap", "unknown", "future", "null", "empty")
# Session and bar geometry: one daily session per slot; intraday bars are contiguous ns intervals.
DAILY_SLOT_NS, DAILY_SESSION_NS = 10, 5
BAR_NS = 10
BAR_VOLUME = 100
# The compact notation omits the close of an unknown-availability slot. A placeholder keeps the row admissible; such a
# slot is never READY (unknown_availability), so the value never enters any output, return or evidence row.
UNSUPPLIED_CLOSE = 1


@dataclass(frozen=True)
class DailyGrid:
    """Local governed daily grid (the R17 grid and slot-coverage conventions); same fields and digest as the library."""

    instrument_id: str
    calendar_id: str
    grid_id: str
    revision: str
    sessions: tuple[SessionSpec, ...]
    target_index: int

    def to_json(self) -> str:
        return json.dumps({"schema": GRID_SCHEMA, **_grid_fields(self)}, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("ascii")).hexdigest()

    @property
    def target(self) -> SessionSpec:
        return self.sessions[self.target_index]

    def slot_bounds(self) -> tuple[tuple[str, int, int], ...]:
        return tuple((s.session_id, s.open_ns, s.close_ns) for s in self.sessions)


def _grid_fields(grid: DailyGrid) -> dict[str, Any]:
    return {"instrument_id": grid.instrument_id, "calendar_id": grid.calendar_id, "grid_id": grid.grid_id,
            "revision": grid.revision, "sessions": [asdict(s) for s in grid.sessions],
            "target_index": grid.target_index}


@dataclass(frozen=True)
class IntradayRunSpec:
    session_id: str
    start_ns: int
    step_ns: int
    count: int


@dataclass(frozen=True)
class IntradayContextSpec:
    """The accepted R17 intraday context (reset epoch), byte-identical to the library codec."""

    instrument_id: str
    calendar_id: str
    grid_id: str
    revision: str
    sessions: tuple[SessionSpec, ...]
    runs: tuple[IntradayRunSpec, ...]
    anchor_index: int
    target_index: int
    mode: str

    def to_json(self) -> str:
        return json.dumps({"schema": CONTEXT_SCHEMA, "instrument_id": self.instrument_id,
                           "calendar_id": self.calendar_id, "grid_id": self.grid_id, "revision": self.revision,
                           "sessions": [asdict(s) for s in self.sessions], "runs": [asdict(r) for r in self.runs],
                           "anchor_index": self.anchor_index, "target_index": self.target_index, "mode": self.mode},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("ascii")).hexdigest()


def daily_sessions(count: int) -> tuple[SessionSpec, ...]:
    """One whole session per governed slot: [10i, 10i+5), namespace SYN, session id S<i>."""
    if type(count) is not int or count < 1:
        raise ContractError(ErrorCode.INVALID_CONFIG, "positive slot count required")
    return tuple(SessionSpec(NAMESPACE, f"S{i}", i * DAILY_SLOT_NS, i * DAILY_SLOT_NS + DAILY_SESSION_NS, "UTC")
                 for i in range(count))


def daily_grid(sessions: Sequence[SessionSpec], target_index: int, *, instrument_id: str = "X") -> DailyGrid:
    return DailyGrid(instrument_id, "SYN-CAL", "SYN-GRID", "r1", tuple(sessions), target_index)


def availability_for(sessions: Sequence[SessionSpec], knowledge_cutoff_ns: int = KNOWLEDGE_CUTOFF_DEFAULT,
                     market_cutoff_ns: int | None = None) -> AvailabilitySpec:
    """Market cutoff at the grid end unless given; evaluation covers both cutoffs (causal known_at mode)."""
    market = sessions[-1].close_ns if market_cutoff_ns is None else market_cutoff_ns
    return AvailabilitySpec(market, knowledge_cutoff_ns, max(knowledge_cutoff_ns, market), "known_at")


def _envelope(identity: str, algorithm: str, parameters: Sequence[Parameter], grid: DailyGrid,
              availability: AvailabilitySpec, price_unit: PriceUnit) -> ConfigSpec:
    """The library daily envelope: target session, whole grid, grid binding by SHA-256, explicit unit and basis."""
    grid_params = (Parameter("grid_schema", GRID_SCHEMA), Parameter("grid_sha256", grid.digest))
    return ConfigSpec(identity, algorithm, tuple(parameters) + grid_params, grid.target,
                      WindowSpec(len(grid.sessions), grid.target.session_id,
                                 tuple(s.session_id for s in grid.sessions), "completed_eod"),
                      availability, AdjustmentSpec(), price_unit)


def price_unit(scale: int) -> PriceUnit:
    return PriceUnit(scale, CURRENCY)


def relative_config(grid: DailyGrid, *, benchmark_id: str = "B", window: Any, min_pairs: Any,
                    availability: AvailabilitySpec, scale: int, policy_version: Any = RELATIVE_POLICY,
                    evidence_limit: Any = 0) -> ConfigSpec:
    """ef3.relative_stats envelope with the caller's values passed through (validation belongs to the library)."""
    params = (Parameter("policy_version", policy_version), Parameter("benchmark_id", benchmark_id),
              Parameter("window", window), Parameter("min_pairs", min_pairs),
              Parameter("evidence_limit", evidence_limit))
    return _envelope(RELATIVE_IDENTITY, RELATIVE_ALGORITHM, params, grid, availability, price_unit(scale))


def log_volatility_config(grid: DailyGrid, *, period: Any, annualization_factor: Any, availability: AvailabilitySpec,
                          scale: int, policy_version: Any = LOG_VOL_POLICY, evidence_limit: Any = 0) -> ConfigSpec:
    params = (Parameter("policy_version", policy_version), Parameter("period", period),
              Parameter("annualization_factor", annualization_factor), Parameter("evidence_limit", evidence_limit))
    return _envelope(LOG_VOL_IDENTITY, LOG_VOL_ALGORITHM, params, grid, availability, price_unit(scale))


def realized_variance_config(context: IntradayContextSpec, *, annualization_factor: Any, availability: AvailabilitySpec,
                             scale: int, policy_version: Any = RV_POLICY, sampling: Any = RV_SAMPLING,
                             evidence_limit: Any = 0) -> ConfigSpec:
    """ef3.intraday_realized_variance envelope; annualization_factor is present exactly when volatility is selected."""
    text = context.to_json()
    chunks = tuple(text[i:i + 4096] for i in range(0, len(text), 4096))
    params = [Parameter("policy_version", policy_version), Parameter("sampling", sampling),
              Parameter("evidence_limit", evidence_limit), Parameter("context_schema", CONTEXT_SCHEMA),
              Parameter("context_sha256", context.digest), Parameter("context_chunks", len(chunks))]
    if annualization_factor is not None:
        params.append(Parameter("annualization_factor", annualization_factor))
    params += [Parameter(f"context_{i:03}", chunk) for i, chunk in enumerate(chunks)]
    target = next(s for s in context.sessions if s.session_id == context.runs[-1].session_id)
    return ConfigSpec(RV_IDENTITY, RV_ALGORITHM, tuple(params), target,
                      WindowSpec(len(context.sessions), target.session_id,
                                 tuple(s.session_id for s in context.sessions), "completed_eod"),
                      availability, AdjustmentSpec(), price_unit(scale))


def _checked_slots(slots: Sequence[Mapping[str, Any]], states: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
    """Compact slot states in governed index order; an unknown state is refused as a schema error."""
    for slot in slots:
        if slot.get("state") not in states:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "unknown compact slot state")
    return tuple(slots)


def close_batch(role_instrument_id: str, grid: DailyGrid, slots: Sequence[Mapping[str, Any]], *, input_id: str,
                scale: int, namespace: str = NAMESPACE, known_default: int = 50) -> CanonicalBatch:
    """One close-only daily BAR role (instrument or benchmark) on the local grid; `slots` is one entry per grid slot.

    priced: row with close c and known_at; absent: no row and no coverage; gap: declared incomplete coverage and no
    row; unknown: known_at null; future: known_at as given (above the cutoff); null: row with a null close.
    """
    if len(slots) != len(grid.sessions):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "one compact slot per governed session required")
    states = _checked_slots(slots, DAILY_STATES)
    rows: list[tuple[Any, ...]] = []
    intervals: list[IntervalCoverage] = []
    for index, (session, slot) in enumerate(zip(grid.sessions, states)):
        state = slot["state"]
        name = f"slot:{index}"
        if state == "absent":
            continue
        if state == "gap":
            intervals.append(IntervalCoverage(name, session.open_ns, session.close_ns, Coverage(1, 0, False)))
            continue
        known = None if state == "unknown" else slot.get("known_at", known_default)
        close = None if state == "null" else slot.get("c", UNSUPPLIED_CLOSE)
        rows.append((role_instrument_id, session.session_id, session.open_ns, session.close_ns, close, known))
        intervals.append(IntervalCoverage(name, session.open_ns, session.close_ns, Coverage(1, 1, True)))
    return _bar_batch(("instrument_id", "session_id", "start_ns", "end_ns", "close", "known_at_ns"), rows,
                      intervals, grid_scope(grid), input_id=input_id, scale=scale, namespace=namespace,
                      count=len(rows))


def grid_scope(grid: DailyGrid) -> InputScope:
    return InputScope(grid.sessions[0].open_ns, grid.sessions[-1].close_ns, "ef3-daily-close")


def _bar_batch(names: tuple[str, ...], rows: Sequence[tuple[Any, ...]], intervals: Sequence[IntervalCoverage],
               scope: InputScope, *, input_id: str, scale: int, namespace: str, count: int) -> CanonicalBatch:
    columns = tuple(Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    metadata = BatchMetadata(namespace, SourceBinding("SYN-SRC", "snap-1", MAPPING_VERSION, input_id),
                             Coverage(None, count, False), price_unit(scale), AdjustmentSpec(), "none",
                             "shares", "declared", "reject", scope, tuple(intervals))
    batch = CanonicalBatch(DataKind.BAR, columns, metadata)
    validate_batch(batch, required_fields=())
    return batch


def intraday_batch(context: IntradayContextSpec, slots: Sequence[Mapping[str, Any]], *, input_id: str,
                   scale: int, namespace: str = NAMESPACE, known_default: int = 50) -> CanonicalBatch:
    """One regular-session OHLCV chunk over the governed slots of the (single) session of the context.

    priced: open=high=low=close=c, volume 100, known_at; absent: nothing; gap: declared incomplete coverage;
    empty: no row and complete coverage with expected 0 (a proven empty slot; no forward fill); null: volume,
    OHLC and close null; unknown and future as for daily roles.
    """
    states = _checked_slots(slots, INTRADAY_STATES)
    if len(states) != context.target_index + 1:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "the context ends at the target slot")
    names = ("instrument_id", "session_id", "start_ns", "end_ns", "open", "high", "low", "close", "volume", "known_at_ns")
    rows: list[tuple[Any, ...]] = []
    intervals: list[IntervalCoverage] = []
    bounds = [(run.session_id, run.start_ns + j * run.step_ns, run.start_ns + (j + 1) * run.step_ns)
              for run in context.runs for j in range(run.count)]
    for index, ((session_id, start, end), slot) in enumerate(zip(bounds, states)):
        state = slot["state"]
        name = f"slot:{index}"
        if state == "absent":
            continue
        if state == "gap":
            intervals.append(IntervalCoverage(name, start, end, Coverage(1, 0, False)))
        elif state == "empty":
            intervals.append(IntervalCoverage(name, start, end, Coverage(0, 0, True)))
        else:
            c = slot.get("c", UNSUPPLIED_CLOSE)
            known = None if state == "unknown" else slot.get("known_at", known_default)
            if state == "null":
                row = (context.instrument_id, session_id, start, end, None, None, None, None, None, known)
            else:
                row = (context.instrument_id, session_id, start, end, c, c, c, c, BAR_VOLUME, known)
            rows.append(row)
            intervals.append(IntervalCoverage(name, start, end, Coverage(1, 1, True)))
    session = next(s for s in context.sessions if s.session_id == context.runs[0].session_id)
    scope = InputScope(session.open_ns, session.close_ns, "ef3-rv-regular")
    return _bar_batch(names, rows, intervals, scope, input_id=input_id, scale=scale, namespace=namespace,
                      count=len(rows))


def make_intraday_context(instrument_id: str, *, sessions: Sequence[SessionSpec], runs: Sequence[IntradayRunSpec],
                          anchor_index: int, target_index: int, mode: str = "reset") -> IntradayContextSpec:
    return IntradayContextSpec(instrument_id, "SYN-CAL", "SYN-GRID", "r1", tuple(sessions), tuple(runs),
                               anchor_index, target_index, mode)


def synthetic_intraday_session(count: int) -> tuple[tuple[SessionSpec, ...], tuple[IntradayRunSpec, ...]]:
    """One regular session [0, 10 * count) with `count` contiguous bars of 10 ns."""
    session = SessionSpec(NAMESPACE, "S0", 0, BAR_NS * count, "UTC")
    return (session,), (IntradayRunSpec("S0", 0, BAR_NS, count),)


__all__ = ["DailyGrid", "IntradayContextSpec", "IntradayRunSpec", "GRID_SCHEMA", "CONTEXT_SCHEMA",
           "RELATIVE_IDENTITY", "RELATIVE_ALGORITHM", "RELATIVE_POLICY", "RELATIVE_FEATURES",
           "LOG_VOL_IDENTITY", "LOG_VOL_ALGORITHM", "LOG_VOL_POLICY", "LOG_VOL_FEATURE",
           "RV_IDENTITY", "RV_ALGORITHM", "RV_POLICY", "RV_FEATURES", "RV_SAMPLING", "MAPPING_VERSION",
           "DAILY_STATES", "INTRADAY_STATES", "UNSUPPLIED_CLOSE", "daily_sessions", "daily_grid", "availability_for", "price_unit",
           "relative_config", "log_volatility_config", "realized_variance_config", "close_batch", "intraday_batch",
           "make_intraday_context", "synthetic_intraday_session", "grid_scope"]
