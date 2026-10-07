"""Caller-owned calendar/history/reference intent outside calculations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import cast

from equity_feature_contracts import (
    AvailabilitySpec, CanonicalBatch, ContractError, Coverage, DataKind, EntityKey,
    HistoryContext, PolicyAdmission, PriceUnit, SessionSpec, WindowSpec, validate_batch,
)
from equity_feature_contracts.adapters import AcquisitionRequest, SourceError, SourceErrorCode
from .mapping import parse_utc_ns
from .resolver import _count, _date, _fail, _text

DAY_NS = 86400 * 10**9


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class GovernedCalendar:
    namespace: str
    version: str
    evidence_id: str
    dated_sessions: tuple[tuple[str, SessionSpec], ...]
    closed_dates: tuple[str, ...] = ()
    grid_kind: str = "supplied_sessions"
    max_sessions: int = 4096

    def __post_init__(self) -> None:
        for value in (self.namespace, self.version, self.evidence_id):
            _text(value)
        _count(self.max_sessions, positive=True)
        if self.grid_kind not in ("supplied_sessions", "utc_daily_intervals"):
            _fail("Explicit supported calendar grid kind required")
        if type(self.dated_sessions) not in (tuple, list) or not self.dated_sessions:
            _fail("Concrete governed date/session pairs required")
        if len(self.dated_sessions) > self.max_sessions:
            _fail("Governed calendar limit exceeded", SourceErrorCode.LIMIT)
        pairs: list[tuple[str, SessionSpec]] = []
        for pair in self.dated_sessions:
            if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[1]) is not SessionSpec:
                _fail("Typed governed date/session pair required")
            date, session = _date(pair[0]), pair[1]
            if session.namespace != self.namespace:
                _fail("Governed calendar namespace conflict")
            if self.grid_kind == "utc_daily_intervals":
                start = parse_utc_ns(date+"T00:00:00Z")
                if session.open_ns != start or session.close_ns != start+DAY_NS:
                    _fail("Explicit completed UTC daily interval required")
            pairs.append((date, session))
        if len({d for d, _ in pairs}) != len(pairs) or len({s.session_id for _, s in pairs}) != len(pairs):
            _fail("Unique governed dates/session identities required")
        if any(a[0] >= b[0] or a[1].close_ns > b[1].open_ns for a, b in zip(pairs, pairs[1:])):
            _fail("Increasing nonoverlapping governed grid required")
        if type(self.closed_dates) not in (tuple, list):
            _fail("Concrete declared closed dates required")
        closed = tuple(_date(d) for d in self.closed_dates)
        if len(set(closed)) != len(closed) or set(closed) & {d for d, _ in pairs}:
            _fail("Closed/session date declaration conflict")
        object.__setattr__(self, "dated_sessions", tuple(pairs))
        object.__setattr__(self, "closed_dates", closed)

    @property
    def sessions(self) -> tuple[SessionSpec, ...]:
        return tuple(s for _, s in self.dated_sessions)

    @property
    def partition_sessions(self) -> tuple[tuple[str, str], ...]:
        return tuple((d, s.session_id) for d, s in self.dated_sessions)

    @property
    def identity_digest(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True)
class HistoryPlan:
    calendar: GovernedCalendar
    window: WindowSpec
    initialization_anchor: str | None = None
    anchor_previous_slot: bool = False
    max_sessions: int = 4096

    def __post_init__(self) -> None:
        if type(self.calendar) is not GovernedCalendar or type(self.window) is not WindowSpec:
            _fail("Typed calendar/window required")
        _count(self.max_sessions, positive=True)
        if type(self.anchor_previous_slot) is not bool:
            _fail("Explicit previous-slot policy required")
        ids = tuple(s.session_id for s in self.calendar.sessions)
        if ids != self.window.governed_sessions:
            _fail("Window must bind exact governed calendar grid")
        if self.initialization_anchor is None:
            if self.anchor_previous_slot:
                _fail("Previous-slot request requires explicit anchor")
        else:
            _text(self.initialization_anchor)
            if self.initialization_anchor not in ids:
                _fail("Required initialization anchor unavailable", SourceErrorCode.UNAVAILABLE)
            position = ids.index(self.initialization_anchor)
            if position > ids.index(self.window.target_session_id) or (self.anchor_previous_slot and position == 0):
                _fail("Required initialization prefix unavailable", SourceErrorCode.UNAVAILABLE)
        if len(self.required_session_ids) > self.max_sessions:
            _fail("History acquisition slot limit exceeded", SourceErrorCode.LIMIT)

    @property
    def required_session_ids(self) -> tuple[str, ...]:
        if self.initialization_anchor is None:
            return self.window.selected_sessions()
        ids = self.window.governed_sessions
        start = ids.index(self.initialization_anchor)-self.anchor_previous_slot
        end = ids.index(self.window.target_session_id)+(self.window.anchor == "completed_eod")
        return ids[start:end]

    @property
    def history_complete(self) -> bool:
        # Structural request sufficiency only; actual input admission remains pure.
        return self.window.history_complete and len(self.required_session_ids) >= self.window.count

    @property
    def dated_sessions(self) -> tuple[tuple[str, SessionSpec], ...]:
        wanted = set(self.required_session_ids)
        return tuple(pair for pair in self.calendar.dated_sessions if pair[1].session_id in wanted)

    @property
    def identity_digest(self) -> str:
        return _digest(asdict(self))

    def acquisition_request(self, request_id: str, kind: DataKind, instruments: tuple[str, ...],
                            snapshot_id: str, price_unit: PriceUnit, availability: AvailabilitySpec,
                            max_batch_rows: int = 1024, max_rows: int = 10000,
                            max_batches: int = 100, sampling: str = "none") -> AcquisitionRequest:
        if kind not in (DataKind.TRADE, DataKind.QUOTE, DataKind.BAR, DataKind.DAILY):
            _fail("Historical market acquisition kind required", SourceErrorCode.UNSUPPORTED)
        if not self.history_complete or not self.dated_sessions:
            _fail("Required governed history insufficient", SourceErrorCode.UNAVAILABLE)
        if kind == DataKind.DAILY and self.calendar.grid_kind != "utc_daily_intervals":
            _fail("Retained UTC daily cannot substitute supplied RTH daily", SourceErrorCode.UNSUPPORTED)
        slots = tuple(s for _, s in self.dated_sessions)
        if any(s.include_opening_auction or s.include_closing_auction for s in slots):
            _fail("Auction acquisition unsupported", SourceErrorCode.UNSUPPORTED)
        selection = "completed_intervals" if kind in (DataKind.BAR, DataKind.DAILY) else "event_half_open"
        try:
            return AcquisitionRequest(request_id, kind, self.calendar.namespace, instruments,
                self.required_session_ids, slots[0].open_ns, slots[-1].close_ns, snapshot_id,
                price_unit, availability, sampling=sampling, max_batch_rows=max_batch_rows,
                max_rows=max_rows, max_batches=max_batches, selection=selection)
        except SourceError as error:
            _fail("Governed acquisition request invalid", error.code)


def plan_history(calendar: GovernedCalendar, window: WindowSpec,
                 initialization_anchor: str | None = None, anchor_previous_slot: bool = False,
                 max_sessions: int = 4096) -> HistoryPlan:
    return HistoryPlan(calendar, window, initialization_anchor, anchor_previous_slot, max_sessions)


def make_history_context(calendar: GovernedCalendar, entity: EntityKey,
                         daily: CanonicalBatch | None, slot_coverage: tuple[Coverage, ...],
                         initialization_anchor: str | None = None,
                         action_admission: PolicyAdmission | None = None) -> HistoryContext:
    if type(calendar) is not GovernedCalendar or type(entity) is not EntityKey:
        _fail("Typed governed historical context inputs required")
    if type(slot_coverage) not in (tuple, list) or len(slot_coverage) != len(calendar.sessions) or any(type(c) is not Coverage for c in slot_coverage):
        _fail("One concrete caller coverage certificate per governed slot required")
    actual: set[str] = set()
    if daily is not None:
        if type(daily) is not CanonicalBatch or daily.kind != DataKind.DAILY or daily.metadata.namespace != calendar.namespace:
            _fail("Supplied compatible canonical daily history required")
        if daily.row_count > len(calendar.sessions) or daily.metadata.coverage.observed != daily.row_count:
            _fail("Daily population cannot match governed slot counts")
        try:
            validate_batch(daily)
        except ContractError:
            _fail("Supplied daily history structural validation failed")
        sessions = {s.session_id: s for s in calendar.sessions}
        columns = {c.name: c.values for c in daily.columns}
        for i in range(daily.row_count):
            identity = cast(str, columns["session_id"][i])
            if identity not in sessions or identity in actual or columns["instrument_id"][i] != entity.instrument_id:
                _fail("Daily row identity conflicts with governed history")
            session = sessions[identity]
            if (columns["start_ns"][i], columns["end_ns"][i]) != (session.open_ns, session.close_ns):
                _fail("Daily interval conflicts with exact governed session")
            actual.add(identity)
    for session, certificate in zip(calendar.sessions, slot_coverage):
        if certificate.expected != 1 or certificate.observed != int(session.session_id in actual):
            _fail("Caller slot certificate conflicts with actual daily row presence")
    try:
        return HistoryContext(entity, calendar.version, calendar.sessions, slot_coverage,
                              initialization_anchor, action_admission)
    except ContractError:
        _fail("Governed historical context validation failed")


@dataclass(frozen=True)
class ReferenceRequest:
    namespace: str
    snapshot_id: str
    instruments: tuple[str, ...]
    fact_kinds: tuple[str, ...]
    availability: AvailabilitySpec
    max_rows: int = 10000

    def __post_init__(self) -> None:
        _text(self.namespace)
        _text(self.snapshot_id)
        for name in ("instruments", "fact_kinds"):
            values = getattr(self, name)
            if type(values) not in (tuple, list) or not values:
                _fail("Concrete unique reference request identities required")
            for value in values:
                _text(value)
            if len(set(values)) != len(values):
                _fail("Unique reference request identities required")
            object.__setattr__(self, name, tuple(values))
        if type(self.availability) is not AvailabilitySpec:
            _fail("Typed reference C/K/E required")
        _count(self.max_rows, positive=True)

    @property
    def identity_digest(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True)
class ReferenceResolution:
    request: ReferenceRequest
    batch: CanonicalBatch | None
    disposition: str
    evidence_gaps: tuple[str, ...]
    identity_digest: str


def resolve_supplied_reference(request: ReferenceRequest,
                               batch: CanonicalBatch | None = None) -> ReferenceResolution:
    if type(request) is not ReferenceRequest:
        _fail("Typed supplied reference request required")
    if batch is None:
        return ReferenceResolution(request, None, "unavailable", ("not_supplied",),
                                   _digest([asdict(request), None]))
    if type(batch) is not CanonicalBatch or batch.kind != DataKind.REFERENCE or batch.metadata.namespace != request.namespace or batch.metadata.source.snapshot_id != request.snapshot_id:
        _fail("Supplied reference kind/namespace/revision conflict")
    if batch.row_count > request.max_rows:
        _fail("Supplied reference row limit exceeded", SourceErrorCode.LIMIT)
    if batch.metadata.coverage.observed != batch.row_count:
        _fail("Supplied reference coverage count conflict")
    try:
        validate_batch(batch)
    except ContractError:
        _fail("Supplied reference structural validation failed")
    columns = {c.name: c.values for c in batch.columns}
    if any(i not in request.instruments for i in columns["instrument_id"]) or any(k not in request.fact_kinds for k in columns["fact_kind"]):
        _fail("Supplied reference differs from requested identities/facts")
    gaps = set() if batch.metadata.coverage.complete else {"incomplete_coverage"}
    known = columns.get("known_at_ns", (None,)*batch.row_count)
    for stamp in known:
        reason = request.availability.knowledge_reason(cast(int | None, stamp))
        if reason is not None:
            gaps.add(reason)
    return ReferenceResolution(request, batch, "supplied", tuple(sorted(gaps)),
                               _digest([asdict(request), asdict(batch)]))
