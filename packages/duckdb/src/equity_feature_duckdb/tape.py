"""Lossless supplied EF4 tape trades, tick seed and notional top-K partitions as canonical batches and configurations.

Maps SUPPLIED TRADE rows and the optional `ef4.tick.seed` REFERENCE fact into canonical batches on a caller-named governed
session, and builds the two producer configurations with the closed envelopes of the core library (core
`docs/ef4/TAPE_CONTRACT_PROPOSAL.md`, identities `ef4.tape_window_sign` / `ef4-tape1` and `ef4.trade_top_k_notional` /
`ef4-notional1`). Nothing is derived, sorted, deduplicated, defaulted, filled, rescaled or inferred: rows keep the supplied
order, a column that is not delivered stays absent, and no tick sign, window total, notional or rank is computed here. The
supplied batch metadata (scale, action basis, kind, coverage, scope) is carried as given, so the shared validators and the
library refuse a mismatch. The library (`equity_features.ef4`) performs every admission, readiness decision and refusal.

Every builder takes the instrument, session, eligibility policy and seed-set identity explicitly. The only constants are the
fixed namespace, source, snapshot and mapping labels, the knowledge-reconstruction label and the trade column names. No
instrument, entity, session or grid identifier is a constant of this module.

Top-K cells are notional-ordered. The shared size-ranked constructor refuses them (INVALID_ORDER), so this module never
rebuilds a cell; the sink and codec store and read the cell fields (see the io-sdk codec).
"""
from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, Coverage, DataKind,
    EntityKey, ErrorCode, InputScope, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec, validate_batch,
)

NAMESPACE = "SYN"
CURRENCY = "USD"
SOURCE_ID = "SYN-SRC"
SNAPSHOT_ID = "snap-1"
MAPPING_VERSION = "ef4-map1"
RECONSTRUCTION_REASON = "ef4-supplied-reconstruction"  # identity label required by a reconstruction availability

WINDOW_IDENTITY, WINDOW_ALGORITHM = "ef4.tape_window_sign", "ef4-tape-window-v1"
TOP_K_IDENTITY, TOP_K_ALGORITHM = "ef4.trade_top_k_notional", "ef4-top-k-notional-v1"
SEED_KIND = "ef4.tick.seed"

# Canonical TRADE columns (contract order). Identity and event columns are always delivered.
TRADE_IDENTITY = ("instrument_id", "session_id", "event_ns", "order_key", "event_id", "eligible")
TRADE_PAYLOAD = ("price", "size", "condition", "known_at_ns")
SEED_COLUMNS = ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns", "effective_end_ns",
                "text", "price", "factor_num", "factor_den", "known_at_ns")


@dataclass(frozen=True)
class TradeSupply:
    """The supplied TRADE batch: rows in the supplied order plus the supplied metadata the shared validators check."""

    rows: tuple[Mapping[str, Any], ...]
    delivered: tuple[str, ...] = ()  # payload columns the supplier delivers (subset of TRADE_PAYLOAD)
    coverage: Coverage | None = None  # default: the delivered rows, complete
    scale: int | None = None  # price scale of the batch; default: the request price scale
    adjustment: str = "raw"  # supplied action basis label
    kind: DataKind = DataKind.TRADE
    scope_policy: str | None = None  # eligibility policy of the scope; default: the request policy
    scope_start_ns: int | None = None  # default: the session open
    scope_end_ns: int | None = None  # default: the market cutoff
    scope_include_opening_auction: bool = False
    scope_include_closing_auction: bool = False
    input_id: str = "trades"  # the source input label; partitions of one merge carry distinct labels


@dataclass(frozen=True)
class SeedSupply:
    """The supplied `ef4.tick.seed` REFERENCE facts for one seed slot, with the caller's seed-set identity."""

    facts: tuple[Mapping[str, Any], ...]
    seed_set_id: str
    scale: int | None = None  # price scale of the seed; default: the request price scale
    adjustment: str = "raw"


