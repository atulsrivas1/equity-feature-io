"""Lossless supplied EF3 robust-history, volume-pace and mean-ratio inputs.

Maps SUPPLIED daily rows (volume or price coefficients), session bounds facts, declared exclusion facts, declared
population members, bucket-grid edges and bucket volumes (bars) into canonical batches on a local governed grid, and
builds the three producer configurations with the same closed envelopes as the core library (core
`docs/ef3/ROBUST_PACE_CONTRACT_PROPOSAL.md`, policies `ef3-robust1`, `ef3-pace1`, `ef3-mean1`). Nothing is derived, filled,
imputed, sorted, rescaled or inferred; no median, MAD, quantile, rank, ratio, z-score or mean mathematics lives here. The
library (`equity_features.ef3`) still performs every admission, decision and refusal.
"""
from __future__ import annotations

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage,
    DataKind, ErrorCode, InputScope, IntervalCoverage, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec,
    validate_batch,
)
from ._typed import checked_known_at, guard_public

NAMESPACE = "SYN"  # documented demo default of the `namespace` parameters; callers pass their own
CURRENCY = "USD"
SOURCE_ID = "SYN-SRC"
SNAPSHOT_ID = "snap-1"
MAPPING_VERSION = "ef3-map1"
INSTRUMENT_ID = "X"
KNOWLEDGE_CUTOFF_DEFAULT = 100  # the fixtures' K
KNOWN_AT_LATE = 150  # the fixtures' "f" rows (above K)
SESSION_SPAN_DEFAULT = 300  # the fixtures' default close offset
SESSION_STEP = 1000  # nominal session open spacing: session j opens at j * 1000
UNSUPPLIED_VALUE = 1  # value of an exclusion-only slot (its own value is ignored) and of an unknown-availability exclusion
VOLUME_PRICED = 100  # volume of a priced daily price row (not read by a price-field producer)
GRID_VERSION = "ef3-grid1"
GRID_ID = "SYN-GRID"
EXCLUSION_ID = "SYN-EXCL"
POPULATION_ID = "SYN-POP"  # documented demo default of the `population_id` parameter

ROBUST_IDENTITY, ROBUST_ALGORITHM, ROBUST_POLICY = "ef3.robust_history", "ef3-robust-history-v1", "ef3-robust1"
PACE_IDENTITY, PACE_ALGORITHM, PACE_POLICY = "ef3.volume_pace_robust", "ef3-volume-pace-robust-v1", "ef3-pace1"
MEAN_IDENTITY, MEAN_ALGORITHM, MEAN_POLICY = "ef3.volume_ratio_mean", "ef3-volume-ratio-mean-v1", "ef3-mean1"
KIND_BOUNDS, KIND_EXCLUDED, KIND_POPULATION, KIND_EDGE = (
    "ef3.session.bounds", "ef3.session.excluded", "ef3.population.member", "ef3.bucket.edge")
ROW, ABSENT, GAP = "row", "absent", "gap"


@dataclass(frozen=True)
class Cell:
    """One governed slot in supplied form. ROW with value None is a null field; ABSENT has no row and no coverage;
    GAP has declared incomplete coverage and no row. `excluded` declares an exclusion fact for the session."""

    state: str
    value: int | None = None
    known_at: int | None = None  # supplied per row; None is unknown availability, never a default
    excluded: bool = False
    exclusion_known_at: int | None = None


@dataclass(frozen=True)
class Session:
    """One governed session: actual open and close offsets in nanoseconds (UTC)."""

    session_id: str
    open_ns: int
    close_ns: int
    excluded: bool = False
    exclusion_known_at: int | None = None
    bounds_known_at: int | None = None  # known_at of the session bounds fact; None is unknown availability


def session(index: int, *, close: int = SESSION_SPAN_DEFAULT, excluded: bool = False,
            exclusion_known_at: int | None = None, bounds_known_at: int | None = None) -> Session:
    """Governed session `<index>` opening at index * SESSION_STEP, closing `close` ns later."""
    if type(index) is not int or index < 0 or type(close) is not int or close < 1:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "non-negative index and positive close offset required")
    open_ns = index * SESSION_STEP
    return Session(f"{index}", open_ns, open_ns + close, excluded, checked_known_at(exclusion_known_at),
                   checked_known_at(bounds_known_at))


