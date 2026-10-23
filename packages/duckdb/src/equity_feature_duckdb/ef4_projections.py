"""Supplied EF4 remaining equity statistical projections (contract I2, EQ-172): session projection, bar projection,
relative excess and rate projection, mapped from SUPPLIED inputs.

Maps supplied daily closes, epoch bars, leg witnesses, sector membership facts and tape-window aggregates into canonical
batches (one batch per role; REFERENCE facts in the contract expansion order), builds the four core configurations with
the core builders (`ef4-proj1`, `ef4-rel1`, `ef4-rate1`) and runs the core computation. Rulings pinned here (core
`docs/ef4/PATH_PROJECTIONS_IMPLEMENTATION.md`): one BAR batch per role with per-slot coverage named `bar:<i>` (session
projection: `slot:<i>`), declared aggregate coverage on every batch, `core_benchmark_ids` passed to the builder as a tuple
(the builder encodes it as canonical JSON text), REFERENCE evidence boundary `ordinary` (library), and the daily-role
DUPLICATE check (library).

Nothing is derived, filled, bridged, rescaled, sorted by value, inferred from a sector name or computed here. Every
identity, cutoff, unit, admission, refusal and value is the library's; the only checks made here are the shared
canonical-batch rules (`validate_batch`) that run while a batch is built, plus the delivery-mode check. Identities are
supplied by the caller through `ProjectionIds`; no entity, instrument, benchmark, session, grid or source id is fixed here.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage,
    DataKind, EntityKey, ErrorCode, FeatureResult, InputScope, IntervalCoverage, Parameter, PriceUnit, SessionSpec,
    SourceBinding, validate_batch,
)
from equity_features.ef3 import DailyGrid
from equity_features.ef4 import (
    BarGrid, build_bar_projection_config, build_rate_projection_config, build_relative_excess_config,
    build_session_projection_config, compute_bar_projection, compute_rate_projection, compute_relative_excess,
    compute_session_projection, encode_core_ids, require_ef4_path_projections_capability,
)

MAPPING_VERSION = "ef4-proj-map1"
SOURCE_ID = "SYN-SRC"
SNAPSHOT_ID = "snap-1"
SCOPE_POLICY = "ef4-supplied-input"
EPOCH_NS = 1_700_000_000_000_000_000  # origin of the compact slot clock (wire_expansion of the contract)
BAR_NS = 60 * 10**9                   # epoch bar spacing of the compact clock
DAY_NS = 86_400 * 10**9               # daily slot spacing of the compact clock
DAY_SESSION_NS = DAY_NS               # one whole day per governed daily slot of the compact clock
SECOND_NS = 10**9
KNOWN_DEFAULT = 50                    # default compact known_at token (ka)
PLACEHOLDER_CLOSE = 1                 # close of an unknown-availability slot: never READY, never used
DELIVERY_MODE = "batch"


class ProjectionStageError(Exception):
    """A refusal tagged with the layer that raised it: `io` (this adapter and the shared batch rules) or `library`."""

    def __init__(self, stage: str, error: BaseException) -> None:
        super().__init__(f"{stage}: {error}")
        self.stage = stage
        self.error = error
        self.code = getattr(error, "code", None)


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


def _known(token: Any, knowledge_ns: int, compact_k: int) -> int | None:
    """Compact known_at token: `None` is unknown availability; otherwise the instant `token` ns (or the compact
    offset from the cutoff when `compact_k` is given: token t maps to knowledge_ns - (compact_k - t) seconds)."""
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
                              input_id: str = "daily") -> tuple[CanonicalBatch, DailyGrid, AvailabilitySpec]:
    """Daily close-only BAR role on the governed daily grid (one slot per supplied close, target slot explicit)."""
    closes = fx["closes"]
    count = len(closes)
    target = fx["target"] if "target" in fx else count - 1
    sessions = tuple(SessionSpec(ids.namespace, f"{ids.day_session_prefix}{i}", EPOCH_NS + i * DAY_NS,
                                 EPOCH_NS + i * DAY_NS + DAY_SESSION_NS, "UTC") for i in range(count))
    grid = DailyGrid(ids.instrument_id, ids.calendar_id, ids.grid_id, ids.revision, sessions, target)
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
        if state == "null":
            close, known = None, _known(token, knowledge, fx["K"])
        else:
            close = PLACEHOLDER_CLOSE if payload is None else payload
            known = _known(token, knowledge, fx["K"])
        rows.append((instrument, session_id, start, end, close, known))
        intervals.append(IntervalCoverage(name, session.open_ns, session.close_ns, Coverage(1, 1, True)))
    names = ("instrument_id", "session_id", "start_ns", "end_ns", "close", "known_at_ns")
    batch = _bar_batch(names, rows, intervals, count, InputScope(sessions[0].open_ns, sessions[-1].close_ns,
                                                              SCOPE_POLICY), ids.namespace, input_id,
                       _unit(ctx["batch"]["unit"]), _adjustment(ctx["batch"]["adjustment"]))
    return _checked(batch, availability), grid, availability


# ------------------------------------------------------------------------------------------ bar projection
def bar_projection_inputs(fx: Mapping[str, Any], ctx: Mapping[str, Any], ids: ProjectionIds, *,
                          input_id: str = "bars") -> tuple[CanonicalBatch, BarGrid, AvailabilitySpec]:
    """Reset-epoch R17-style BAR delivery as ONE batch per role: chunks are concatenated here, coverage is `bar:<i>`."""
    bars = fx["bars"]
    count = len(bars)
    target = fx["target"] if "target" in fx else count - 1
    session = SessionSpec(ids.namespace, ids.bar_session_id, EPOCH_NS, EPOCH_NS + count * BAR_NS, "UTC")
    grid = BarGrid(ids.instrument_id, ids.calendar_id, ids.grid_id, ids.revision, session, BAR_NS, count, target)
    market = session.close_ns
    knowledge = market + fx["K"] * SECOND_NS
    availability = _availability(market, knowledge)
    notional_column = fx["notional_column"]
    rows: list[list[Any]] = []
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
            ohlc, volume, notional = list(payload[:4]), payload[4], payload[5] if len(payload) > 5 else None
        instrument = ids.bind(wire["inst"]) if "inst" in wire else ids.instrument_id
        session_id = ids.bind(wire["ss"]) if "ss" in wire else ids.bar_session_id
        rows.append([instrument, session_id, wire.get("start", start), wire.get("end", end), *ohlc, volume,
                     notional, _known(token, knowledge, fx["K"])])
        intervals.append(IntervalCoverage(name, start, end, Coverage(1, 1, True)))
    names = ["instrument_id", "session_id", "start_ns", "end_ns", "open", "high", "low", "close", "volume"]
    if notional_column:
        names.append("actual_notional")
    names.append("known_at_ns")
    columns = []
    for position, column in enumerate(names):
        if column == "known_at_ns":
            values = [row[-1] for row in rows]
        elif column == "actual_notional":
            values = [row[9] for row in rows]
        else:
            values = [row[position] for row in rows]
        columns.append(Column(column, tuple(values)))
    scope = InputScope(session.open_ns, session.close_ns, SCOPE_POLICY)
    metadata = BatchMetadata(ids.namespace, _source(input_id), _aggregate(count, len(rows)),
                             _unit(ctx["batch"]["unit"]), _adjustment(ctx["batch"]["adjustment"]), "none", "shares",
                             "declared", "reject", scope, tuple(intervals))
    batch = CanonicalBatch(DataKind.BAR, tuple(columns), metadata)
    return _checked(batch, availability), grid, availability


def _bar_batch(names: Sequence[str], rows: Sequence[tuple[Any, ...]], intervals: Sequence[IntervalCoverage],
               count: int, scope: InputScope, namespace: str, input_id: str, unit: PriceUnit | None,
               adjustment: AdjustmentSpec) -> CanonicalBatch:
    columns = tuple(Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    metadata = BatchMetadata(namespace, _source(input_id), _aggregate(count, len(rows)), unit, adjustment, "none",
                             "shares", "declared", "reject", scope, tuple(intervals))
    return CanonicalBatch(DataKind.BAR, columns, metadata)


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


def _leg_rows(facts: Sequence[Mapping[str, Any]], ids: ProjectionIds, *,
              default_profile: str | None) -> list[dict[str, Any]]:
    """Leg witnesses as REFERENCE rows; a start without `pf` takes `default_profile` (window_start for rate legs)."""
    rows = []
    for fact in facts:
        instrument = ids.bind(fact["inst"])
        session = ids.bind(fact["ss"])
        slot = fact.get("slot", "A")
        known = _known(fact.get("ka"), 0, None)
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
    knowledge = fx["K"]
    legs = _leg_rows(facts, ids, default_profile=None)
    unit = _unit(ctx["batch"]["unit"])
    adjustment = _adjustment(ctx["batch"]["adjustment"])
    legs_batch = _checked(_reference_batch(legs, namespace=ids.namespace, input_id=legs_input_id, unit=unit,
                                           adjustment=adjustment), None) if legs else None
    members = []
    for member in fx["membership"]:
        instrument = ids.bind(member["inst"])
        bound = ids.bind(member["bound"])
        members.append(_fact_row("ef4.sector.membership", instrument, session_id,
                                 _reference_id(f"{instrument}#membership"), member["eff"], None,
                                 _known(member.get("ka"), knowledge, None), None, bound))
    membership_batch = _checked(_reference_batch(_sorted_rows(members), namespace=ids.namespace,
                                                 input_id=membership_input_id, unit=None,
                                                 adjustment=adjustment), None) if members else None
    times = [f["t"] for f in facts] + [fx["C"]]
    session = SessionSpec(ids.namespace, session_id, min(times) - 1, max(times) + 1, "UTC")
    availability = _availability(fx["C"], fx["K"])
    return {"legs": legs_batch, "membership": membership_batch, "session": session, "availability": availability,
            "entity": EntityKey(target, session_id)}


def rate_projection_inputs(fx: Mapping[str, Any], ctx: Mapping[str, Any], ids: ProjectionIds, *,
                           tape_input_id: str = "tape", legs_input_id: str = "legs") -> dict[str, Any]:
    """Tape-window aggregates (role `tape`) and window_start legs (role `legs`) for the target instrument."""
    target = ids.bind(fx["instrument"])
    facts = fx["legs"]
    end = next((f for f in facts if f["kind"] == "end"), None)
    session_id = ids.bind(end["ss"]) if end is not None else ids.target_session_id
    knowledge = fx["K"]
    unit = _unit(ctx["batch"]["unit"])
    adjustment = _adjustment(ctx["batch"]["adjustment"])
    tape_rows = []
    for fact in fx["tape"]:
        kind = fact["kind"]
        text = fact["v"] if isinstance(fact["v"], str) else str(fact["v"])
        tape_rows.append(_fact_row(f"ef4.tape.{kind}", target, session_id, _reference_id(f"window#{kind}"), fact["s"],
                                   fact["e"], _known(fact.get("ka"), knowledge, None), None, text))
    has_notional = any(f["kind"] == "notional" for f in fx["tape"])
    tape_batch = _checked(_reference_batch(_sorted_rows(tape_rows), namespace=ids.namespace, input_id=tape_input_id,
                                           unit=unit if has_notional else None, adjustment=adjustment),
                          None) if tape_rows else None
    legs = _leg_rows(facts, ids, default_profile="window_start")
    legs_batch = _checked(_reference_batch(legs, namespace=ids.namespace, input_id=legs_input_id, unit=unit,
                                           adjustment=adjustment), None) if legs else None
    times = [f["s"] for f in fx["tape"]] + [f["e"] for f in fx["tape"]] + [f["t"] for f in facts] + [fx["C"]]
    session = SessionSpec(ids.namespace, session_id, min(times) - 1, max(times) + 1, "UTC")
    availability = _availability(fx["C"], fx["K"])
    return {"tape": tape_batch, "legs": legs_batch, "session": session, "availability": availability,
            "entity": EntityKey(target, session_id)}


# ------------------------------------------------------------------------------------------ producers
def _library(stage_error: Exception) -> ProjectionStageError:
    return ProjectionStageError("library", stage_error)


_KNOWN_PARAMETERS = {
    "session_projection": frozenset({"policy_version", "window", "evidence_limit"}),
    "bar_projection": frozenset({"policy_version", "evidence_limit"}),
    "relative_excess": frozenset({"policy_version", "alignment_tolerance_ns", "max_endpoint_age_ns", "evidence_limit",
                                  "primary_benchmark_id", "secondary_benchmark_id", "sector_benchmark_id", "window_ns",
                                  "core_benchmark_ids", "core_profile"}),
    "rate_projection": frozenset({"policy_version", "window_ns", "max_endpoint_age_ns", "evidence_limit",
                                  "alignment_tolerance_ns", "adjacency"}),
}


def _with_supplied_extras(config: ConfigSpec, producer: str, parameters: Mapping[str, Any]) -> ConfigSpec:
    """Supplied parameters the producer does not define are appended unchanged, so the library's closed envelope
    decoder (not this layer) refuses them."""
    extra = tuple(Parameter(name, value if not isinstance(value, (list, tuple)) else encode_core_ids(value))
                  for name, value in parameters.items() if name not in _KNOWN_PARAMETERS[producer])
    return replace(config, parameters=config.parameters + extra) if extra else config


def compute_projection(producer: str, fx: Mapping[str, Any], ctx: Mapping[str, Any],
                       ids: ProjectionIds) -> FeatureResult:
    """Supplied inputs (I/O tier), core configuration (core builders) and core computation (library tier).

    `ctx` carries config_unit, batch unit and adjustment, config_adjustment, capability and features exactly as the
    harness default context does. The delivery capability and feature checks are the library's
    (`require_ef4_path_projections_capability`), not this layer's."""
    features = tuple(ctx["features"])
    p = fx["params"]
    config_unit = _unit(ctx["config_unit"])
    try:
        config_adjustment = _adjustment(ctx["config_adjustment"])
        if producer == "session_projection":
            batch, grid, availability = session_projection_inputs(fx, ctx, ids)
            batches = (batch,)
        elif producer == "bar_projection":
            batch, grid, availability = bar_projection_inputs(fx, ctx, ids)
            batches = (batch,)
        elif producer == "relative_excess":
            inputs = relative_excess_inputs(fx, ctx, ids)
            batches = (inputs["legs"], inputs["membership"])
        elif producer == "rate_projection":
            inputs = rate_projection_inputs(fx, ctx, ids)
            batches = (inputs["tape"], inputs["legs"])
        else:
            raise ContractError(ErrorCode.INVALID_CONFIG, "unknown producer")
    except ContractError as error:
        raise ProjectionStageError("io", error) from error
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ProjectionStageError("io", ContractError(ErrorCode.INVALID_SCHEMA, f"unreadable supplied input: {error}")) \
            from error
    try:
        for feature in features:
            require_ef4_path_projections_capability(feature, ctx["capability"])
        if producer == "session_projection":
            config = build_session_projection_config(
                grid, policy_version=p.get("policy_version"), window=p.get("window"), availability=availability,
                adjustment=config_adjustment, price_unit=config_unit, evidence_limit=p.get("evidence_limit"))
            config = _with_supplied_extras(config, producer, p)
            return compute_session_projection(batches, grid, config, features=features)
        if producer == "bar_projection":
            config = build_bar_projection_config(
                grid, policy_version=p.get("policy_version"), availability=availability,
                adjustment=config_adjustment, price_unit=config_unit, evidence_limit=p.get("evidence_limit"))
            config = _with_supplied_extras(config, producer, p)
            return compute_bar_projection(batches, grid, config, features=features)
        if producer == "relative_excess":
            core = p.get("core_benchmark_ids")
            config = build_relative_excess_config(
                policy_version=p.get("policy_version"),
                primary_benchmark_id=ids.bind(p["primary_benchmark_id"]) if "primary_benchmark_id" in p else None,
                secondary_benchmark_id=ids.bind(p["secondary_benchmark_id"]) if "secondary_benchmark_id" in p else None,
                sector_benchmark_id=ids.bind(p["sector_benchmark_id"]) if "sector_benchmark_id" in p else None,
                alignment_tolerance_ns=p.get("alignment_tolerance_ns"), max_endpoint_age_ns=p.get("max_endpoint_age_ns"),
                window_ns=p.get("window_ns"),
                core_benchmark_ids=tuple(ids.bind(x) for x in core) if isinstance(core, (list, tuple)) else core,
                core_profile=p.get("core_profile"), session=inputs["session"], availability=inputs["availability"],
                adjustment=config_adjustment, price_unit=config_unit, evidence_limit=p.get("evidence_limit"))
            config = _with_supplied_extras(config, producer, p)
            return compute_relative_excess(batches, config, entity=inputs["entity"], features=features)
        config = build_rate_projection_config(
            policy_version=p.get("policy_version"), window_ns=p.get("window_ns"),
            max_endpoint_age_ns=p.get("max_endpoint_age_ns"), alignment_tolerance_ns=p.get("alignment_tolerance_ns"),
            adjacency=p.get("adjacency"), session=inputs["session"], availability=inputs["availability"],
            adjustment=config_adjustment, price_unit=config_unit, evidence_limit=p.get("evidence_limit"))
        config = _with_supplied_extras(config, producer, p)
        return compute_rate_projection(batches, config, entity=inputs["entity"], features=features)
    except ContractError as error:
        raise _library(error) from error


