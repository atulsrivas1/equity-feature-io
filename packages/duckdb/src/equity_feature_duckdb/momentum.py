"""Lossless supplied momentum inputs; no EMA, MACD, DMI, ADX or stochastic mathematics.

Maps SUPPLIED OHLCV bars into the R17 governed-grid BAR delivery of the frozen momentum and
trend contract (config intraday.momentum.v1, convention group ef2-conv1; core
docs/ef2/MOMENTUM_TREND_CONTRACT_PROPOSAL.md). Nothing is derived, filled or inferred.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, cast

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec,
    ContractError, Coverage, DataKind, ErrorCode, InputScope, IntervalCoverage, Parameter,
    PriceUnit, SessionSpec, SourceBinding, WindowSpec, validate_batch,
)
from equity_feature_contracts.inputs import Cell

ROLES = ("bars",)
_ORIGINS = frozenset(("synthetic", "duckdb_backed_observed", "unavailable"))
MAPPING_VERSION = "ef2-momentum-map1"
CONFIG_IDENTITY = "intraday.momentum.v1"
ALGORITHM_VERSION = "intraday-momentum-v1"
CONVENTION_VERSION = "ef2-conv1"
CONTEXT_SCHEMA = "equity-features.intraday-context.v1"  # the accepted R17 context codec, unchanged
# Closed per-family period parameters (declaration order) and their output ids (lexical order).
FAMILY_PERIODS: dict[str, tuple[str, ...]] = {
    "macd": ("fast_period", "slow_period", "signal_period"),
    "dmi": ("di_period", "adx_period"),
    "stochastic": ("k_period", "k_slowing", "d_period"),
}
FAMILY_FEATURES: dict[str, tuple[str, ...]] = {
    "macd": ("intraday.macd_histogram", "intraday.macd_line", "intraday.macd_signal"),
    "dmi": ("intraday.adx", "intraday.dx", "intraday.minus_di", "intraday.plus_di"),
    "stochastic": ("intraday.stoch_d", "intraday.stoch_k", "intraday.williams_r"),
}
# Units of the ten outputs (new strings except currency/share), for the sink headers of the worker layer.
FEATURE_UNITS: dict[str, str] = {
    **{f: "currency/share" for f in FAMILY_FEATURES["macd"]},
    **{f: "DMI points" for f in FAMILY_FEATURES["dmi"]},
    "intraday.stoch_d": "stochastic points", "intraday.stoch_k": "stochastic points",
    "intraday.williams_r": "Williams %R points",
}
# The one ef2-conv1 value of every convention parameter, as the contract's config section lists them.
CONVENTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "macd": (("ema_seed", "sma_first_n"), ("ema_alpha", "two_over_n_plus_one"),
             ("signal_seed", "sma_first_n_macd"), ("macd_start", "slow_seed_bar"),
             ("numeric_policy", "r17_decimal120_v1")),
    "dmi": (("smoothing", "wilder_average_seeded_by_mean"), ("dm_rule", "strict_greater_zero_on_tie"),
            ("di_scale", "points_0_100"), ("undefined_di_dx", "not_applicable_zero_denominator"),
            ("adx_chain_start", "first_defined_dx"), ("numeric_policy", "r17_decimal120_v1")),
    "stochastic": (("raw_k", "close_location_in_window_including_current"), ("stoch_smoothing", "sma"),
                   ("zero_range", "undefined_not_applicable"),
                   ("oscillator_scale", "points_0_100_williams_minus100_0"),
                   ("numeric_policy", "r17_decimal120_v1")),
}
# Columns of a supplied bar row; open is not part of the momentum contract and is never invented.
BAR_COLUMNS = ("instrument_id", "session_id", "start_ns", "end_ns", "high", "low", "close",
               "volume", "known_at_ns")


def make_momentum_batch(column_order: tuple[str, ...], rows: tuple[tuple[Cell, ...], ...], *,
                        metadata: BatchMetadata) -> CanonicalBatch:
    """Convert exact supplied rectangular BAR cells, retaining order and metadata.

    No sorting, filtering, field filling, unit or basis conversion or timestamp inference occurs.
    Columns the delivery lacks are simply not listed. Admission (grid, order, duplicates, cutoff,
    readiness) belongs to the pure producer; generic canonical validation may refuse an invalid
    original row first.
    """
    if (type(column_order) is not tuple or any(type(name) is not str for name in column_order)
            or type(rows) is not tuple
            or any(type(row) is not tuple or len(row) != len(column_order) for row in rows)
            or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied momentum bar rectangle required")
    result = CanonicalBatch(DataKind.BAR, tuple(Column(name, tuple(row[i] for row in rows))
                                                for i, name in enumerate(column_order)), metadata)
    validate_batch(result, required_fields=())
    return result


def make_slot_coverage(index: int, start_ns: int, end_ns: int, *, expected: int | None,
                       observed: int, complete: bool) -> IntervalCoverage:
    """Declare the per-slot coverage entry `slot:<index>` of one governed grid slot, as supplied."""
    if type(index) is not int or index < 0:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Nonnegative governed slot index required")
    return IntervalCoverage(f"slot:{index}", start_ns, end_ns, Coverage(expected, observed, complete))


def make_momentum_config(*, instrument_id: str, calendar_id: str, grid_id: str, revision: str,
                         sessions: Sequence[SessionSpec], runs: Sequence[tuple[str, int, int, int]],
                         anchor_index: int, target_index: int, mode: str, family: str,
                         fast_period: int | None = None, slow_period: int | None = None,
                         signal_period: int | None = None, di_period: int | None = None,
                         adx_period: int | None = None, k_period: int | None = None,
                         k_slowing: int | None = None, d_period: int | None = None,
                         availability: AvailabilitySpec, adjustment: AdjustmentSpec,
                         price_unit: PriceUnit, evidence_limit: int = 0,
                         conventions: dict[str, str] | None = None) -> ConfigSpec:
    """Build the intraday.momentum.v1 ConfigSpec from explicit caller-supplied selection.

    Envelope (verified byte-identical to the library build_momentum_config): momentum_family, exactly that
    family's period parameters, its convention parameters (default: the single ef2-conv1 value of
    each), evidence_limit and the unchanged R17 context transport (schema, sha256, closed chunks).
    There is no default period or evidence limit. Every range, mode, anchor/target, bound and vocabulary
    check (invalid_config, incompatible_version) belongs to the pure decoder, so malformed values pass
    through unchanged. runs are (session_id, start_ns, step_ns, count).
    """
    given = {"fast_period": fast_period, "slow_period": slow_period, "signal_period": signal_period,
             "di_period": di_period, "adx_period": adx_period, "k_period": k_period,
             "k_slowing": k_slowing, "d_period": d_period}
    if (type(family) is not str or family not in FAMILY_PERIODS
            or any((given[name] is not None) != (name in FAMILY_PERIODS[family]) for name in given)
            or type(sessions) not in (tuple, list) or any(type(s) is not SessionSpec for s in sessions)
            or not sessions or type(runs) not in (tuple, list)
            or any(type(r) is not tuple or len(r) != 4 for r in runs) or not runs
            or (conventions is not None and type(conventions) is not dict)):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Explicit family, its periods, sessions and runs required")
    context = json.dumps({
        "schema": CONTEXT_SCHEMA, "instrument_id": instrument_id, "calendar_id": calendar_id,
        "grid_id": grid_id, "revision": revision, "sessions": [asdict(s) for s in sessions],
        "runs": [{"session_id": r[0], "start_ns": r[1], "step_ns": r[2], "count": r[3]} for r in runs],
        "anchor_index": anchor_index, "target_index": target_index, "mode": mode,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    chunks = tuple(context[i:i + 4096] for i in range(0, len(context), 4096))
    params = [Parameter("momentum_family", family)]
    params += [Parameter(name, given[name]) for name in FAMILY_PERIODS[family]]
    params += [Parameter(name, value)
               for name, value in (CONVENTIONS[family] if conventions is None else conventions.items())]
    params += [Parameter("evidence_limit", evidence_limit), Parameter("context_schema", CONTEXT_SCHEMA),
               Parameter("context_sha256", hashlib.sha256(context.encode("ascii")).hexdigest()),
               Parameter("context_chunks", len(chunks))]
    params += [Parameter(f"context_{i:03}", chunk) for i, chunk in enumerate(chunks)]
    target_id = runs[-1][0]
    target = next((s for s in sessions if s.session_id == target_id), sessions[-1])
    return ConfigSpec(CONFIG_IDENTITY, ALGORITHM_VERSION, tuple(params), target,
                      WindowSpec(len(sessions), target.session_id, tuple(s.session_id for s in sessions),
                                 "completed_eod"), availability, adjustment, price_unit)


@dataclass(frozen=True)
class MomentumInputs:
    """One nullable `bars` role holding the ordered BAR chunks of the governed grid.

    `bars=None` is missing delivery. Origins are explicit caller declarations, not
    capability or rights evidence. Nothing here orders, merges or repairs chunks.
    """
    bars: tuple[CanonicalBatch, ...] | None = None
    provenance: tuple[str, ...] = ("unavailable",)

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 1:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly one momentum origin required")
        origin = self.provenance[0]
        if type(origin) is not str or origin not in _ORIGINS or (self.bars is None) != (origin == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
        if self.bars is not None:
            if type(self.bars) is not tuple:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete tuple of BAR chunks required")
            for batch in self.bars:
                if type(batch) is not CanonicalBatch or batch.kind is not DataKind.BAR:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Momentum role requires BAR batches")
                validate_batch(batch, required_fields=())
            if len({b.metadata.source.input_id for b in self.bars}) != len(self.bars):
                raise ContractError(ErrorCode.DUPLICATE, "Distinct momentum chunk input IDs required")
            if len({b.metadata.namespace for b in self.bars}) > 1:
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One momentum namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return ROLES

    @property
    def slots(self) -> tuple[tuple[CanonicalBatch, ...] | None, ...]:
        return (self.bars,)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return () if self.bars is None else self.bars


__all__ = ["MomentumInputs", "make_momentum_batch", "make_slot_coverage", "make_momentum_config",
           "BAR_COLUMNS", "FAMILY_PERIODS", "FAMILY_FEATURES", "FEATURE_UNITS", "CONVENTIONS",
           "MAPPING_VERSION", "ALGORITHM_VERSION", "CONVENTION_VERSION", "CONFIG_IDENTITY", "CONTEXT_SCHEMA"]


# Original synthetic supplied series keyed by the contract's own fixture ids (inputs only: no expected
# values). f family, p period parameters, s price scale, a anchor slot, ev evidence_limit (absent: the
# contract default 10000), sel selected output subset, none = absent delivery, abs = columns missing from
# the whole delivery. slots are [high, low, close, state]; the compact states are priced, missing,
# empty, null, future and unknown. P01 to P03 carry two series (A, B: same prefix, different tail)
# and the prefix lengths (pre) instead of slots.
_SYNTHETIC = json.loads('''{
    "M01": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"]]},
    "M02": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"]]},
    "M03": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"]]},
    "M04": {"f":"macd","p":{"fast_period":3,"slow_period":5,"signal_period":3},"s":0,"a":0,"slots":[[null,null,7,"priced"],[null,null,7,"priced"],[null,null,7,"priced"],[null,null,7,"priced"],[null,null,7,"priced"],[null,null,7,"priced"],[null,null,7,"priced"]]},
    "M05": {"f":"macd","p":{"fast_period":3,"slow_period":5,"signal_period":3},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,11,"priced"],[null,null,12,"priced"],[null,null,13,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,16,"priced"],[null,null,17,"priced"]]},
    "M06": {"f":"macd","p":{"fast_period":3,"slow_period":5,"signal_period":3},"s":0,"a":0,"slots":[[null,null,20,"priced"],[null,null,19,"priced"],[null,null,18,"priced"],[null,null,17,"priced"],[null,null,16,"priced"],[null,null,15,"priced"],[null,null,14,"priced"],[null,null,13,"priced"]]},
    "M07_5": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"]]},
    "M07_6": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"],[null,null,11,"priced"]]},
    "M07_7": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"],[null,null,11,"priced"],[null,null,10,"priced"]]},
    "M07_8": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"],[null,null,11,"priced"],[null,null,10,"priced"],[null,null,12,"priced"]]},
    "M07_9": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"],[null,null,11,"priced"],[null,null,10,"priced"],[null,null,12,"priced"],[null,null,15,"priced"]]},
    "M07_10": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"],[null,null,11,"priced"],[null,null,10,"priced"],[null,null,12,"priced"],[null,null,15,"priced"],[null,null,16,"priced"]]},
    "M05b": {"f":"macd","p":{"fast_period":3,"slow_period":5,"signal_period":3},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,11,"priced"],[null,null,13,"priced"],[null,null,16,"priced"],[null,null,20,"priced"],[null,null,25,"priced"],[null,null,31,"priced"],[null,null,38,"priced"]]},
    "M25": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,1,"priced"],[null,null,1,"priced"],[null,null,4,"priced"],[null,null,6,"priced"]]},
    "M26": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,1,"priced"],[null,null,2,"priced"],[null,null,3,"priced"],[null,null,1,"priced"]]},
    "M08": {"f":"macd","p":{"fast_period":1,"slow_period":2,"signal_period":1},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,13,"priced"],[null,null,11,"priced"],[null,null,16,"priced"]]},
    "M09": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":2,"a":0,"slots":[[null,null,10050,"priced"],[null,null,10100,"priced"],[null,null,10200,"priced"],[null,null,10150,"priced"],[null,null,10300,"priced"]]},
    "M10": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,1152921504606846975,"priced"],[null,null,1152921504606846976,"priced"],[null,null,1152921504606846977,"priced"],[null,null,1152921504606846979,"priced"]]},
    "M11": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,null,"missing"],[null,null,15,"priced"],[null,null,16,"priced"]]},
    "M12": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,null,"missing"],[null,null,12,"priced"]]},
    "M13": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,null,"null"],[null,null,15,"priced"],[null,null,16,"priced"]]},
    "M14": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"future"],[null,null,15,"priced"],[null,null,16,"priced"]]},
    "M15": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"unknown"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,16,"priced"]]},
    "M16": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"abs":["close"],"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"]]},
    "M17": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"none":1,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"]]},
    "M18": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"abs":["high","low"],"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"]]},
    "M19": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,null,"empty"],[null,null,15,"priced"],[null,null,16,"priced"]]},
    "M20": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":2,"slots":[[null,null,null,"missing"],[null,null,999,"priced"],[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"]]},
    "M22": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"ev":4,"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"]]},
    "M23": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"sel":["intraday.macd_line"],"slots":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"]]},
    "M24": {"f":"macd","p":{"fast_period":3,"slow_period":6,"signal_period":4},"s":0,"a":0,"slots":[[null,null,44,"priced"],[null,null,46,"priced"],[null,null,45,"priced"],[null,null,47,"priced"],[null,null,50,"priced"],[null,null,49,"priced"],[null,null,48,"priced"],[null,null,52,"priced"],[null,null,55,"priced"],[null,null,54,"priced"],[null,null,53,"priced"],[null,null,51,"priced"],[null,null,50,"priced"],[null,null,52,"priced"]]},
    "D02_inside": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[18,12,14,"priced"]]},
    "D02_outside_up": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[24,7,20,"priced"]]},
    "D02_outside_down": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[22,5,8,"priced"]]},
    "D02_tie_positive": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[23,7,15,"priced"]]},
    "D02_shift_up": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[22,12,20,"priced"]]},
    "D02_shift_down": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[18,8,9,"priced"]]},
    "D02_gap_up": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[40,30,38,"priced"]]},
    "D02_zero_up": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[20,11,12,"priced"]]},
    "D02_tie_zero": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,10,15,"priced"],[20,10,15,"priced"]]},
    "D02_flat2": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[15,15,15,"priced"],[15,15,15,"priced"]]},
    "D01": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"]]},
    "D03_3": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"]]},
    "D03_4": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"]]},
    "D03_5": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D03_7": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"],[23,19,20,"priced"],[26,21,25,"priced"]]},
    "D04": {"f":"dmi","p":{"di_period":3,"adx_period":3},"s":0,"a":0,"slots":[[12,10,11,"priced"],[13,11,12,"priced"],[14,12,13,"priced"],[15,13,14,"priced"],[16,14,15,"priced"],[17,15,16,"priced"],[18,16,17,"priced"]]},
    "D05": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"]]},
    "D06_3": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"]]},
    "D06_4": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[12,10,12,"priced"]]},
    "D06_5": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[12,10,12,"priced"],[14,12,14,"priced"]]},
    "D06_6": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[12,10,12,"priced"],[14,12,14,"priced"],[13,11,12,"priced"]]},
    "D07": {"f":"dmi","p":{"di_period":2,"adx_period":3},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D08": {"f":"dmi","p":{"di_period":3,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,15,16,"priced"],[23,18,22,"priced"],[22,17,18,"priced"],[25,19,24,"priced"],[24,18,19,"priced"],[26,20,25,"priced"],[25,19,20,"priced"]]},
    "D09": {"f":"dmi","p":{"di_period":1,"adx_period":1},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"]]},
    "D10": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[null,null,null,"missing"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D11": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[null,16,18,"null"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D12": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,null,"null"]]},
    "D13": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,null,"null"],[25,20,22,"priced"]]},
    "D14": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"abs":["high"],"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D15": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"none":1,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D16": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"priced"],[null,null,null,"empty"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D17": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[20,16,18,"future"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D18": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":2,"slots":[[null,null,null,"missing"],[1,1,1,"priced"],[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"]]},
    "D20": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[null,null,null,"missing"],[12,10,12,"priced"]]},
    "D21": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[null,null,null,"missing"],[10,10,10,"priced"]]},
    "D22": {"f":"dmi","p":{"di_period":1,"adx_period":2},"s":0,"a":0,"slots":[[20,10,15,"priced"],[24,7,20,"priced"],[23,10,18,"priced"],[26,12,25,"priced"]]},
    "D19": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"ev":5,"slots":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"]]},
    "T01": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"]]},
    "T02": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"]]},
    "T03": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"]]},
    "T04": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"]]},
    "T05": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"],[13,11,11,"priced"],[12,10,10,"priced"]]},
    "T06": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,13,"priced"],[14,11,14,"priced"],[15,12,15,"priced"]]},
    "T07": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[15,12,12,"priced"],[14,11,11,"priced"],[13,10,10,"priced"],[12,9,9,"priced"],[11,8,8,"priced"]]},
    "T08": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"]]},
    "T09": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[12,10,11,"priced"]]},
    "T10": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[12,10,11,"priced"],[13,10,12,"priced"]]},
    "T11": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,10,10,"priced"],[10,10,10,"priced"],[10,10,10,"priced"],[12,10,11,"priced"],[13,10,12,"priced"],[13,11,13,"priced"]]},
    "T12": {"f":"stochastic","p":{"k_period":3,"k_slowing":1,"d_period":1},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"]]},
    "T13": {"f":"stochastic","p":{"k_period":1,"k_slowing":1,"d_period":1},"s":0,"a":0,"slots":[[10,8,9,"priced"],[20,10,10,"priced"]]},
    "T14": {"f":"stochastic","p":{"k_period":1,"k_slowing":1,"d_period":1},"s":0,"a":0,"slots":[[10,8,9,"priced"],[10,10,10,"priced"]]},
    "T15": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[12,10,11,"priced"],[12,10,10,"priced"],[12,10,12,"priced"],[12,10,11,"priced"],[12,10,12,"priced"]]},
    "T16": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[null,null,null,"missing"],[14,12,14,"priced"],[13,11,11,"priced"],[12,10,10,"priced"],[13,10,12,"priced"]]},
    "T17": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[null,null,null,"missing"],[13,11,11,"priced"],[12,10,10,"priced"],[13,10,12,"priced"]]},
    "T18": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,null,"null"],[14,12,14,"priced"],[13,11,11,"priced"],[12,10,10,"priced"],[13,10,12,"priced"]]},
    "T19": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"],[13,11,null,"null"],[12,10,10,"priced"],[13,10,12,"priced"]]},
    "T20": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"],[13,11,11,"priced"],[null,10,10,"null"],[13,10,12,"priced"]]},
    "T21": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"abs":["high","low"],"slots":[[null,null,9,"priced"],[null,null,11,"priced"],[null,null,12,"priced"],[null,null,11,"priced"],[null,null,14,"priced"]]},
    "T22": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"none":1,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"]]},
    "T23": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"future"],[14,12,14,"priced"],[13,11,11,"priced"]]},
    "T24": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[null,null,null,"empty"],[14,12,14,"priced"],[13,11,11,"priced"]]},
    "T25": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":3,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"]]},
    "T27": {"f":"stochastic","p":{"k_period":5,"k_slowing":3,"d_period":3},"s":0,"a":0,"slots":[[30,26,28,"priced"],[32,27,31,"priced"],[33,28,29,"priced"],[31,26,27,"priced"],[30,24,25,"priced"],[29,23,28,"priced"],[33,27,32,"priced"],[35,30,34,"priced"],[36,31,33,"priced"],[34,29,30,"priced"],[33,28,32,"priced"],[35,31,35,"priced"]]},
    "T28": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":2,"a":0,"slots":[[1000,800,900,"priced"],[1200,900,1100,"priced"],[1300,1000,1200,"priced"],[1400,1100,1100,"priced"],[1400,1200,1400,"priced"]]},
    "T29": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"ev":6,"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"]]},
    "T30": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"sel":["intraday.williams_r"],"slots":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"]]},
    "P01": {"f":"macd","p":{"fast_period":2,"slow_period":3,"signal_period":2},"s":0,"a":0,"A":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"],[null,null,11,"priced"],[null,null,10,"priced"],[null,null,12,"priced"],[null,null,15,"priced"],[null,null,16,"priced"]],"B":[[null,null,10,"priced"],[null,null,12,"priced"],[null,null,14,"priced"],[null,null,15,"priced"],[null,null,13,"priced"],[null,null,11,"priced"],[null,null,99,"priced"],[null,null,1,"priced"],[null,null,50,"priced"],[null,null,50,"priced"]],"pre":[3,4,5,6]},
    "P02": {"f":"dmi","p":{"di_period":2,"adx_period":2},"s":0,"a":0,"A":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"],[23,19,20,"priced"],[26,21,25,"priced"]],"B":[[20,16,18,"priced"],[22,17,21,"priced"],[21,16,17,"priced"],[24,18,23,"priced"],[25,20,22,"priced"],[90,2,50,"priced"],[3,1,2,"priced"]],"pre":[3,4,5]},
    "P03": {"f":"stochastic","p":{"k_period":3,"k_slowing":2,"d_period":2},"s":0,"a":0,"A":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"],[13,11,11,"priced"],[12,10,10,"priced"]],"B":[[10,8,9,"priced"],[12,9,11,"priced"],[13,10,12,"priced"],[14,11,11,"priced"],[14,12,14,"priced"],[50,1,25,"priced"],[7,7,7,"priced"]],"pre":[3,4,5]}
}''')
SYNTHETIC_MOMENTUM_CASES = tuple(_SYNTHETIC)
_STEP_NS = 10
_VOLUME = 100  # positive volume of every supplied bar; the contract fixes none
_KNOWN_NS = 5  # known_at of causal rows


def _case(case_id: str) -> dict[str, Any]:
    if type(case_id) is not str or case_id not in _SYNTHETIC:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic momentum case")
    return cast(dict[str, Any], _SYNTHETIC[case_id])


def _series(case_id: str, series: str, length: int | None) -> list[list[Any]]:
    case = _case(case_id)
    if "slots" in case:
        if series != "A" or length not in (None, len(case["slots"])):
            raise ContractError(ErrorCode.INVALID_CONFIG, "Only the prefix fixtures P01 to P03 take series and length")
        return cast(list[list[Any]], case["slots"])
    if series not in ("A", "B"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "series must be A or B")
    full = cast(list[list[Any]], case[series])
    if length is None:
        return full
    if type(length) is not int or (length not in case["pre"] and length != len(full)):
        raise ContractError(ErrorCode.INVALID_CONFIG, "length must be one of the fixture prefix lengths")
    return full[:length]


def synthetic_momentum_features(case_id: str) -> tuple[str, ...]:
    """The output subset the contract fixture selects: its whole family, or the listed subset."""
    case = _case(case_id)
    return tuple(case.get("sel") or FAMILY_FEATURES[case["f"]])


def synthetic_momentum_prefix_lengths(case_id: str) -> tuple[int, ...]:
    """Prefix lengths of a prefix-property fixture P01 to P03; empty for every other fixture."""
    return tuple(_case(case_id).get("pre", ()))


def synthetic_momentum_config(case_id: str, *, length: int | None = None) -> ConfigSpec:
    """Detached synthetic intraday.momentum.v1 config for a contract fixture (reset epoch).

    Entity X in namespace SYN, ten-ns grid of one slot per supplied position. With anchor 0 one session S
    holds every slot; with anchor a > 0 slots 0..a-1 form a prior session S0 outside the epoch and S
    starts at the anchor. The target is the last slot, K = evaluation = the end of the last slot (also the
    session close), raw basis, USD at the fixture scale. evidence_limit is the fixture's, else the
    contract default 10000. `length` (P01 to P03 only) truncates the series to a prefix. These grid and
    entity choices are not contract-specified (listed for the worker).
    """
    case = _case(case_id)
    count = len(_series(case_id, "A", length))
    anchor = case["a"]
    end = count * _STEP_NS
    if anchor:
        sessions = (SessionSpec("SYN", "S0", 0, anchor * _STEP_NS, "UTC"),
                    SessionSpec("SYN", "S", anchor * _STEP_NS, end, "UTC"))
        runs = (("S0", 0, _STEP_NS, anchor), ("S", anchor * _STEP_NS, _STEP_NS, count - anchor))
    else:
        sessions = (SessionSpec("SYN", "S", 0, end, "UTC"),)
        runs = (("S", 0, _STEP_NS, count),)
    return make_momentum_config(
        instrument_id="X", calendar_id="synthetic-calendar", grid_id="ten-ns-grid", revision="revision1",
        sessions=sessions, runs=runs, anchor_index=anchor, target_index=count - 1, mode="reset",
        family=case["f"], **case["p"],
        availability=AvailabilitySpec(end, end, end), adjustment=AdjustmentSpec(),
        price_unit=PriceUnit(case["s"], "USD"), evidence_limit=case.get("ev", 10000))


def synthetic_momentum_fixture(case_id: str, *, series: str = "A", length: int | None = None,
                               empty_form: str = "row") -> MomentumInputs:
    """Original synthetic OHLCV slots of one contract fixture as BAR chunks; nothing is computed.

    One chunk per actual session (bars-000; with anchor > 0 the prior session S0 is bars-000 and S bars-001).

    priced slots carry volume 100 known at 5. Where the compact fixture leaves high and low null
    (the MACD fixtures) a priced, future or unknown bar is supplied with high = low = close so the
    bar is valid; the producer reads only the columns its family needs. missing is a declared incomplete
    slot without a row; empty (observed-empty) is a zero-volume all-null-OHLC row with complete coverage
    (empty_form="row", default) or complete coverage of expected 0 without a row ("coverage"); null is a
    row with null volume and the listed OHLC field null (a positive-volume bar with a null OHLC cell
    is invalid); future is known after K and unknown has known_at null. Columns the fixture lists as
    absent are omitted from the whole delivery and "none" delivery is bars=None. `series`/`length`
    select series A or B and a prefix of the prefix-property fixtures P01 to P03.
    """
    if empty_form not in ("row", "coverage"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "empty_form must be row or coverage")
    case = _case(case_id)
    slots = _series(case_id, series, length)
    if case.get("none"):
        return MomentumInputs(None, ("unavailable",))
    count, anchor = len(slots), case["a"]
    end_k = count * _STEP_NS
    absent = set(case.get("abs", ()))
    rows: list[list[tuple[Cell, ...]]] = [[], []]  # one BAR chunk per actual session: prior S0, then S
    entries: list[list[IntervalCoverage]] = [[], []]
    for index, (high, low, close, state) in enumerate(slots):
        start, end = index * _STEP_NS, (index + 1) * _STEP_NS
        part = 0 if index < anchor else 1
        row: dict[str, Cell] | None = None
        if state in ("priced", "future", "unknown"):
            known = {"priced": _KNOWN_NS, "future": end_k + 50, "unknown": None}[state]
            row = {"high": close if high is None else high, "low": close if low is None else low,
                   "close": close, "volume": _VOLUME, "known_at_ns": known}
        elif state == "null":
            row = {"high": high, "low": low, "close": close, "volume": None, "known_at_ns": _KNOWN_NS}
        elif state == "empty" and empty_form == "row":
            row = {"high": None, "low": None, "close": None, "volume": 0, "known_at_ns": _KNOWN_NS}
        if row is not None:
            cells = (("instrument_id", "X"), ("session_id", "S" if part else "S0"), ("start_ns", start),
                     ("end_ns", end), *row.items())
            rows[part].append(tuple(v for k, v in cells if k not in absent))
            entries[part].append(make_slot_coverage(index, start, end, expected=1, observed=1, complete=True))
        elif state == "empty":
            entries[part].append(make_slot_coverage(index, start, end, expected=0, observed=0, complete=True))
        elif state == "missing":
            entries[part].append(make_slot_coverage(index, start, end, expected=1, observed=0, complete=False))
        else:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Unknown compact slot state")
    columns = tuple(c for c in BAR_COLUMNS if c not in absent)
    batches: list[CanonicalBatch] = []
    for part, (first, last) in enumerate(((0, anchor), (anchor, count))):
        if first == last:
            continue
        expected = sum(cast(int, e.coverage.expected) for e in entries[part])
        coverage = Coverage(expected, len(rows[part]),
                            all(e.coverage.complete for e in entries[part]) and expected == len(rows[part]))
        metadata = BatchMetadata(
            "SYN", SourceBinding("SYN-BARS", "snap1", MAPPING_VERSION, f"bars-{len(batches):03}"), coverage,
            PriceUnit(case["s"], "USD"), scope=InputScope(first * _STEP_NS, last * _STEP_NS, "synthetic-v1"),
            interval_coverage=tuple(entries[part]))
        batches.append(make_momentum_batch(columns, tuple(rows[part]), metadata=metadata))
    return MomentumInputs(tuple(batches), ("synthetic",))


__all__ += ["SYNTHETIC_MOMENTUM_CASES", "synthetic_momentum_features", "synthetic_momentum_prefix_lengths",
            "synthetic_momentum_config", "synthetic_momentum_fixture"]