def parse_cell(token: Any, *, known_at: int | None) -> Cell:
    """Compact slot notation of the contract (not a wire format). Integer: priced row; "null": row with a null field;
    "absent" and "gap"; None: absent; ["x", v]: priced row with a declared exclusion; ["xu"] and ["xf"]: exclusion with
    null and late knowledge; ["f", v]: row with knowledge above K; ["u", v]: row with null knowledge; ["p", v, ka]:
    explicit knowledge. `known_at` is the explicit knowledge of the tokens that do not state their own (integer, "null",
    "x"); the caller must pass it (None means unknown availability)."""
    known_at = checked_known_at(known_at)
    if token is None or token == ABSENT:
        return Cell(ABSENT)
    if token == GAP:
        return Cell(GAP)
    if token == "null":
        return Cell(ROW, None, known_at)
    if type(token) is int:
        return Cell(ROW, token, known_at)
    if type(token) is list and token:
        head = token[0]
        if head == "x" and len(token) == 2:
            return Cell(ROW, token[1], known_at, True, known_at)
        if head == "xu" and len(token) == 1:
            return Cell(ROW, UNSUPPLIED_VALUE, known_at, True, None)
        if head == "xf" and len(token) == 1:
            return Cell(ROW, UNSUPPLIED_VALUE, known_at, True, KNOWN_AT_LATE)
        if head == "f" and len(token) == 2:
            return Cell(ROW, token[1], KNOWN_AT_LATE)
        if head == "u" and len(token) == 2:
            return Cell(ROW, token[1], None)
        if head == "p" and len(token) == 3:
            return Cell(ROW, token[1], checked_known_at(token[2]))
    raise ContractError(ErrorCode.INVALID_SCHEMA, "unknown compact slot notation")


def parse_bucket(token: Any, *, known_at: int | None) -> Cell:
    """Pace bucket notation: as `parse_cell`, except that None inside a bucket list is a row with a null volume (a
    session whose whole cell list is None has no rows; that is the caller's ABSENT, not this function)."""
    if token is None:
        return Cell(ROW, None, checked_known_at(known_at))
    return parse_cell(token, known_at=known_at)


def availability(market_cutoff_ns: int, knowledge_cutoff_ns: int = KNOWLEDGE_CUTOFF_DEFAULT) -> AvailabilitySpec:
    """Causal known_at timing: market cutoff and knowledge cutoff with evaluation at the later of the two."""
    return AvailabilitySpec(market_cutoff_ns, knowledge_cutoff_ns, max(knowledge_cutoff_ns, market_cutoff_ns), "known_at")


def price_unit(scale: int) -> PriceUnit:
    return PriceUnit(scale, CURRENCY)


def reference(text: str) -> str:
    """Closed x1 reference identity: `x1:` followed by the unpadded URL-safe base64 of the id text."""
    return "x1:" + base64.urlsafe_b64encode(text.encode("utf-8")).rstrip(b"=").decode("ascii")


def _source(input_id: str) -> SourceBinding:
    return SourceBinding(SOURCE_ID, SNAPSHOT_ID, MAPPING_VERSION, input_id)


def _scope(start_ns: int, end_ns: int) -> InputScope:
    return InputScope(start_ns, end_ns, "ef3-supplied")