def publish_results(results: Sequence[FeatureResult], output_path: Any, *, destination_scope: str,
                    generation_id: str, job_id: str, partition_id: str) -> Any:
    """Publish one complete result per generation to a local DuckDB sink (existing core SDK path) and return the
    receipt. The caller reads it back with `DuckDBSink.read(receipt)`; this function does no computation."""
    from equity_feature_duckdb_sink import DuckDBSink
    from equity_feature_io_contracts import SinkRequirements
    from equity_feature_io_sdk import prepare_publication, publish

    limits = SinkRequirements(max_results=len(results), max_chunk_bytes=1048576, max_total_bytes=10485760,
                              max_result_cells=100000, max_evidence_rows=100000)
    envelope = prepare_publication(tuple(results), destination_scope=destination_scope, generation_id=generation_id,
                                   job_id=job_id, partition_id=partition_id, limits=limits)
    with DuckDBSink(Path(output_path), destination_scope, limits=limits) as sink:
        return publish(sink, envelope, tuple(results))


__all__ = ["ProjectionIds", "ProjectionStageError", "bar_projection_inputs", "compute_projection",
           "publish_results", "rate_projection_inputs", "relative_excess_inputs", "session_projection_inputs",
           "DELIVERY_MODE", "MAPPING_VERSION"]
