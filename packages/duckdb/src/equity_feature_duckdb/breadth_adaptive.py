"""Lossless supplied EF3 declared breadth, observed breadth and adaptive-volume inputs.

Maps SUPPLIED member, roster and observation facts into canonical REFERENCE batches on a local governed session, and
builds the three producer configurations with the closed envelopes of the core library (core
`docs/ef3/BREADTH_ADAPTIVE_CONTRACT_PROPOSAL.md`, policies `ef3-breadth1`, `ef3-obsbreadth1`, `ef3-adaptive1`). Nothing is
derived, filled, imputed, sorted by value, rescaled or inferred; no count, ratio, proximity, rank or rate mathematics lives
here. The library (`equity_features.ef3`) still performs every admission, decision and refusal.

Every builder takes its instrument, member, role and kind explicitly. The namespace, population id, record-set id and
the single governed session come from an explicit `Frame` (default: the documented demo frame DEMO_FRAME). No `known_at`
is ever defaulted: a fact without `ka` carries a null `known_at_ns` and the library reports `unknown_availability`; a
`ka` that is not a non-negative integer is a typed INVALID_SCHEMA refusal. Configurations depend on the selected outputs exactly as the library
does: a tolerance is present only when its fraction output is selected.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage, DataKind,
    EntityKey, ErrorCode, InputScope, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec,
    validate_batch,
)
from ._typed import checked_known_at, guard_public

NAMESPACE = "SYN"  # demo default
CURRENCY = "USD"
SOURCE_ID = "SYN-SRC"
SNAPSHOT_ID = "snap-1"
MAPPING_VERSION = "ef3-map1"
SESSION_ID = "0"  # demo default
SESSION_OPEN_NS = 0  # demo default
SESSION_CLOSE_NS = 10**12  # demo default: one governed session wide enough for every fixture time
POPULATION_ID = "SYN-POP"  # demo default
POPULATION_REVISION = "rev-1"
RECORD_SET_ID = "SYN-ROSTER"  # demo default
EPOCH_DEFAULT = "e1"
EVENT_DEFAULT = 50  # member and roster rows without an explicit event time (fixture default t)

BREADTH_IDENTITY, BREADTH_ALGORITHM, BREADTH_POLICY = "ef3.session_breadth", "ef3-session-breadth-v1", "ef3-breadth1"
OBSERVED_IDENTITY, OBSERVED_ALGORITHM, OBSERVED_POLICY = "ef3.observed_breadth", "ef3-observed-breadth-v1", "ef3-obsbreadth1"
ADAPTIVE_IDENTITY, ADAPTIVE_ALGORITHM, ADAPTIVE_POLICY = "ef3.adaptive_volume", "ef3-adaptive-volume-v1", "ef3-adaptive1"

# Library role slots, in slot order.
BREADTH_ROLES = ("population", "prior_reference_availability", "current_return", "cumulative_volume", "endpoint_price",
                 "vwap", "momentum", "selected_high", "selected_low")
OBSERVED_ROLES = ("members", "change", "qualifier_price", "qualifier_volume")
ADAPTIVE_ROLES = ("observations",)

# Fact kinds (contract reference_fact_schemas).
POPULATION_KIND = "ef3.population.member"
INTERVAL_KIND = "ef3.breadth.membership_interval"
PRA_AVAILABLE, PRA_UNAVAILABLE = "ef3.member.prior_reference.available", "ef3.member.prior_reference.unavailable"
CURRENT_RETURN_KIND = "ef3.member.current_return"
CUMULATIVE_VOLUME_KIND = "ef3.member.cumulative_volume"
ENDPOINT_PRICE_KIND = "ef3.member.endpoint_price"
VWAP_KIND, VWAP_UNAVAILABLE = "ef3.member.vwap", "ef3.member.vwap.unavailable"
MOMENTUM_KIND = "ef3.member.momentum"
SELECTED_HIGH_KIND, SELECTED_LOW_KIND = "ef3.member.selected_high", "ef3.member.selected_low"
OBSERVED_MEMBER_KIND = "ef3.observed.member"
OBSERVED_CHANGE_KIND = "ef3.observed.change"
QUALIFIER_PRICE_KIND = "ef3.observed.qualifier_price"
QUALIFIER_VOLUME_KIND = "ef3.observed.qualifier_volume"
RATE_KIND = "ef3.adaptive.rate"

# Declared fixture roles (short names of the contract notation) to library slots.
DECLARED_SLOTS = {"population": "population", "pra": "prior_reference_availability", "ret": "current_return",
                  "vol": "cumulative_volume", "ep": "endpoint_price", "vwap": "vwap", "mom": "momentum",
                  "hi": "selected_high", "lo": "selected_low"}
# Fact kind and price rule of each declared member role (the population role is handled separately).
DECLARED_FACT = {
    "pra": ("prior_reference", None), "ret": (CURRENT_RETURN_KIND, "v"), "vol": (CUMULATIVE_VOLUME_KIND, "v"),
    "ep": (ENDPOINT_PRICE_KIND, "v"), "vwap": ("vwap", None), "mom": (MOMENTUM_KIND, "v"),
    "hi": (SELECTED_HIGH_KIND, "v"), "lo": (SELECTED_LOW_KIND, "v"),
}

@dataclass(frozen=True)
class Fact:
    """One supplied fact row. `instrument_id` is the member, roster member, or the target entity of the adaptive stream."""

    instrument_id: str
    reference_id: str
    fact_kind: str
    start_ns: int
    end_ns: int | None
    known_at_ns: int | None
    text: str | None = None
    price: int | None = None
    factor_num: int | None = None
    factor_den: int | None = None


@dataclass(frozen=True)
class Frame:
    """Identity of the governed frame of a request: namespace, population and record-set ids and the single session."""

    namespace: str = NAMESPACE
    population_id: str = POPULATION_ID
    record_set_id: str = RECORD_SET_ID
    session_id: str = SESSION_ID
    session_open_ns: int = SESSION_OPEN_NS
    session_close_ns: int = SESSION_CLOSE_NS


DEMO_FRAME = Frame()


@dataclass(frozen=True)
class Case:
    """One supplied request: the role slots (None for an undelivered slot), the timing and the selection-free settings."""

    producer: str
    slots: tuple[CanonicalBatch | None, ...]
    session: SessionSpec
    availability: AvailabilitySpec
    unit: PriceUnit
    entity: EntityKey
    settings: Mapping[str, Any]
    frame: Frame = DEMO_FRAME

    def config(self, features: Sequence[str]) -> ConfigSpec:
        """The envelope of this request for one selection of outputs (the library rule for the optional parameters)."""
        if self.producer == "session_breadth":
            return _breadth_config(self, features)
        if self.producer == "observed_breadth":
            return _observed_config(self)
        if self.producer == "adaptive_volume":
            return _adaptive_config(self)
        raise ContractError(ErrorCode.INVALID_CONFIG, "unknown producer")


def price_unit(scale: int) -> PriceUnit:
    return PriceUnit(scale, CURRENCY)


def session_spec(frame: Frame = DEMO_FRAME) -> SessionSpec:
    return SessionSpec(frame.namespace, frame.session_id, frame.session_open_ns, frame.session_close_ns, "UTC")


def availability(market_cutoff_ns: int, knowledge_cutoff_ns: int) -> AvailabilitySpec:
    """Causal known_at timing: market cutoff and knowledge cutoff with evaluation at the later of the two."""
    return AvailabilitySpec(market_cutoff_ns, knowledge_cutoff_ns, max(knowledge_cutoff_ns, market_cutoff_ns), "known_at")


def reference(prefix: str, shape: tuple[str, ...], values: tuple[str | int, ...]) -> str:
    """Reference identity `prefix:part...`: `t` is the unpadded URL-safe base64 of the text, `dN` an N-digit decimal."""
    parts = [prefix]
    for kind, value in zip(shape, values, strict=True):
        if kind == "t":
            parts.append(base64.urlsafe_b64encode(str(value).encode("utf-8")).rstrip(b"=").decode("ascii"))
        else:
            parts.append(str(value).zfill(int(kind[1:])))
    return ":".join(parts)


def reference_batch(facts: Sequence[Fact], *, input_id: str, complete: bool, unit: PriceUnit,
                    frame: Frame = DEMO_FRAME) -> CanonicalBatch:
    """One REFERENCE role batch: rows ordered by (effective_start_ns, reference_id), one snapshot, one PriceUnit.

    `complete` is the declared coverage of the role. A complete role declares its row count as expected; an incomplete
    role declares no expected count, so the library treats its missing members as governed gaps."""
    ordered = sorted(facts, key=lambda f: (f.start_ns, f.reference_id))
    columns = (
        Column("instrument_id", tuple(f.instrument_id for f in ordered)),
        Column("session_id", tuple(frame.session_id for _ in ordered)),
        Column("reference_id", tuple(f.reference_id for f in ordered)),
        Column("fact_kind", tuple(f.fact_kind for f in ordered)),
        Column("effective_start_ns", tuple(f.start_ns for f in ordered)),
        Column("effective_end_ns", tuple(f.end_ns for f in ordered)),
        Column("text", tuple(f.text for f in ordered)),
        Column("price", tuple(f.price for f in ordered)),
        Column("factor_num", tuple(f.factor_num for f in ordered)),
        Column("factor_den", tuple(f.factor_den for f in ordered)),
        Column("known_at_ns", tuple(checked_known_at(f.known_at_ns) for f in ordered)),
    )
    count = len(ordered)
    coverage = Coverage(count, count, True) if complete else Coverage(None, count, False)
    metadata = BatchMetadata(frame.namespace, SourceBinding(SOURCE_ID, SNAPSHOT_ID, MAPPING_VERSION, input_id), coverage, unit,
                             AdjustmentSpec(), "none", "shares", "declared", "reject",
                             InputScope(frame.session_open_ns, frame.session_close_ns, "ef3-supplied"), ())
    batch = CanonicalBatch(DataKind.REFERENCE, columns, metadata)
    validate_batch(batch, required_fields=())
    return batch


def _role_rows(role: Mapping[str, Any]) -> Sequence[tuple[str, Mapping[str, Any]]]:
    """Rows of a fixture role as (member, row) pairs; a list (population) carries its member in `m`."""
    rows = role["rows"]
    if isinstance(rows, Mapping):
        return list(rows.items())
    return [(row["m"], row) for row in rows]


def _population_facts(rows: Sequence[Mapping[str, Any]], profile: str, frame: Frame) -> list[Fact]:
    facts: list[Fact] = []
    static = profile == "static"
    for row in rows:
        ka = row.get("ka")
        if static:
            facts.append(Fact(row["m"], reference("x1", ("t",), (frame.population_id,)), POPULATION_KIND, frame.session_open_ns,
                         frame.session_close_ns, ka, SNAPSHOT_ID))
        else:
            ref = reference("bh1", ("t", "t", "d6"), (frame.population_id, POPULATION_REVISION, row["stint"]))
            facts.append(Fact(row["m"], ref, INTERVAL_KIND, row["s"], row["end"], ka, SNAPSHOT_ID))
    return facts


def _declared_fact(name: str, member: str, row: Mapping[str, Any], frame: Frame) -> Fact:
    start = row.get("t", EVENT_DEFAULT)
    ka = row.get("ka")
    ref = reference("bf1", ("t",), (frame.population_id,))
    if name == "pra":
        kind = PRA_AVAILABLE if row["k"] == "available" else PRA_UNAVAILABLE
        return Fact(member, ref, kind, start, None, ka)
    if name == "vwap":
        if row["k"] == "rat":
            return Fact(member, ref, VWAP_KIND, start, None, ka, None, row["num"], 1, row["den"])
        return Fact(member, ref, VWAP_UNAVAILABLE, start, None, ka)
    kind, _ = DECLARED_FACT[name]
    return Fact(member, ref, kind, start, None, ka, None, row["v"])


def declared_case(inp: Mapping[str, Any], *, entity_instrument: str, frame: Frame = DEMO_FRAME) -> Case:
    """Supplied declared-universe request (fixture input of the declared group) as nine nullable REFERENCE slots."""
    scale = inp.get("scale", 2)
    profile = "static_snapshot" if inp["profile"] == "static" else "ordered_history"
    slots: list[CanonicalBatch | None] = []
    for slot in BREADTH_ROLES:
        short = next(k for k, v in DECLARED_SLOTS.items() if v == slot)
        role = inp["roles"][short]
        if role is None:
            slots.append(None)
            continue
        complete = role["cov"] == "complete"
        if short == "population":
            facts = _population_facts(role["rows"], inp["profile"], frame)
        else:
            facts = [_declared_fact(short, m, row, frame) for m, row in _role_rows(role)]
        slots.append(reference_batch(facts, input_id=slot, complete=complete, unit=price_unit(scale), frame=frame))
    params = inp["params"]
    settings = {
        "profile": profile, "evidence_limit": params["evidence_limit"],
        "near_high": tuple(params["near_high_tol"]) if "near_high_tol" in params else None,
        "near_low": tuple(params["near_low_tol"]) if "near_low_tol" in params else None,
    }
    return Case("session_breadth", tuple(slots), session_spec(frame), availability(inp["C"], inp["K"]), price_unit(scale),
                EntityKey(entity_instrument, frame.session_id), settings, frame)


def observed_case(inp: Mapping[str, Any], *, entity_instrument: str, frame: Frame = DEMO_FRAME) -> Case:
    """Supplied observed-population request (roster and three fact roles) as four nullable REFERENCE slots."""
    scale = inp.get("scale", 2)
    slots: list[CanonicalBatch | None] = []
    spec = {"members": (OBSERVED_MEMBER_KIND,), "change": (OBSERVED_CHANGE_KIND,),
            "qualifier_price": (QUALIFIER_PRICE_KIND,), "qualifier_volume": (QUALIFIER_VOLUME_KIND,)}
    for slot, short in zip(OBSERVED_ROLES, ("members", "chg", "qp", "qv")):
        role = inp["roles"][short]
        if role is None:
            slots.append(None)
            continue
        facts: list[Fact] = []
        for member, row in _role_rows(role):
            start = row.get("t", EVENT_DEFAULT)
            ka = row.get("ka")
            ref = reference("ob1", ("t",), (frame.record_set_id,))
            if slot == "members":
                facts.append(Fact(member, ref, spec[slot][0], start, None, ka, row.get("g")))
            else:
                facts.append(Fact(member, ref, spec[slot][0], start, None, ka, None, row["v"]))
        slots.append(reference_batch(facts, input_id=slot, complete=role["cov"] == "complete", unit=price_unit(scale),
                                     frame=frame))
    params = inp["params"]
    group = params.get("group_label")
    settings = {"scope": params["scope"], "group_label": group, "floor_price": tuple(params["floor_price"]),
                "floor_volume": params["floor_volume"], "evidence_limit": params["evidence_limit"]}
    return Case("observed_breadth", tuple(slots), session_spec(frame), availability(inp["C"], inp["K"]), price_unit(scale),
                EntityKey(entity_instrument, frame.session_id), settings, frame)


def adaptive_case(inp: Mapping[str, Any], *, entity_instrument: str, frame: Frame = DEMO_FRAME) -> Case:
    """Supplied adaptive observation stream as one nullable REFERENCE slot (the rows of one epoch)."""
    obs = inp["obs"]
    epoch = inp.get("epoch", EPOCH_DEFAULT)
    slot: CanonicalBatch | None = None
    if obs is not None:
        facts: list[Fact] = []
        for row in obs["rows"]:
            q, t = row["q"], row["t"]
            ka = row.get("ka")
            ref = reference("ao1", ("t", "d19", "t"), (epoch, q, f"ev{q}"))
            rate = row["rate"]
            if rate is None:
                price = fnum = fden = None
            else:
                price, fnum, fden = rate
            facts.append(Fact(entity_instrument, ref, RATE_KIND, t, None, ka, SNAPSHOT_ID, price, fnum, fden))
        slot = reference_batch(facts, input_id="observations", complete=obs["cov"] == "complete", unit=price_unit(0),
                               frame=frame)
    settings = {"epoch": epoch, "tau_ns": inp["tau_ns"], "warmup_count": inp["W"], "evidence_limit": inp["evidence_limit"]}
    return Case("adaptive_volume", (slot,), session_spec(frame), availability(inp["C"], inp["K"]), price_unit(0),
                EntityKey(entity_instrument, frame.session_id), settings, frame)


def _envelope(identity: str, algorithm: str, params: tuple[Parameter, ...], case: Case, count: int) -> ConfigSpec:
    """The library `make_config` envelope (target session, one shared adjustment, the explicit PriceUnit)."""
    session = case.session
    if case.availability.market_cutoff_ns < session.open_ns:
        raise ContractError(ErrorCode.BOUNDS, "market cutoff precedes the target session open")
    return ConfigSpec(identity, algorithm, params, session,
                      WindowSpec(count, session.session_id, (session.session_id,), "prior_only"),
                      case.availability, AdjustmentSpec(), case.unit)


def _breadth_config(case: Case, features: Sequence[str]) -> ConfigSpec:
    s = case.settings
    params = [Parameter("policy_version", BREADTH_POLICY), Parameter("membership_profile", s["profile"]),
              Parameter("population_id", case.frame.population_id), Parameter("population_revision", POPULATION_REVISION),
              Parameter("evidence_limit", s["evidence_limit"])]
    if "breadth.session.near_high_fraction" in features:
        params += [Parameter("near_high_tol_num", s["near_high"][0]), Parameter("near_high_tol_den", s["near_high"][1])]
    if "breadth.session.near_low_fraction" in features:
        params += [Parameter("near_low_tol_num", s["near_low"][0]), Parameter("near_low_tol_den", s["near_low"][1])]
    return _envelope(BREADTH_IDENTITY, BREADTH_ALGORITHM, tuple(params), case, 1)


def _observed_config(case: Case) -> ConfigSpec:
    s = case.settings
    params = [Parameter("policy_version", OBSERVED_POLICY), Parameter("scope", s["scope"]),
              Parameter("record_set_id", case.frame.record_set_id), Parameter("floor_price_num", s["floor_price"][0]),
              Parameter("floor_price_den", s["floor_price"][1]), Parameter("floor_volume", s["floor_volume"]),
              Parameter("evidence_limit", s["evidence_limit"])]
    if s["group_label"] is not None:
        params.append(Parameter("group_label", s["group_label"]))
    return _envelope(OBSERVED_IDENTITY, OBSERVED_ALGORITHM, tuple(params), case, 1)


def _adaptive_config(case: Case) -> ConfigSpec:
    s = case.settings
    params = (Parameter("policy_version", ADAPTIVE_POLICY), Parameter("epoch", s["epoch"]),
              Parameter("tau_ns", s["tau_ns"]), Parameter("warmup_count", s["warmup_count"]),
              Parameter("evidence_limit", s["evidence_limit"]))
    return _envelope(ADAPTIVE_IDENTITY, ADAPTIVE_ALGORITHM, params, case, 1)


__all__ = [
    "ADAPTIVE_ALGORITHM", "ADAPTIVE_IDENTITY", "ADAPTIVE_POLICY", "ADAPTIVE_ROLES", "BREADTH_ALGORITHM", "BREADTH_IDENTITY",
    "BREADTH_POLICY", "BREADTH_ROLES", "Case", "DEMO_FRAME", "Fact", "Frame", "NAMESPACE", "OBSERVED_ALGORITHM", "OBSERVED_IDENTITY",
    "OBSERVED_POLICY", "OBSERVED_ROLES", "POPULATION_ID", "POPULATION_REVISION", "RECORD_SET_ID", "SESSION_ID",
    "SNAPSHOT_ID", "adaptive_case", "availability", "declared_case", "observed_case", "price_unit", "reference",
    "reference_batch", "session_spec",
]


guard_public(globals(), __name__)