def _batch(kind: DataKind, names: tuple[str, ...], rows: Sequence[tuple[Any, ...]], intervals: Sequence[IntervalCoverage],
           unit: PriceUnit | None, *, input_id: str, bounds: tuple[int, int], count: int,
           namespace: str = NAMESPACE) -> CanonicalBatch:
    columns = tuple(Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    metadata = BatchMetadata(namespace, _source(input_id), Coverage(None, count, False), unit, AdjustmentSpec(),
                             "none", "shares", "declared", "reject", _scope(*bounds), tuple(intervals))
    batch = CanonicalBatch(kind, columns, metadata)
    validate_batch(batch, required_fields=())
    return batch


def sessions_batch(sessions: Sequence[Session], *, input_id: str, instrument_id: str = INSTRUMENT_ID,
                   namespace: str = NAMESPACE) -> CanonicalBatch:
    """`sessions` role: one ef3.session.bounds fact per governed session and optional ef3.session.excluded facts."""
    rows: list[tuple[Any, ...]] = []
    for s in sessions:
        rows.append((instrument_id, s.session_id, reference(GRID_ID), KIND_BOUNDS, s.open_ns, s.close_ns, SNAPSHOT_ID,
                     checked_known_at(s.bounds_known_at)))
        if s.excluded:
            rows.append((instrument_id, s.session_id, reference(EXCLUSION_ID), KIND_EXCLUDED, s.open_ns, s.close_ns,
                         "declared exclusion", checked_known_at(s.exclusion_known_at)))
    rows.sort(key=lambda r: (r[4], r[2]))
    names = ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns", "effective_end_ns", "text",
             "known_at_ns")
    return _batch(DataKind.REFERENCE, names, rows, (), None, input_id=input_id,
                  bounds=(sessions[0].open_ns, sessions[-1].close_ns), count=len(rows), namespace=namespace)


def population_batch(members: Sequence[str | tuple[str, int | None]], target: Session, *, input_id: str,
                     known_at: int | None = None, namespace: str = NAMESPACE,
                     population_id: str = POPULATION_ID) -> CanonicalBatch:
    """`population` role: one ef3.population.member fact per declared member, on the target session.

    A member is a name or a (name, known_at) pair; a bare name takes `known_at` (None is unknown availability)."""
    rows = []
    for m in members:
        name, ka = (m, known_at) if isinstance(m, str) else (m[0], m[1])
        rows.append((name, target.session_id, reference(population_id), KIND_POPULATION, target.open_ns, target.close_ns,
                     SNAPSHOT_ID, checked_known_at(ka)))
    names = ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns", "effective_end_ns", "text",
             "known_at_ns")
    return _batch(DataKind.REFERENCE, names, rows, (), None, input_id=input_id,
                  bounds=(target.open_ns, target.close_ns), count=len(rows), namespace=namespace)


def grid_batch(offsets: Sequence[int | tuple[int, int | None]], target: Session, *, input_id: str,
               instrument_id: str = INSTRUMENT_ID, grid_version: str = GRID_VERSION, known_at: int | None = None,
               namespace: str = NAMESPACE) -> CanonicalBatch:
    """`grid` role: B+1 ef3.bucket.edge facts, offsets from the actual open (first 0, strictly increasing).

    An offset is an int or an (offset, known_at) pair; a bare int takes `known_at` (None is unknown availability)."""
    pairs = [(o, known_at) if type(o) is int else (cast("tuple[int, int | None]", o)[0], cast("tuple[int, int | None]", o)[1]) for o in offsets]
    rows = [(instrument_id, target.session_id, reference(f"{grid_version}#{i}"), KIND_EDGE, int(o), None, grid_version,
             checked_known_at(ka)) for i, (o, ka) in enumerate(pairs)]
    names = ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns", "effective_end_ns", "text",
             "known_at_ns")
    return _batch(DataKind.REFERENCE, names, rows, (), None, input_id=input_id,
                  bounds=(target.open_ns, target.open_ns + max(o for o, _ in pairs) + 1), count=len(rows),
                  namespace=namespace)