@dataclass(frozen=True)
class TapeCase:
    """One supplied request: the fixed nullable slots, the timing and the selection-free settings of one producer."""

    producer: str  # "window" or "topk"
    slots: tuple[CanonicalBatch | None, ...]
    session: SessionSpec
    availability: AvailabilitySpec
    unit: PriceUnit
    entity: EntityKey
    settings: Mapping[str, Any] = field(default_factory=dict)

    def config(self) -> ConfigSpec:
        """The envelope of this request (no selection-dependent parameter exists for either producer)."""
        s = self.settings
        params: tuple[Parameter, ...]
        if self.producer == "window":
            params = (Parameter("policy_version", s["policy_version"]), Parameter("window_ns", s["window_ns"]),
                      Parameter("seed_policy", s["seed_policy"]), Parameter("evidence_limit", s["evidence_limit"]),
                      Parameter("eligibility_policy", s["eligibility_policy"]))
            return _envelope(WINDOW_IDENTITY, WINDOW_ALGORITHM, params + _extra(s), self)
        if self.producer == "topk":
            params = (Parameter("policy_version", s["policy_version"]), Parameter("top_k", s["top_k"]),
                      Parameter("evidence_limit", s["evidence_limit"]), Parameter("eligibility_policy", s["eligibility_policy"]))
            return _envelope(TOP_K_IDENTITY, TOP_K_ALGORITHM, params + _extra(s), self)
        raise ContractError(ErrorCode.INVALID_CONFIG, "unknown producer")


def seed_reference(seed_set_id: str) -> str:
    """The closed `x1:B(seed_set_id)` grammar: `x1:` and the unpadded URL-safe base64 of the caller's seed-set id."""
    if type(seed_set_id) is not str or not seed_set_id:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "a caller seed-set identity is required for a supplied seed")
    return "x1:" + base64.urlsafe_b64encode(seed_set_id.encode("utf-8")).rstrip(b"=").decode("ascii")


def session_spec(session_id: str, open_ns: int, close_ns: int, *, include_opening_auction: bool = False,
                 include_closing_auction: bool = False) -> SessionSpec:
    return SessionSpec(NAMESPACE, session_id, open_ns, close_ns, "UTC", include_opening_auction=include_opening_auction,
                       include_closing_auction=include_closing_auction)


def availability(market_cutoff_ns: int, knowledge_cutoff_ns: int, mode: str = "known_at") -> AvailabilitySpec:
    """Causal `known_at` timing (evaluation at the later cutoff), or `reconstruction` timing with its identity label."""
    evaluation = max(knowledge_cutoff_ns, market_cutoff_ns)
    if mode == "reconstruction":
        return AvailabilitySpec(market_cutoff_ns, knowledge_cutoff_ns, evaluation, "reconstruction", RECONSTRUCTION_REASON)
    return AvailabilitySpec(market_cutoff_ns, knowledge_cutoff_ns, evaluation, "known_at")


def trade_batch(supply: TradeSupply, *, open_ns: int, cutoff_ns: int, price_scale: int,
                eligibility_policy: str) -> CanonicalBatch:
    """One TRADE role batch in the supplied order, carrying the supplied scale, basis, coverage and scope.

    Identity and event fields must be present on every row. A delivered payload field missing from a row is a null cell;
    an undelivered payload column is omitted from the batch (the library reports it as absent_input)."""
    for name in supply.delivered:
        if name not in TRADE_PAYLOAD:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "unknown trade payload column")
    rows = supply.rows
    columns = [Column(name, tuple(_required(row, name) for row in rows)) for name in TRADE_IDENTITY]
    columns += [Column(name, tuple(row.get(name) for row in rows)) for name in TRADE_PAYLOAD if name in supply.delivered]
    coverage = supply.coverage if supply.coverage is not None else Coverage(len(rows), len(rows), True)
    scope = InputScope(open_ns if supply.scope_start_ns is None else supply.scope_start_ns,
                       cutoff_ns if supply.scope_end_ns is None else supply.scope_end_ns,
                       eligibility_policy if supply.scope_policy is None else supply.scope_policy,
                       supply.scope_include_opening_auction, supply.scope_include_closing_auction)
    unit = PriceUnit(price_scale if supply.scale is None else supply.scale, CURRENCY)
    metadata = BatchMetadata(NAMESPACE, SourceBinding(SOURCE_ID, SNAPSHOT_ID, MAPPING_VERSION, supply.input_id), coverage,
                             unit, AdjustmentSpec(supply.adjustment), "none", "shares", "declared", "reject", scope, ())
    batch = CanonicalBatch(supply.kind, tuple(columns), metadata)
    validate_batch(batch, required_fields=())
    return batch


def seed_batch(supply: SeedSupply, *, open_ns: int, price_scale: int, input_id: str = "seed") -> CanonicalBatch:
    """The REFERENCE seed role: the supplied `ef4.tick.seed` facts in the supplied order, under the caller's seed-set id."""
    reference = seed_reference(supply.seed_set_id)
    rows = [dict(fact, reference_id=reference) for fact in supply.facts]
    columns = [Column(name, tuple(row.get(name) for row in rows)) for name in SEED_COLUMNS]
    count = len(rows)
    unit = PriceUnit(price_scale if supply.scale is None else supply.scale, CURRENCY)
    metadata = BatchMetadata(NAMESPACE, SourceBinding(SOURCE_ID, SNAPSHOT_ID, MAPPING_VERSION, input_id),
                             Coverage(count, count, True), unit, AdjustmentSpec(supply.adjustment), "none", "shares",
                             "declared", "reject", InputScope(open_ns - 1, open_ns, "ef4-seed"), ())
    batch = CanonicalBatch(DataKind.REFERENCE, tuple(columns), metadata)
    validate_batch(batch, required_fields=())
    return batch


