"""Lossless supplied EF5 price-structure inputs; no candle, swing, return, velocity or trend-count mathematics.

Maps SUPPLIED OHLCV bars (or close-only bars) on the R17 governed grid into the one nullable `bars` role of the frozen
EF5 contract (configs `ef5.candle`, `ef5.structure`, `ef5.technical`; algorithms `ef5-candle-v1`, `ef5-structure-v1`,
`ef5-technical-v1`; core docs/ef5/PRICE_STRUCTURES_CONTRACT_PROPOSAL.md) and builds the closed configuration envelopes with
the same R17 context transport as the library codec. Nothing is derived, filled, bridged, sorted or inferred. Every identity
(instrument, session, start, end) comes from the caller's context, never from a constant in this module.

Defaults ledger (the brief step the contract requires): there is none. Every parameter, the adjustment label, the adjustment
policy version, the price unit, the original known_at of every bar and the per-slot coverage declaration are supplied by the
caller. The library (`equity_features_intraday`) still performs every admission, decision and refusal; this adapter refuses only
what it cannot represent (a missing or mistyped declaration) and, per ruling E2, rows delivered with coverage not declared.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, ConfigSpec, ContractError, Coverage, DataKind,
    ErrorCode, InputScope, IntervalCoverage, Parameter, PriceUnit, SourceBinding, WindowSpec, validate_batch,
)

from .path_efficiency import make_path_batch, make_slot_coverage
from .relative_rv import CONTEXT_SCHEMA, IntradayContextSpec, IntradayRunSpec

ROLES = ("bars",)
_ORIGINS = frozenset(("supplied", "duckdb_backed_observed", "unavailable"))
MAPPING_VERSION = "ef5-map1"
EPOCH_PROFILES = {"session_reset": "reset", "governed_history": "carry"}  # profile -> required R17 context mode
CHUNK_CHARS = 4096
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
CLOSE_COLUMNS = ("close",)
_COMMON = ("policy_version", "epoch_profile", "evidence_limit", "adjustment", "adjustment_policy_version")
# producer -> (config identity, algorithm version, policy label, producer parameters in contract order)
PRODUCERS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "candle": ("ef5.candle", "ef5-candle-v1", "ef5-candle1", ("doji_body_max_fraction",)),
    "structure": ("ef5.structure", "ef5-structure-v1", "ef5-structure1", ("swing_strength", "lookback")),
    "technical": ("ef5.technical", "ef5-technical-v1", "ef5-technical1", ("trend_window", "trend_count")),
}
# Output ids (lexical order) and their units, for the sink headers of the worker layer.
EF5_UNITS: dict[str, str] = {
    "candle.body_fraction": "fraction", "candle.doji": "boolean", "candle.engulfing_bearish": "boolean",
    "candle.engulfing_bullish": "boolean", "candle.inside_bar": "boolean", "candle.lower_shadow_fraction": "fraction",
    "candle.upper_shadow_fraction": "fraction",
    "structure.last_swing_high_price": "currency/share", "structure.last_swing_low_price": "currency/share",
    "structure.swing_high_confirmed": "boolean", "structure.swing_low_confirmed": "boolean",
    "technical.momentum_acceleration_fraction_per_second_squared": "fraction/s^2",
    "technical.price_velocity_fraction_per_second": "fraction/s", "technical.session_return_fraction": "fraction",
    "technical.signed_trend_window_count": "windows",
}
EF5_FEATURES: tuple[str, ...] = tuple(sorted(EF5_UNITS))


def make_ef5_batch(column_order: tuple[str, ...], rows: tuple[tuple[Any, ...], ...], *,
                   metadata: BatchMetadata) -> CanonicalBatch:
    """Exact supplied rectangular BAR cells; generic canonical validation may refuse an invalid original row first."""
    if type(column_order) is tuple and "volume" in column_order and type(rows) is tuple:
        index = column_order.index("volume")
        if any(type(row) is tuple and len(row) > index and type(row[index]) is int and row[index] < 0 for row in rows):
            # Contract RF14: a negative volume is INVALID_SCHEMA (the generic validator would say BOUNDS).
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Negative volume")
    return make_path_batch(column_order, rows, metadata=metadata)


def make_ef5_chunks(context: IntradayContextSpec, slots: Sequence[Any], *, input_id: str, source_id: str,
                    snapshot_id: str, namespace: str, price_unit: PriceUnit, adjustment: AdjustmentSpec,
                    columns: tuple[str, ...], eligibility_policy: str, declare_coverage: bool
                    ) -> tuple[CanonicalBatch, ...]:
    """BAR chunks over the governed slots of the context: one chunk per actual session, in context order.

    A slot entry is "absent" or "forming" (no row, no coverage: the library tells a bar still forming at the market
    cutoff from an absent one), "gap" (no row, declared incomplete coverage), "empty" (no row, complete coverage of
    expected 0: a proven empty slot, never forward filled), or a mapping {"values": tuple, "known_at_ns": int | None}
    whose values align with `columns` (known_at_ns None is unknown availability, never defaulted). `declare_coverage`
    has no default: True declares complete coverage of one row for every supplied row; False delivers rows with no
    coverage declared, which is refused here (ruling E2: no default-to-complete).
    """
    if type(context) is not IntradayContextSpec or type(columns) is not tuple or type(declare_coverage) is not bool:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete context, column tuple and coverage declaration required")
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
            if slot in ("absent", "forming"):
                continue
            if slot == "gap":
                intervals.append(make_slot_coverage(index, start, end, expected=1, observed=0, complete=False))
            elif slot == "empty":
                intervals.append(make_slot_coverage(index, start, end, expected=0, observed=0, complete=True))
            elif (type(slot) is dict and set(slot) == {"values", "known_at_ns"} and type(slot["values"]) is tuple
                  and len(slot["values"]) == len(columns)):
                rows.append((context.instrument_id, session_id, start, end, *slot["values"], slot["known_at_ns"]))
                if declare_coverage:
                    intervals.append(make_slot_coverage(index, start, end, expected=1, observed=1, complete=True))
            else:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Unknown supplied slot entry")
        if rows and not declare_coverage:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Rows delivered with coverage not declared (no default-to-complete)")
        scope = InputScope(session.open_ns, session.close_ns, eligibility_policy)
        metadata = BatchMetadata(namespace,
                                 SourceBinding(source_id, snapshot_id, MAPPING_VERSION,
                                               f"{input_id}-{len(chunks):03}"),
                                 Coverage(None, len(rows), False), price_unit, adjustment, "none", "shares",
                                 "declared", "reject", scope, tuple(intervals))
        chunks.append(make_ef5_batch(names, tuple(rows), metadata=metadata))
    return tuple(chunks)


@dataclass(frozen=True)
class Ef5Inputs:
    """One nullable `bars` role holding the ordered BAR chunks of the governed grid.

    `bars=None` is missing delivery. Origins are explicit caller declarations, not capability or rights evidence.
    Nothing here orders, merges or repairs chunks.
    """
    bars: tuple[CanonicalBatch, ...] | None = None
    provenance: tuple[str, ...] = ("unavailable",)

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 1:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly one EF5 origin required")
        origin = self.provenance[0]
        if type(origin) is not str or origin not in _ORIGINS or (self.bars is None) != (origin == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
        if self.bars is not None:
            if type(self.bars) is not tuple:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete tuple of BAR chunks required")
            for batch in self.bars:
                if type(batch) is not CanonicalBatch or batch.kind is not DataKind.BAR:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "EF5 role requires BAR batches")
                validate_batch(batch, required_fields=())
            if len({b.metadata.source.input_id for b in self.bars}) != len(self.bars):
                raise ContractError(ErrorCode.DUPLICATE, "Distinct EF5 chunk input IDs required")
            if len({b.metadata.namespace for b in self.bars}) > 1:
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One EF5 namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return ROLES

    @property
    def slots(self) -> tuple[tuple[CanonicalBatch, ...] | None, ...]:
        return (self.bars,)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return () if self.bars is None else self.bars


def make_ef5_config(producer: str, context: IntradayContextSpec, *, availability: AvailabilitySpec,
                    adjustment: AdjustmentSpec, price_unit: PriceUnit | None, policy_version: Any,
                    epoch_profile: Any, evidence_limit: Any, adjustment_label: Any, adjustment_policy_version: Any,
                    **parameters: Any) -> ConfigSpec:
    """Closed envelope of one EF5 producer over the accepted R17 context (same parameters, identity and algorithm as
    the library builder for the same context). Every declaration is a required argument: no default exists, and the
    shared AdjustmentSpec defaults are never read. Pure I/O checks only: producer name, types, the epoch profile
    vocabulary and the price unit presence; the library decodes every other value (ranges, the label vocabulary and
    pairing, currency, policy label, adjustment, identities).
    """
    if producer not in PRODUCERS:
        raise ContractError(ErrorCode.UNKNOWN_FEATURE, "Unknown EF5 producer")
    identity, algorithm, _, names = PRODUCERS[producer]
    if price_unit is None:
        raise ContractError(ErrorCode.INVALID_UNIT, "Explicit price unit required")
    if type(context) is not IntradayContextSpec or type(availability) is not AvailabilitySpec \
            or type(adjustment) is not AdjustmentSpec or type(price_unit) is not PriceUnit:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Concrete context, timing, adjustment and unit required")
    if type(epoch_profile) is not str or epoch_profile not in EPOCH_PROFILES:
        raise ContractError(ErrorCode.INVALID_CONFIG, "epoch_profile must be session_reset or governed_history")
    declared = {"policy_version": policy_version, "epoch_profile": epoch_profile, "evidence_limit": evidence_limit,
                "adjustment": adjustment_label, "adjustment_policy_version": adjustment_policy_version}
    declared.update({name: parameters.pop(name, None) for name in names})
    if declared["adjustment_policy_version"] is None:
        raise ContractError(ErrorCode.UNSUPPORTED_ADJUSTMENT, "adjustment_spec.policy_version must be declared (PQ-2)")
    if any(value is None for value in declared.values()):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Every EF5 parameter and declaration is required (no defaults)")
    text = context.to_json()
    chunks = tuple(text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS))
    params: list[Parameter] = [Parameter(name, declared[name]) for name in (*_COMMON, *names)]
    params += [Parameter("context_schema", CONTEXT_SCHEMA), Parameter("context_sha256", context.digest),
               Parameter("context_chunks", len(chunks))]
    params += [Parameter(f"context_{i:03}", chunk) for i, chunk in enumerate(chunks)]
    # A surplus parameter is not representable by this adapter; the library's closed envelope refuses it.
    params = params[:len(_COMMON) + len(names)] + [Parameter(k, v) for k, v in parameters.items()] + \
        params[len(_COMMON) + len(names):]
    target = next(s for s in context.sessions if s.session_id == context.runs[-1].session_id)
    return ConfigSpec(identity, algorithm, tuple(params), target,
                      WindowSpec(len(context.sessions), target.session_id,
                                 tuple(s.session_id for s in context.sessions), "completed_eod"),
                      availability, adjustment, price_unit)


def make_ef5_context(instrument_id: str, *, calendar_id: str, grid_id: str, revision: str,
                     sessions: Sequence[Any], runs: Sequence[IntradayRunSpec], anchor_index: int,
                     target_index: int, epoch_profile: str) -> IntradayContextSpec:
    """The R17 context for one epoch profile; the mode is fixed by the profile (session_reset: reset,
    governed_history: carry). The library enforces the 64-session context cap and the mode consistency when it
    decodes the context."""
    if type(epoch_profile) is not str or epoch_profile not in EPOCH_PROFILES:
        raise ContractError(ErrorCode.INVALID_CONFIG, "epoch_profile must be session_reset or governed_history")
    return IntradayContextSpec(instrument_id, calendar_id, grid_id, revision, tuple(sessions), tuple(runs),
                               anchor_index, target_index, EPOCH_PROFILES[epoch_profile])


__all__ = ["Ef5Inputs", "make_ef5_batch", "make_ef5_chunks", "make_ef5_config", "make_ef5_context", "ROLES",
           "MAPPING_VERSION", "PRODUCERS", "EPOCH_PROFILES", "EF5_UNITS", "EF5_FEATURES", "OHLCV_COLUMNS",
           "CLOSE_COLUMNS"]