def daily_batch(entries: Sequence[tuple[str, Session, Cell]], *, field: str, scale: int, input_id: str,
                role: str, namespace: str = NAMESPACE) -> CanonicalBatch:
    """DAILY rows of one or more instruments on governed sessions (`series` and `cohort_values` roles).

    `field` names the operand: volume (int64 shares, column volume) or a price (open, high, low or close coefficients at
    `scale`). A priced price row carries open = high = low = close = c and volume VOLUME_PRICED; a null price row carries
    null OHLC with zero volume (the shared zero-volume rule); a null volume row carries a null volume. `role` names the
    coverage entries explicitly: "session" (series: session:<session_id>) or "member" (cohort: member:<instrument_id>)."""
    if role not in ("session", "member"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "role must be session or member")
    if field not in ("volume", "open", "high", "low", "close"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "field outside volume, open, high, low, close")
    price = field != "volume"
    rows: list[tuple[Any, ...]] = []
    intervals: list[IntervalCoverage] = []
    for instrument, s, cell in entries:
        name = f"session:{s.session_id}" if role == "session" else f"member:{instrument}"
        if cell.state == ABSENT:
            continue
        checked_known_at(cell.exclusion_known_at)  # validated even though not emitted
        if cell.state == GAP:
            intervals.append(IntervalCoverage(name, s.open_ns, s.close_ns, Coverage(1, 0, False)))
            continue
        if not price:
            rows.append((instrument, s.session_id, s.open_ns, s.close_ns, cell.value, checked_known_at(cell.known_at)))
        elif cell.value is None:
            rows.append((instrument, s.session_id, s.open_ns, s.close_ns, None, None, None, None, 0, checked_known_at(cell.known_at)))
        else:
            c = cell.value
            rows.append((instrument, s.session_id, s.open_ns, s.close_ns, c, c, c, c, VOLUME_PRICED, checked_known_at(cell.known_at)))
    names: tuple[str, ...]
    if price:
        names = ("instrument_id", "session_id", "start_ns", "end_ns", "open", "high", "low", "close", "volume",
                 "known_at_ns")
    else:
        names = ("instrument_id", "session_id", "start_ns", "end_ns", "volume", "known_at_ns")
    bounds = (min(s.open_ns for _, s, _ in entries), max(s.close_ns for _, s, _ in entries))
    return _batch(DataKind.DAILY, names, rows, intervals, price_unit(scale), input_id=input_id, bounds=bounds,
                  count=len(rows), namespace=namespace)


def bars_batch(entries: Sequence[tuple[Session, int, Cell]], offsets: Sequence[int], *, input_id: str,
               instrument_id: str = INSTRUMENT_ID, scale: int = 0, namespace: str = NAMESPACE) -> CanonicalBatch:
    """BAR rows: one row per session per grid bucket c, covering [open + offsets[c], open + offsets[c + 1])."""
    rows: list[tuple[Any, ...]] = []
    intervals: list[IntervalCoverage] = []
    for s, c, cell in entries:
        start, end = s.open_ns + offsets[c], s.open_ns + offsets[c + 1]
        name = f"bucket:{s.session_id}:{c}"
        if cell.state == ABSENT:
            continue
        checked_known_at(cell.exclusion_known_at)  # validated even though not emitted
        if cell.state == GAP:
            intervals.append(IntervalCoverage(name, start, end, Coverage(1, 0, False)))
            continue
        rows.append((instrument_id, s.session_id, start, end, cell.value, checked_known_at(cell.known_at)))
    rows.sort(key=lambda r: (r[2], r[1]))
    names = ("instrument_id", "session_id", "start_ns", "end_ns", "volume", "known_at_ns")
    lo = min(s.open_ns for s, _, _ in entries)
    hi = max(s.open_ns + max(offsets) for s, _, _ in entries)
    return _batch(DataKind.BAR, names, rows, intervals, price_unit(scale), input_id=input_id, bounds=(lo, hi),
                  count=len(rows), namespace=namespace)


def _named(config_identity: str, algorithm: str, params: tuple[Parameter, ...], count: int, target: Session,
           timing: AvailabilitySpec, unit: PriceUnit, namespace: str = NAMESPACE) -> ConfigSpec:
    """The library `make_config` envelope: one target session, the target-only governed window (prior_only)."""
    session_spec = SessionSpec(namespace, target.session_id, target.open_ns, target.close_ns, "UTC")
    if timing.market_cutoff_ns < session_spec.open_ns:
        raise ContractError(ErrorCode.BOUNDS, "market cutoff precedes the target session open")
    return ConfigSpec(config_identity, algorithm, params, session_spec,
                      WindowSpec(count, session_spec.session_id, (session_spec.session_id,), "prior_only"),
                      timing, AdjustmentSpec(), unit)


