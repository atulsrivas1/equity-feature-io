"""Supplied EF4 remaining equity statistical projections (contract I2, EQ-172): session projection, bar projection,
relative excess and rate projection, mapped from SUPPLIED inputs.

Maps supplied daily closes, epoch bars, leg witnesses, sector membership facts and tape-window aggregates into canonical
batches (one batch per role; REFERENCE facts in the contract expansion order), and builds the four `ConfigSpec`
envelopes by hand (the same parameter layout as the core builders, with the supplied parameters passed through
unvalidated, so the core closed-envelope decoder refuses bad or unknown parameters). Pinned rulings (core
`docs/ef4/PATH_PROJECTIONS_IMPLEMENTATION.md`): one BAR batch per role; the epoch bars arrive as one flat list, and each
bar is one slot with coverage `bar:<i>` (session projection: `slot:<i>`); declared aggregate coverage on every batch;
`core_benchmark_ids` is canonical compact JSON text.

This module imports only `equity_feature_contracts` and the EF3 daily grid codec of this package. It does not import the
core library: the caller builds the core grid objects from the codecs, checks the envelopes against the core builders if
it wishes, and runs the core computation. Nothing is derived, filled, bridged, rescaled, sorted by value, inferred from a
sector name or computed here; the shared canonical-batch rules (`validate_batch`) run while batches are built. Identities
are supplied through `ProjectionIds`; no entity, instrument, benchmark, session, grid or source id is fixed here.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage,
    DataKind, EntityKey, ErrorCode, InputScope, IntervalCoverage, Parameter, PriceUnit, SessionSpec, SourceBinding,
    WindowSpec, validate_batch,
)

from .relative_rv import DailyGrid as DailyGridCodec, GRID_SCHEMA as DAILY_GRID_SCHEMA

# Identities, algorithms and schemas of the frozen contract (core `equity_features.ef4`, checked by the driver).
SESSION_IDENTITY, SESSION_ALGORITHM = "ef4.session_projection", "ef4-session-projection-v1"
BAR_IDENTITY, BAR_ALGORITHM = "ef4.bar_projection", "ef4-bar-projection-v1"
BAR_GRID_SCHEMA = "equity-features.ef4-bar-grid.v1"
RELATIVE_IDENTITY, RELATIVE_ALGORITHM = "ef4.relative_excess", "ef4-relative-excess-v1"
RATE_IDENTITY, RATE_ALGORITHM = "ef4.rate_projection", "ef4-rate-projection-v1"

MAPPING_VERSION = "ef4-proj-map1"
SOURCE_ID = "SYN-SRC"
SNAPSHOT_ID = "snap-1"
SCOPE_POLICY = "ef4-supplied-input"
EPOCH_NS = 1_700_000_000_000_000_000  # origin of the compact slot clock (wire_expansion of the contract)
BAR_NS = 60 * 10**9                   # epoch bar spacing of the compact clock
DAY_NS = 86_400 * 10**9               # daily slot spacing of the compact clock; one whole day per daily slot
SECOND_NS = 10**9
KNOWN_DEFAULT = 50                    # default compact known_at token (ka)
PLACEHOLDER_CLOSE = 1                 # close of an unknown-availability slot: never READY, never used
DELIVERY_MODE = "batch"


class ProjectionStageError(Exception):
    """A refusal tagged with the layer that raised it: `io` (supplied-input mapping and the shared batch rules) or
    `library` (envelope and computation tier, which the core library decides)."""

    def __init__(self, stage: str, error: BaseException) -> None:
        super().__init__(f"{stage}: {error}")
        self.stage = stage
        self.error = error
        self.code = getattr(error, "code", None)


@dataclass(frozen=True)
class BarGridCodec:
    """Local codec of the core reset-epoch bar grid: same fields, schema and digest (checked by the driver)."""

    instrument_id: str
    calendar_id: str
    grid_id: str
    revision: str
    session: SessionSpec
    bar_ns: int
    bar_count: int
    target_index: int

    def to_json(self) -> str:
        return json.dumps({"schema": BAR_GRID_SCHEMA, **asdict(self)}, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("ascii")).hexdigest()

    @property
    def target_end_ns(self) -> int:
        return self.session.open_ns + (self.target_index + 1) * self.bar_ns


@dataclass(frozen=True)
class ProjectionIds:
    """Caller-bound identities. `names` maps the supplied (compact) instrument, benchmark and session names to the bound
    ids; an unmapped name is passed through unchanged so that the library, not this layer, decides on it."""

    namespace: str
    instrument_id: str
    calendar_id: str
    grid_id: str
    revision: str
    day_session_prefix: str
    bar_session_id: str
    target_session_id: str
    names: Mapping[str, str] = field(default_factory=dict)

    def bind(self, name: Any) -> Any:
        return self.names.get(name, name) if isinstance(name, str) else name


@dataclass(frozen=True)
class ProjectionRequest:
    """Everything the core computation needs, as plain contract objects and codecs."""

    producer: str
    grid: Any                      # DailyGridCodec or BarGridCodec (None for relative excess and rate projection)
    batches: tuple[CanonicalBatch | None, ...]
    config: ConfigSpec
    features: tuple[str, ...]
    capability: str
    entity: EntityKey | None


def _source(input_id: str) -> SourceBinding:
    return SourceBinding(SOURCE_ID, SNAPSHOT_ID, MAPPING_VERSION, input_id)


def _unit(value: Mapping[str, Any] | None) -> PriceUnit | None:
    if value is None:
        return None
    return PriceUnit(value["scale"], value["currency"])


def _adjustment(basis: Any) -> AdjustmentSpec:
    return AdjustmentSpec() if basis == "raw" else AdjustmentSpec(basis=basis)


def _availability(market_ns: int, knowledge_ns: int) -> AvailabilitySpec:
    return AvailabilitySpec(market_ns, knowledge_ns, max(knowledge_ns, market_ns), "known_at")


def _known(token: Any, knowledge_ns: int | None, compact_k: int | None) -> int | None:
    """Compact known_at token: `None` is unknown availability. With `compact_k` (session and bar notation) token t maps to
    knowledge_ns - (compact_k - t) seconds; without it (relative and rate notation) the token is the instant itself."""
    if token is None:
        return None
    if compact_k is None:
        return token
    return knowledge_ns - (compact_k - token) * SECOND_NS


def _unpack(slot: Any) -> tuple[str, Any, Any, dict[str, Any]]:
    """(state, payload, known token, wire overrides). State is `row`, `absent`, `gap`, `empty` or `null`."""
    if isinstance(slot, str):
        return slot, None, KNOWN_DEFAULT, {}
    if isinstance(slot, dict) and "wire" in slot:
        wire = dict(slot["wire"])
        payload = wire.pop("row", None)
        token = KNOWN_DEFAULT
        if isinstance(payload, dict) and "row" in payload:
            token = payload["ka"] if "ka" in payload else KNOWN_DEFAULT
            payload = payload["row"]
        return "row", payload, token, wire
    if isinstance(slot, dict) and "row" in slot:
        return "row", slot["row"], slot["ka"] if "ka" in slot else KNOWN_DEFAULT, {}
    return "row", slot, KNOWN_DEFAULT, {}


def _aggregate(expected: int, observed: int) -> Coverage:
    return Coverage(expected, observed, expected == observed)


def _checked(batch: CanonicalBatch, availability: AvailabilitySpec | None) -> CanonicalBatch:
    """The shared canonical-batch rules at build time (the I/O tier)."""
    validate_batch(batch, availability=availability, required_fields=())
    return batch


# ------------------------------------------------------------------------------------------ session projection
def session_projection_inputs(fx: Mapping[str, Any], ctx: Mapping[str, Any], ids: ProjectionIds, *,
                              input_id: str = "daily") -> tuple[CanonicalBatch, DailyGridCodec, AvailabilitySpec]:
    """Daily close-only BAR role on the governed daily grid: one slot per supplied close, target slot explicit."""
    closes = fx["closes"]
    count = len(closes)
    target = fx["target"] if "target" in fx else count - 1
    sessions = tuple(SessionSpec(ids.namespace, f"{ids.day_session_prefix}{i}", EPOCH_NS + i * DAY_NS,
                                 EPOCH_NS + (i + 1) * DAY_NS, "UTC") for i in range(count))
    grid = DailyGridCodec(ids.instrument_id, ids.calendar_id, ids.grid_id, ids.revision, sessions, target)
    market = sessions[-1].close_ns
    knowledge = market + fx["K"] * SECOND_NS
    availability = _availability(market, knowledge)
    rows: list[tuple[Any, ...]] = []
    intervals: list[IntervalCoverage] = []
    for index, slot in enumerate(closes):
        state, payload, token, wire = _unpack(slot)
        session = sessions[index]
        instrument = ids.bind(wire["inst"]) if "inst" in wire else ids.instrument_id
        session_id = ids.bind(wire["ss"]) if "ss" in wire else session.session_id
        start = wire.get("start", session.open_ns)
        end = wire.get("end", session.close_ns)
        name = f"slot:{index}"
        if state == "absent":
            continue
        if state == "gap":
            intervals.append(IntervalCoverage(name, session.open_ns, session.close_ns, Coverage(1, 0, False)))
            continue
        close = None if state == "null" else (PLACEHOLDER_CLOSE if payload is None else payload)
        rows.append((instrument, session_id, start, end, close, _known(token, knowledge, fx["K"])))
        intervals.append(IntervalCoverage(name, session.open_ns, session.close_ns, Coverage(1, 1, True)))
    names = ("instrument_id", "session_id", "start_ns", "end_ns", "close", "known_at_ns")
    columns = tuple(Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    metadata = BatchMetadata(ids.namespace, _source(input_id), _aggregate(count, len(rows)),
                             _unit(ctx["batch"]["unit"]), _adjustment(ctx["batch"]["adjustment"]), "none", "shares",
                             "declared", "reject", InputScope(sessions[0].open_ns, sessions[-1].close_ns, SCOPE_POLICY),
                             tuple(intervals))
    return _checked(CanonicalBatch(DataKind.BAR, columns, metadata), availability), grid, availability


# ------------------------------------------------------------------------------------------ bar projection
def bar_projection_inputs(fx: Mapping[str, Any], ctx: Mapping[str, Any], ids: ProjectionIds, *,
                          input_id: str = "bars") -> tuple[CanonicalBatch, BarGridCodec, AvailabilitySpec]:
    """The reset-epoch bars of one supplied flat list (one entry per bar slot) as ONE batch for the role; per-slot
    coverage is named `bar:<i>`. The chunked R17 delivery is not modelled here: the caller supplies one list."""
    bars = fx["bars"]
    count = len(bars)
    target = fx["target"] if "target" in fx else count - 1
    session = SessionSpec(ids.namespace, ids.bar_session_id, EPOCH_NS, EPOCH_NS + count * BAR_NS, "UTC")
    grid = BarGridCodec(ids.instrument_id, ids.calendar_id, ids.grid_id, ids.revision, session, BAR_NS, count, target)
    market = session.close_ns
    knowledge = market + fx["K"] * SECOND_NS
    availability = _availability(market, knowledge)
    rows: list[dict[str, Any]] = []
    intervals: list[IntervalCoverage] = []
    for index, slot in enumerate(bars):
        state, payload, token, wire = _unpack(slot)
        start = EPOCH_NS + index * BAR_NS
        end = start + BAR_NS
        name = f"bar:{index}"
        if state == "absent":
            continue
        if state == "gap":
            intervals.append(IntervalCoverage(name, start, end, Coverage(1, 0, False)))
            continue
        if state == "empty":
            ohlc, volume, notional = [None] * 4, 0, 0
        elif state == "null":
            ohlc, volume, notional = [None] * 4, None, None
        else:
            ohlc, volume = list(payload[:4]), payload[4]
            notional = payload[5] if len(payload) > 5 else None
        instrument = ids.bind(wire["inst"]) if "inst" in wire else ids.instrument_id
        session_id = ids.bind(wire["ss"]) if "ss" in wire else ids.bar_session_id
        rows.append({"instrument_id": instrument, "session_id": session_id, "start_ns": wire.get("start", start),
                     "end_ns": wire.get("end", end), "open": ohlc[0], "high": ohlc[1], "low": ohlc[2],
                     "close": ohlc[3], "volume": volume, "actual_notional": notional,
                     "known_at_ns": _known(token, knowledge, fx["K"])})
        intervals.append(IntervalCoverage(name, start, end, Coverage(1, 1, True)))
    names = ["instrument_id", "session_id", "start_ns", "end_ns", "open", "high", "low", "close", "volume"]
    if fx["notional_column"]:
        names.append("actual_notional")
    names.append("known_at_ns")
    columns = [Column(name, tuple(row[name] for row in rows)) for name in names]
    metadata = BatchMetadata(ids.namespace, _source(input_id), _aggregate(count, len(rows)),
                             _unit(ctx["batch"]["unit"]), _adjustment(ctx["batch"]["adjustment"]), "none", "shares",
                             "declared", "reject", InputScope(session.open_ns, session.close_ns, SCOPE_POLICY),
                             tuple(intervals))
    return _checked(CanonicalBatch(DataKind.BAR, tuple(columns), metadata), availability), grid, availability


# ------------------------------------------------------------------------------------------ REFERENCE facts
def _reference_id(inner: str) -> str:
    """Closed x1 reference grammar: `x1:` followed by the URL-safe base64 (no padding) of the component text."""
    return "x1:" + base64.urlsafe_b64encode(inner.encode("utf-8")).rstrip(b"=").decode("ascii")


def _reference_batch(rows: list[dict[str, Any]], *, namespace: str, input_id: str, unit: PriceUnit | None,
                     adjustment: AdjustmentSpec) -> CanonicalBatch:
    """One REFERENCE batch in the contract expansion order; the price column exists only when prices are supplied."""
    names = ["fact_kind", "instrument_id", "session_id", "reference_id", "effective_start_ns", "effective_end_ns",
             "known_at_ns"]
    if any(row["price"] is not None for row in rows):
        names.append("price")
    names.append("text")
    columns = tuple(Column(name, tuple(row[name] for row in rows)) for name in names)
    metadata = BatchMetadata(namespace, _source(input_id), _aggregate(len(rows), len(rows)), unit, adjustment,
                             "none", "shares", "declared", "reject", None, ())
    return CanonicalBatch(DataKind.REFERENCE, columns, metadata)


def _fact_row(kind: str, instrument: Any, session: Any, reference_id: str, start: int, end: int | None,
              known: int | None, price: Any, text: Any) -> dict[str, Any]:
    return {"fact_kind": kind, "instrument_id": instrument, "session_id": session, "reference_id": reference_id,
            "effective_start_ns": start, "effective_end_ns": end, "known_at_ns": known, "price": price, "text": text}


def _sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row["effective_start_ns"], row["reference_id"]))


def _leg_rows(facts: Sequence[Mapping[str, Any]], ids: ProjectionIds, *, default_profile: str | None) -> list[dict[str, Any]]:
    """Leg witnesses as REFERENCE rows; a start without `pf` takes `default_profile` (window_start for rate legs)."""
    rows = []
    for fact in facts:
        instrument = ids.bind(fact["inst"])
        session = ids.bind(fact["ss"])
        slot = fact.get("slot", "A")
        known = _known(fact.get("ka"), None, None)
        if fact["kind"] == "start":
            kind = "ef4.leg.start"
            profile = fact.get("pf", default_profile)
            text = f"profile={profile};slot={slot};rev={fact['rev']};act={fact['act']}"
            reference_id = _reference_id(f"{instrument}#start#{profile}#{slot}")
        else:
            kind = "ef4.leg.end"
            text = f"slot={slot};rev={fact['rev']};act={fact['act']}"
            reference_id = _reference_id(f"{instrument}#end#{slot}")
        rows.append(_fact_row(kind, instrument, session, reference_id, fact["t"], None, known, fact["p"], text))
    return _sorted_rows(rows)


def relative_excess_inputs(fx: Mapping[str, Any], ctx: Mapping[str, Any], ids: ProjectionIds, *,
                           legs_input_id: str = "legs", membership_input_id: str = "membership") -> dict[str, Any]:
    """Leg witnesses (role `legs`) and sector membership (role `membership`) for the target instrument."""
    target = ids.bind(fx["instrument"])
    facts = fx["facts"]
    end = next((f for f in facts if f["kind"] == "end" and f["inst"] == fx["instrument"]), None)
    session_id = ids.bind(end["ss"]) if end is not None else ids.target_session_id
    unit = _unit(ctx["batch"]["unit"])
    adjustment = _adjustment(ctx["batch"]["adjustment"])
    legs = _leg_rows(facts, ids, default_profile=None)
    legs_batch = _checked(_reference_batch(legs, namespace=ids.namespace, input_id=legs_input_id, unit=unit,
                                           adjustment=adjustment), None) if legs else None
    members = []
    for member in fx["membership"]:
        instrument = ids.bind(member["inst"])
        members.append(_fact_row("ef4.sector.membership", instrument, session_id,
                                 _reference_id(f"{instrument}#membership"), member["eff"], None,
                                 _known(member.get("ka"), None, None), None, ids.bind(member["bound"])))
    membership_batch = _checked(_reference_batch(_sorted_rows(members), namespace=ids.namespace,
                                                 input_id=membership_input_id, unit=None,
                                                 adjustment=adjustment), None) if members else None
    times = [f["t"] for f in facts] + [fx["C"]]
    session = SessionSpec(ids.namespace, session_id, min(times) - 1, max(times) + 1, "UTC")
    return {"batches": (legs_batch, membership_batch), "session": session,
            "availability": _availability(fx["C"], fx["K"]), "entity": EntityKey(target, session_id)}


def rate_projection_inputs(fx: Mapping[str, Any], ctx: Mapping[str, Any], ids: ProjectionIds, *,
                           tape_input_id: str = "tape", legs_input_id: str = "legs") -> dict[str, Any]:
    """Tape-window aggregates (role `tape`) and window_start legs (role `legs`) for the target instrument."""
    target = ids.bind(fx["instrument"])
    facts = fx["legs"]
    end = next((f for f in facts if f["kind"] == "end"), None)
    session_id = ids.bind(end["ss"]) if end is not None else ids.target_session_id
    unit = _unit(ctx["batch"]["unit"])
    adjustment = _adjustment(ctx["batch"]["adjustment"])
    tape_rows = []
    for fact in fx["tape"]:
        kind = fact["kind"]
        text = fact["v"] if isinstance(fact["v"], str) else str(fact["v"])
        tape_rows.append(_fact_row(f"ef4.tape.{kind}", target, session_id, _reference_id(f"window#{kind}"), fact["s"],
                                   fact["e"], _known(fact.get("ka"), None, None), None, text))
    has_notional = any(f["kind"] == "notional" for f in fx["tape"])
    tape_batch = _checked(_reference_batch(_sorted_rows(tape_rows), namespace=ids.namespace, input_id=tape_input_id,
                                           unit=unit if has_notional else None, adjustment=adjustment),
                          None) if tape_rows else None
    legs = _leg_rows(facts, ids, default_profile="window_start")
    legs_batch = _checked(_reference_batch(legs, namespace=ids.namespace, input_id=legs_input_id, unit=unit,
                                           adjustment=adjustment), None) if legs else None
    times = [f["s"] for f in fx["tape"]] + [f["e"] for f in fx["tape"]] + [f["t"] for f in facts] + [fx["C"]]
    session = SessionSpec(ids.namespace, session_id, min(times) - 1, max(times) + 1, "UTC")
    return {"batches": (tape_batch, legs_batch), "session": session,
            "availability": _availability(fx["C"], fx["K"]), "entity": EntityKey(target, session_id)}


# ------------------------------------------------------------------------------------------ envelopes by hand
_ENVELOPE_KEYS = {
    "session_projection": ("policy_version", "window", "evidence_limit"),
    "bar_projection": ("policy_version", "evidence_limit"),
    "relative_excess": ("policy_version", "alignment_tolerance_ns", "max_endpoint_age_ns", "evidence_limit",
                        "primary_benchmark_id", "secondary_benchmark_id", "sector_benchmark_id", "window_ns",
                        "core_profile", "core_benchmark_ids"),
    "rate_projection": ("policy_version", "window_ns", "max_endpoint_age_ns", "evidence_limit",
                        "alignment_tolerance_ns", "adjacency"),
}
_BOUND_KEYS = frozenset({"primary_benchmark_id", "secondary_benchmark_id", "sector_benchmark_id"})


def _scalar(value: Any) -> Any:
    """Canonical compact JSON text for a supplied list of ids (as the core `encode_core_ids`); other values unchanged."""
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), separators=(",", ":"), ensure_ascii=True)
    return value


def _parameters(producer: str, p: Mapping[str, Any], ids: ProjectionIds) -> list[Parameter]:
    """Supplied parameters in the producer's envelope order, bound where they name instruments or benchmarks; a key
    the supplied fixture omits is omitted here, so the core decoder refuses it. Unknown keys are appended unchanged."""
    out = []
    for key in _ENVELOPE_KEYS[producer]:
        if key not in p:
            continue
        value = ids.bind(p[key]) if key in _BOUND_KEYS else p[key]
        if key == "core_benchmark_ids" and isinstance(value, (list, tuple)):
            value = [ids.bind(x) for x in value]
        out.append(Parameter(key, _scalar(value)))
    for key, value in p.items():
        if key not in _ENVELOPE_KEYS[producer]:
            out.append(Parameter(key, _scalar(value)))
    return out


def _grid_parameters(schema: str, digest: str) -> tuple[Parameter, Parameter]:
    return Parameter("grid_schema", schema), Parameter("grid_sha256", digest)


def _config(producer: str, fx: Mapping[str, Any], ids: ProjectionIds, grid: Any, batches_session: SessionSpec | None,
            availability: AvailabilitySpec, adjustment: AdjustmentSpec, unit: PriceUnit | None) -> ConfigSpec:
    p = fx["params"]
    if unit is None:
        raise ProjectionStageError("library", ContractError(ErrorCode.INVALID_UNIT, "an explicit PriceUnit is required"))
    parameters = _parameters(producer, p, ids)
    if producer == "session_projection":
        target = grid.target
        return ConfigSpec(SESSION_IDENTITY, SESSION_ALGORITHM,
                          tuple(parameters) + _grid_parameters(DAILY_GRID_SCHEMA, grid.digest), target,
                          WindowSpec(len(grid.sessions), target.session_id,
                                     tuple(s.session_id for s in grid.sessions), "completed_eod"),
                          availability, adjustment, unit)
    if producer == "bar_projection":
        session = grid.session
        return ConfigSpec(BAR_IDENTITY, BAR_ALGORITHM,
                          tuple(parameters) + _grid_parameters(BAR_GRID_SCHEMA, grid.digest), session,
                          WindowSpec(grid.bar_count, session.session_id, (session.session_id,), "completed_eod"),
                          availability, adjustment, unit)
    identity, algorithm = ((RELATIVE_IDENTITY, RELATIVE_ALGORITHM) if producer == "relative_excess"
                           else (RATE_IDENTITY, RATE_ALGORITHM))
    return ConfigSpec(identity, algorithm, tuple(parameters), batches_session,
                      WindowSpec(1, batches_session.session_id, (batches_session.session_id,), "prior_only"),
                      availability, adjustment, unit)


def build_request(producer: str, fx: Mapping[str, Any], ctx: Mapping[str, Any],
                  ids: ProjectionIds) -> ProjectionRequest:
    """Supplied inputs (I/O tier) and the core configuration envelope (hand-built). Computation and the delivery
    capability check belong to the caller (the core library).

    `ctx` carries config_unit, batch unit and adjustment, config_adjustment, capability and features exactly as the
    harness default context does."""
    features = tuple(ctx["features"])
    config_unit = _unit(ctx["config_unit"])
    try:
        config_adjustment = _adjustment(ctx["config_adjustment"])
        if producer == "session_projection":
            batch, grid, availability = session_projection_inputs(fx, ctx, ids)
            batches: tuple[CanonicalBatch | None, ...] = (batch,)
            entity = None
            session = None
        elif producer == "bar_projection":
            batch, grid, availability = bar_projection_inputs(fx, ctx, ids)
            batches = (batch,)
            entity = None
            session = None
        elif producer == "relative_excess":
            inputs = relative_excess_inputs(fx, ctx, ids)
            batches, grid = inputs["batches"], None
            availability, session, entity = inputs["availability"], inputs["session"], inputs["entity"]
        elif producer == "rate_projection":
            inputs = rate_projection_inputs(fx, ctx, ids)
            batches, grid = inputs["batches"], None
            availability, session, entity = inputs["availability"], inputs["session"], inputs["entity"]
        else:
            raise ContractError(ErrorCode.INVALID_CONFIG, "unknown producer")
    except ContractError as error:
        raise ProjectionStageError("io", error) from error
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ProjectionStageError("io", ContractError(ErrorCode.INVALID_SCHEMA,
                                                       f"unreadable supplied input: {error}")) from error
    try:
        config = _config(producer, fx, ids, grid, session, availability, config_adjustment, config_unit)
    except ContractError as error:
        raise ProjectionStageError("library", error) from error
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ProjectionStageError("library", ContractError(ErrorCode.INVALID_CONFIG,
                                                            f"unreadable supplied parameters: {error}")) from error
    return ProjectionRequest(producer, grid, batches, config, features, ctx["capability"], entity)


__all__ = ["BarGridCodec", "ProjectionIds", "ProjectionRequest", "ProjectionStageError", "bar_projection_inputs",
           "build_request", "rate_projection_inputs", "relative_excess_inputs", "session_projection_inputs",
           "DELIVERY_MODE", "MAPPING_VERSION"]