def window_case(*, instrument_id: str, session_id: str, open_ns: int, cutoff_ns: int, knowledge_ns: int,
                session_close_ns: int, price_scale: int, eligibility_policy: str, window_ns: int, seed_policy: str,
                evidence_limit: int, policy_version: str, trades: TradeSupply | None, seed: SeedSupply | None = None,
                extra_parameters: Mapping[str, Any] | None = None, mode: str = "known_at",
                include_opening_auction: bool = False, include_closing_auction: bool = False) -> TapeCase:
    """The `ef4.tape_window_sign` request: nullable `(trades, seed)` slots; the seed slot is filled exactly when supplied."""
    session = session_spec(session_id, open_ns, session_close_ns, include_opening_auction=include_opening_auction,
                           include_closing_auction=include_closing_auction)
    slots = (
        None if trades is None else trade_batch(trades, open_ns=open_ns, cutoff_ns=cutoff_ns, price_scale=price_scale,
                                                eligibility_policy=eligibility_policy),
        None if seed is None else seed_batch(seed, open_ns=open_ns, price_scale=price_scale),
    )
    settings = {"window_ns": window_ns, "seed_policy": seed_policy, "evidence_limit": evidence_limit,
                "eligibility_policy": eligibility_policy, "policy_version": policy_version,
                "extra": dict(extra_parameters or {})}
    return TapeCase("window", slots, session, availability(cutoff_ns, knowledge_ns, mode),
                    PriceUnit(price_scale, CURRENCY), EntityKey(instrument_id, session_id), settings)


def top_k_case(*, instrument_id: str, session_id: str, open_ns: int, cutoff_ns: int, knowledge_ns: int,
               session_close_ns: int, price_scale: int, eligibility_policy: str, top_k: int, evidence_limit: int,
               policy_version: str, trades: TradeSupply | None, extra_parameters: Mapping[str, Any] | None = None,
               mode: str = "known_at", include_opening_auction: bool = False,
               include_closing_auction: bool = False) -> TapeCase:
    """The `ef4.trade_top_k_notional` request: one nullable `(trades,)` slot; each partition is its own request."""
    session = session_spec(session_id, open_ns, session_close_ns, include_opening_auction=include_opening_auction,
                           include_closing_auction=include_closing_auction)
    slots = (None if trades is None else trade_batch(trades, open_ns=open_ns, cutoff_ns=cutoff_ns,
                                                     price_scale=price_scale, eligibility_policy=eligibility_policy),)
    settings = {"top_k": top_k, "evidence_limit": evidence_limit, "eligibility_policy": eligibility_policy,
                "policy_version": policy_version, "extra": dict(extra_parameters or {})}
    return TapeCase("topk", slots, session, availability(cutoff_ns, knowledge_ns, mode),
                    PriceUnit(price_scale, CURRENCY), EntityKey(instrument_id, session_id), settings)


def _required(row: Mapping[str, Any], name: str) -> Any:
    if name not in row:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "identity or event field missing from a supplied trade row")
    return row[name]


def _extra(settings: Mapping[str, Any]) -> tuple[Parameter, ...]:
    return tuple(Parameter(name, value) for name, value in sorted(settings["extra"].items()))


def _envelope(identity: str, algorithm: str, params: tuple[Parameter, ...], case: TapeCase) -> ConfigSpec:
    """The library `make_config` envelope (target session, one shared adjustment, the explicit PriceUnit)."""
    session = case.session
    return ConfigSpec(identity, algorithm, params, session,
                      WindowSpec(1, session.session_id, (session.session_id,), "prior_only"),
                      case.availability, AdjustmentSpec(), case.unit)


__all__ = [
    "CURRENCY", "MAPPING_VERSION", "NAMESPACE", "RECONSTRUCTION_REASON", "SEED_KIND", "SNAPSHOT_ID", "SOURCE_ID",
    "SeedSupply", "TOP_K_ALGORITHM", "TOP_K_IDENTITY", "TRADE_IDENTITY", "TRADE_PAYLOAD", "TapeCase",
    "TradeSupply", "WINDOW_ALGORITHM", "WINDOW_IDENTITY", "availability", "seed_batch", "seed_reference",
    "session_spec", "top_k_case", "trade_batch", "window_case",
]