def robust_history_config(target: Session, *, timing: AvailabilitySpec, field: str, scale: int, window: int,
                          min_history: int, quantile: tuple[int, int] | None = None,
                          min_population: int | None = None, evidence_limit: int = 0,
                          namespace: str = NAMESPACE) -> ConfigSpec:
    """ef3.robust_history envelope; the quantile pair is present exactly with robust.quantile and min_population exactly
    with a cohort output (the caller passes them only then)."""
    params = [Parameter("policy_version", ROBUST_POLICY), Parameter("field", field), Parameter("window", window),
              Parameter("min_history", min_history), Parameter("evidence_limit", evidence_limit)]
    if quantile is not None:
        params += [Parameter("quantile_num", quantile[0]), Parameter("quantile_den", quantile[1])]
    if min_population is not None:
        params.append(Parameter("min_population", min_population))
    return _named(ROBUST_IDENTITY, ROBUST_ALGORITHM, tuple(params), window, target, timing, price_unit(scale), namespace)


def volume_pace_config(target: Session, *, timing: AvailabilitySpec, profile: str, window: int, min_history: int,
                       scale_pair: tuple[int, int] | None = None, evidence_limit: int = 0,
                       namespace: str = NAMESPACE) -> ConfigSpec:
    """ef3.volume_pace_robust envelope; the scale pair k = scale_num/scale_den is present exactly with pace.robust_z."""
    params = [Parameter("policy_version", PACE_POLICY), Parameter("profile", profile), Parameter("window", window),
              Parameter("min_history", min_history), Parameter("grid_version", GRID_VERSION),
              Parameter("evidence_limit", evidence_limit)]
    if scale_pair is not None:
        params += [Parameter("scale_num", scale_pair[0]), Parameter("scale_den", scale_pair[1])]
    return _named(PACE_IDENTITY, PACE_ALGORITHM, tuple(params), window, target, timing, price_unit(0), namespace)


def mean_ratio_config(target: Session, *, timing: AvailabilitySpec, numerator_window: int, baseline_window: int,
                      numerator_inclusion: str, baseline_inclusion: str, evidence_limit: int = 0,
                      namespace: str = NAMESPACE) -> ConfigSpec:
    """ef3.volume_ratio_mean envelope (volume only, the mean-ratio companion; no optional parameter)."""
    params = (Parameter("policy_version", MEAN_POLICY), Parameter("field", "volume"),
              Parameter("numerator_window", numerator_window), Parameter("baseline_window", baseline_window),
              Parameter("numerator_inclusion", numerator_inclusion), Parameter("baseline_inclusion", baseline_inclusion),
              Parameter("evidence_limit", evidence_limit))
    return _named(MEAN_IDENTITY, MEAN_ALGORITHM, params, max(numerator_window, baseline_window), target, timing,
                  price_unit(0), namespace)


__all__ = [
    "Cell", "Session", "parse_cell", "parse_bucket", "session", "availability", "price_unit", "sessions_batch", "population_batch",
    "grid_batch", "daily_batch", "bars_batch", "robust_history_config", "volume_pace_config", "mean_ratio_config",
    "ROBUST_IDENTITY", "ROBUST_ALGORITHM", "ROBUST_POLICY", "PACE_IDENTITY", "PACE_ALGORITHM", "PACE_POLICY",
    "MEAN_IDENTITY", "MEAN_ALGORITHM", "MEAN_POLICY", "GRID_VERSION", "INSTRUMENT_ID", "NAMESPACE", "CURRENCY",
    "KNOWLEDGE_CUTOFF_DEFAULT", "KNOWN_AT_LATE", "SESSION_SPAN_DEFAULT", "SESSION_STEP",
    "UNSUPPLIED_VALUE", "VOLUME_PRICED",
]


guard_public(globals(), __name__)
