"""Lossless supplied EF4-H quote dynamics and VWAP path inputs.

Maps SUPPLIED quote rows, trade rows, bar rows and declared gaps, grid edge facts, a prepared-series proof fact and the
interval bounds fact into canonical batches, and assembles the two producer requests with the closed parameter sets of
the core library (core `docs/ef4/QUOTE_VWAP_CONTRACT_PROPOSAL.json`, policies `ef4-quote1` and `ef4-vwap1`). Every value
the caller supplies (instrument, session, reference identity, fact kind, text, times, prices, sizes, eligibility,
knowledge, unit and adjustment basis, parameters) is carried through unchanged. Nothing is derived, filled, imputed,
sorted, rescaled, netted or inferred; no midpoint, spread, microprice, VWAP, slope or extremum mathematics lives here. The
library (`equity_features.ef4`) and the shared validators perform every admission, decision and refusal.

Coverage is always declared by the caller for every role that is delivered: `complete`, `incomplete` or `absent`. An
undeclared role with rows would be read as complete by the library, so there is no undeclared path here.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage,
    DataKind, EntityKey, ErrorCode, InputScope, IntervalCoverage, Parameter, PriceUnit, SessionSpec, SourceBinding,
    WindowSpec, validate_batch,
)

NAMESPACE = "SYN"
SOURCE_ID = "SYN-SRC"
SNAPSHOT_ID = "snap"
MAPPING_VERSION = "ef4-map1"

QUOTE_IDENTITY, QUOTE_ALGORITHM = "ef4.quote_dynamics", "ef4-quote-dynamics-v1"
VWAP_IDENTITY, VWAP_ALGORITHM = "ef4.vwap_path", "ef4-vwap-path-v1"

COMPLETE, INCOMPLETE, ABSENT = "complete", "incomplete", "absent"
REFERENCE_NAMES = ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns", "effective_end_ns",
                   "text", "known_at_ns")


def reference(text: str) -> str:
    """Closed reference identity `x1:` followed by the unpadded URL-safe base64 of the id text (the contract's `B(id)`)."""
    if type(text) is not str or not text.strip():
        raise ContractError(ErrorCode.INVALID_SCHEMA, "nonempty reference text required")
    return "x1:" + base64.urlsafe_b64encode(text.encode("utf-8")).rstrip(b"=").decode("ascii")


def price_unit(scale: int, currency: str) -> PriceUnit:
    return PriceUnit(scale, currency)


def adjustment(basis: str) -> AdjustmentSpec:
    """The one shared adjustment basis of a request (`raw` names no action snapshot or anchor)."""
    return AdjustmentSpec(basis=basis, policy_version="raw-v1" if basis == "raw" else "adjusted-v1",
                          action_snapshot="none" if basis == "raw" else "supplied", anchor="none" if basis == "raw" else "supplied")


@dataclass(frozen=True)
class Scope:
    """The declared delivery window of one batch: `[start_ns, end_ns)` (the interval for events and the grid span)."""

    start_ns: int
    end_ns: int
    name: str


@dataclass(frozen=True)
class Fact:
    """One supplied REFERENCE fact: every identity, kind, time, text and knowledge value as supplied."""

    instrument_id: str
    session_id: str
    reference_id: str
    fact_kind: str
    start_ns: int
    end_ns: int | None
    text: str | None
    known_at_ns: int | None


@dataclass(frozen=True)
class QuoteRow:
    """One supplied full quote state; sizes and prices may be null (the library decides what a null means)."""

    instrument_id: str
    session_id: str
    event_id: str
    event_ns: int
    order_key: int
    bid: int | None
    ask: int | None
    bid_size: int | None
    ask_size: int | None
    known_at_ns: int | None


@dataclass(frozen=True)
class TradeRow:
    """One supplied trade with its supplied eligibility flag."""

    instrument_id: str
    session_id: str
    event_id: str
    event_ns: int
    order_key: int
    eligible: bool
    price: int | None
    size: int | None
    known_at_ns: int | None


@dataclass(frozen=True)
class BarRow:
    """One supplied bar on a grid slot (start and end equal the slot edges); `incomplete` declares the delivered slot as a
    governed gap."""

    instrument_id: str
    session_id: str
    start_ns: int
    end_ns: int
    volume: int | None
    notional: int | None
    known_at_ns: int | None
    incomplete: bool = False
    ohlc: Mapping[str, int | None] | None = None  # supplied OHLC fields of this bar, when delivered


@dataclass(frozen=True)
class Gap:
    """A declared incomplete grid slot with no bar row (the declared slot coverage, not a row)."""

    start_ns: int
    end_ns: int


@dataclass(frozen=True)
class Request:
    """A complete supplied request: the fixed role slots, the closed configuration and the target entity."""

    producer: str
    slots: tuple[CanonicalBatch | None, ...]
    config: ConfigSpec
    entity: EntityKey


def _metadata(kind_scope: Scope, coverage: Coverage, unit: PriceUnit | None, *, input_id: str, basis: AdjustmentSpec,
              sampling: str = "none", intervals: tuple[IntervalCoverage, ...] = ()) -> BatchMetadata:
    return BatchMetadata(NAMESPACE, SourceBinding(SOURCE_ID, SNAPSHOT_ID, MAPPING_VERSION, input_id), coverage, unit, basis,
                         sampling, "shares", "declared", "reject",
                         InputScope(kind_scope.start_ns, kind_scope.end_ns, "ef4-supplied"), intervals)


def _batch(kind: DataKind, names: tuple[str, ...], rows: Sequence[tuple], metadata: BatchMetadata) -> CanonicalBatch:
    columns = tuple(Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    batch = CanonicalBatch(kind, columns, metadata)
    validate_batch(batch, required_fields=())
    return batch


def _event_coverage(count: int, declared: str, scope: Scope) -> tuple[Coverage, tuple[IntervalCoverage, ...]]:
    """Explicit aggregate and interval coverage of an event role. `absent` declares nothing and admits no row."""
    if declared not in (COMPLETE, INCOMPLETE, ABSENT):
        raise ContractError(ErrorCode.INVALID_CONFIG, "coverage must be declared complete, incomplete or absent")
    if declared == ABSENT:
        if count:
            raise ContractError(ErrorCode.INVALID_CONFIG, "absent coverage cannot carry delivered rows")
        return Coverage(None, 0, False), ()
    complete = declared == COMPLETE
    expected = count if complete else None
    return (Coverage(count, count, complete),
            (IntervalCoverage(scope.name, scope.start_ns, scope.end_ns, Coverage(expected, count, complete)),))


def reference_batch(facts: Sequence[Fact], *, scope: Scope, declared: str, input_id: str) -> CanonicalBatch:
    """REFERENCE role of supplied facts in the supplied order; `complete` declares the count, `incomplete` an unknown
    expected count, and `absent` admits no fact."""
    if declared not in (COMPLETE, INCOMPLETE, ABSENT):
        raise ContractError(ErrorCode.INVALID_CONFIG, "coverage must be declared complete, incomplete or absent")
    if declared == ABSENT and facts:
        raise ContractError(ErrorCode.INVALID_CONFIG, "absent coverage cannot carry delivered facts")
    count = len(facts)
    coverage = Coverage(count, count, True) if declared == COMPLETE else Coverage(None, count, False)
    rows = [(f.instrument_id, f.session_id, f.reference_id, f.fact_kind, f.start_ns, f.end_ns, f.text, f.known_at_ns)
            for f in facts]
    return _batch(DataKind.REFERENCE, REFERENCE_NAMES, rows,
                  _metadata(scope, coverage, None, input_id=input_id, basis=adjustment("raw")))


def quote_batch(rows: Sequence[QuoteRow], *, scope: Scope, sampling: str, unit: PriceUnit | None, declared: str,
                basis: AdjustmentSpec, input_id: str = "quotes") -> CanonicalBatch:
    """QUOTE role: full state rows in the supplied order, the supplied sampling, unit, basis and declared coverage."""
    names = ("instrument_id", "session_id", "event_id", "event_ns", "order_key", "bid", "ask", "bid_size", "ask_size",
             "known_at_ns")
    data = [(r.instrument_id, r.session_id, r.event_id, r.event_ns, r.order_key, r.bid, r.ask, r.bid_size, r.ask_size,
             r.known_at_ns) for r in rows]
    coverage, intervals = _event_coverage(len(data), declared, scope)
    return _batch(DataKind.QUOTE, names, data,
                  _metadata(scope, coverage, unit, input_id=input_id, basis=basis, sampling=sampling, intervals=intervals))


def trade_batch(rows: Sequence[TradeRow], *, scope: Scope, unit: PriceUnit | None, declared: str, basis: AdjustmentSpec,
                input_id: str = "trades") -> CanonicalBatch:
    """TRADE role: supplied eligibility, price and size; the supplied unit, basis and declared coverage."""
    names = ("instrument_id", "session_id", "event_id", "event_ns", "order_key", "eligible", "price", "size", "known_at_ns")
    data = [(r.instrument_id, r.session_id, r.event_id, r.event_ns, r.order_key, r.eligible, r.price, r.size, r.known_at_ns)
            for r in rows]
    coverage, intervals = _event_coverage(len(data), declared, scope)
    return _batch(DataKind.TRADE, names, data,
                  _metadata(scope, coverage, unit, input_id=input_id, basis=basis, intervals=intervals))


def bar_batch(rows: Sequence[BarRow], gaps: Sequence[Gap], *, scope: Scope, unit: PriceUnit | None, basis: AdjustmentSpec,
              input_id: str = "bars") -> CanonicalBatch:
    """BAR role: supplied rows and declared gaps. Each row carries a complete slot entry unless declared incomplete; each
    gap carries an incomplete entry with no row; a slot with neither is absent. The aggregate is incomplete (expected
    unknown) because the slot entries carry the declaration."""
    names = ("instrument_id", "session_id", "start_ns", "end_ns", "volume", "actual_notional", "known_at_ns")
    ohlc_names = tuple(sorted({k for r in rows if r.ohlc is not None for k in r.ohlc}))
    names = names + ohlc_names  # OHLC columns exist only when a supplied bar carries them
    data = [(r.instrument_id, r.session_id, r.start_ns, r.end_ns, r.volume, r.notional, r.known_at_ns)
            + tuple(None if r.ohlc is None else r.ohlc.get(k) for k in ohlc_names) for r in rows]
    intervals = [IntervalCoverage(f"slot:{r.start_ns}:{r.end_ns}", r.start_ns, r.end_ns,
                                  Coverage(1, 1, not r.incomplete)) for r in rows]
    intervals += [IntervalCoverage(f"slot:{g.start_ns}:{g.end_ns}", g.start_ns, g.end_ns, Coverage(1, 0, False)) for g in gaps]
    coverage = Coverage(None, len(data), False)
    return _batch(DataKind.BAR, names, data,
                  _metadata(scope, coverage, unit, input_id=input_id, basis=basis, intervals=tuple(intervals)))


def quote_parameters(*, policy_version: str, sampling: str, evidence_limit: int) -> tuple[Parameter, ...]:
    """The closed quote-dynamics parameter set, in the library order."""
    return (Parameter("policy_version", policy_version), Parameter("sampling", sampling),
            Parameter("evidence_limit", evidence_limit))


def vwap_parameters(*, policy_version: str, series_source: str, evidence_limit: int, grid_version: str | None = None,
                    series_policy_id: str | None = None) -> tuple[Parameter, ...]:
    """The closed VWAP-path parameter set; grid and series policy are present exactly when the caller supplies them."""
    params = [Parameter("policy_version", policy_version), Parameter("series_source", series_source),
              Parameter("evidence_limit", evidence_limit)]
    if grid_version is not None:
        params.append(Parameter("grid_version", grid_version))
    if series_policy_id is not None:
        params.append(Parameter("series_policy_id", series_policy_id))
    return tuple(params)


def _config(identity: str, algorithm: str, params: tuple[Parameter, ...], session: SessionSpec, timing: AvailabilitySpec,
            unit: PriceUnit | None) -> ConfigSpec:
    """The closed envelope of the library `make_config`: target session, one shared adjustment, the explicit unit."""
    if type(session) is not SessionSpec:
        raise ContractError(ErrorCode.INVALID_CONFIG, "concrete session required")
    return ConfigSpec(identity, algorithm, params, session,
                      WindowSpec(1, session.session_id, (session.session_id,), "prior_only"), timing, adjustment("raw"),
                      unit)


def availability(market_cutoff_ns: int, knowledge_cutoff_ns: int) -> AvailabilitySpec:
    """Causal known_at timing: market cutoff and knowledge cutoff with evaluation at the later of the two."""
    return AvailabilitySpec(market_cutoff_ns, knowledge_cutoff_ns, max(knowledge_cutoff_ns, market_cutoff_ns), "known_at")


def quote_request(*, entity: EntityKey, session: SessionSpec, timing: AvailabilitySpec, config_unit: PriceUnit | None,
                  params: tuple[Parameter, ...], bounds: CanonicalBatch | None,
                  quotes: CanonicalBatch | None) -> Request:
    """ef4.quote_dynamics request: slots (bounds, quotes); bounds is required by the library and quotes is nullable."""
    config = _config(QUOTE_IDENTITY, QUOTE_ALGORITHM, params, session, timing, config_unit)
    return Request("quote_dynamics", (bounds, quotes), config, entity)


def vwap_request(*, entity: EntityKey, session: SessionSpec, timing: AvailabilitySpec, config_unit: PriceUnit | None,
                 params: tuple[Parameter, ...], bounds: CanonicalBatch | None, grid: CanonicalBatch | None,
                 trades: CanonicalBatch | None, bars: CanonicalBatch | None, proof: CanonicalBatch | None) -> Request:
    """ef4.vwap_path request: slots (bounds, grid, trades, bars, proof); bounds is required, the others are nullable."""
    config = _config(VWAP_IDENTITY, VWAP_ALGORITHM, params, session, timing, config_unit)
    return Request("vwap_path", (bounds, grid, trades, bars, proof), config, entity)


__all__ = [
    "ABSENT", "BarRow", "COMPLETE", "Fact", "Gap", "INCOMPLETE", "NAMESPACE", "QuoteRow", "Request", "Scope", "TradeRow",
    "adjustment", "availability", "bar_batch", "price_unit", "quote_batch", "quote_parameters", "quote_request",
    "reference", "reference_batch", "trade_batch", "vwap_parameters", "vwap_request",
]
