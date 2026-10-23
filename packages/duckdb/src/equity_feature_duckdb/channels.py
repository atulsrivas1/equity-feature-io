"""Lossless supplied channel inputs; no Ichimoku, Keltner, Donchian, pivot, percentile or squeeze mathematics.

Maps SUPPLIED OHLCV bars into the R17 governed-grid BAR delivery of the frozen Ichimoku and price-channel
contract (config identities ef2.<producer>, contract version ef2-v1, algorithm ef2-channels-v1; core
docs/ef2/ICHIMOKU_CHANNELS_CONTRACT_PROPOSAL.md). Nothing is derived, filled or inferred.
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
MAPPING_VERSION = "ef2-channels-map1"
ALGORITHM_VERSION = "ef2-channels-v1"
CONTRACT_VERSION = "ef2-v1"
CONTEXT_SCHEMA = "equity-features.intraday-context.v1"  # the accepted R17 context codec, unchanged
# Closed operation parameters per producer (declaration order) and the identity ef2.<producer>.
PRODUCER_PARAMETERS: dict[str, tuple[str, ...]] = {
    "ichimoku": ("conversion_period", "base_period", "leading_b_period", "displacement"),
    "keltner": ("ema_period", "atr_period", "atr_multiplier_num", "atr_multiplier_den"),
    "donchian": ("period",),
    "pivot_levels": (),
    "band_width_percentile": ("band_period", "band_k_num", "band_k_den", "population_size", "min_population"),
    "bollinger_keltner_squeeze": ("band_period", "band_k_num", "band_k_den", "ema_period", "atr_period",
                                  "atr_multiplier_num", "atr_multiplier_den"),
}
CONFIG_IDENTITIES: dict[str, str] = {name: f"ef2.{name}" for name in PRODUCER_PARAMETERS}
# The single convention label of each producer (the contract's convention_version).
CONVENTION_LABELS: dict[str, str] = {
    "ichimoku": "ef2-ichimoku-conv1", "keltner": "ef2-keltner-conv1", "donchian": "ef2-donchian-conv1",
    "pivot_levels": "ef2-pivot-conv1", "band_width_percentile": "ef2-bandpct-conv1",
    "bollinger_keltner_squeeze": "ef2-squeeze-conv1",
}
# Output ids of each producer (lexical order, the complete fixed set of one result).
PRODUCER_FEATURES: dict[str, tuple[str, ...]] = {
    "ichimoku": tuple(f"trend.ichimoku.{n}" for n in (
        "base_line", "conversion_line", "lagging_line_observed", "lagging_line_reference_close",
        "leading_span_a_displayed", "leading_span_a_observed", "leading_span_b_displayed",
        "leading_span_b_observed")),
    "keltner": tuple(f"channel.keltner.{n}" for n in ("lower", "middle", "upper", "width_ratio")),
    "donchian": tuple(f"channel.donchian.{n}" for n in ("lower", "middle", "upper", "width_ratio")),
    "pivot_levels": tuple(f"channel.pivot.{n}" for n in
                          ("point", "resistance_1", "resistance_2", "support_1", "support_2")),
    "band_width_percentile": ("channel.band_width.percentile",),
    "bollinger_keltner_squeeze": ("channel.squeeze.bollinger_inside_keltner", "channel.squeeze.lower_gap",
                                  "channel.squeeze.upper_gap"),
}
# Units and dtypes of the 25 outputs per the contract header table, for the sink headers of the worker
# layer: float64 everywhere except the squeeze flag (bool, unit boolean).
FEATURE_UNITS: dict[str, str] = {
    f: ("fraction" if f.endswith(("width_ratio", "percentile")) else
        "boolean" if f.endswith("bollinger_inside_keltner") else "currency/share")
    for ids in PRODUCER_FEATURES.values() for f in ids
}
FEATURE_DTYPES: dict[str, str] = {
    f: "bool" if f.endswith("bollinger_inside_keltner") else "float64"
    for ids in PRODUCER_FEATURES.values() for f in ids
}
# Columns of a supplied bar row; open is not part of the channels contract and is never invented.
BAR_COLUMNS = ("instrument_id", "session_id", "start_ns", "end_ns", "high", "low", "close",
               "volume", "known_at_ns")


def make_channels_batch(column_order: tuple[str, ...], rows: tuple[tuple[Cell, ...], ...], *,
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
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied channels bar rectangle required")
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


def make_channels_config(*, producer: str, instrument_id: str, calendar_id: str, grid_id: str, revision: str,
                         sessions: Sequence[SessionSpec], runs: Sequence[tuple[str, int, int, int]],
                         anchor_index: int, target_index: int, mode: str,
                         conversion_period: int | None = None, base_period: int | None = None,
                         leading_b_period: int | None = None, displacement: int | None = None,
                         ema_period: int | None = None, atr_period: int | None = None,
                         atr_multiplier_num: int | None = None, atr_multiplier_den: int | None = None,
                         period: int | None = None, band_period: int | None = None,
                         band_k_num: int | None = None, band_k_den: int | None = None,
                         population_size: int | None = None, min_population: int | None = None,
                         availability: AvailabilitySpec, adjustment: AdjustmentSpec,
                         price_unit: PriceUnit, evidence_limit: int = 0,
                         convention_version: str | None = None) -> ConfigSpec:
    """Build the ef2.<producer> ConfigSpec from explicit caller-supplied selection.

    Envelope (verified byte-identical to the library build_channels_config): exactly that producer's
    operation parameters, convention_version (default: the producer's single label), evidence_limit
    and the unchanged R17 context transport (schema, sha256, closed chunks). There is no default
    period; evidence_limit defaults to 0 as in the library. Every range, mode, anchor/target, bound
    and vocabulary check (invalid_config, incompatible_version) belongs to the pure decoder, so
    malformed values pass through unchanged. runs are (session_id, start_ns, step_ns, count).
    """
    given = {"conversion_period": conversion_period, "base_period": base_period,
             "leading_b_period": leading_b_period, "displacement": displacement, "ema_period": ema_period,
             "atr_period": atr_period, "atr_multiplier_num": atr_multiplier_num,
             "atr_multiplier_den": atr_multiplier_den, "period": period, "band_period": band_period,
             "band_k_num": band_k_num, "band_k_den": band_k_den, "population_size": population_size,
             "min_population": min_population}
    if (type(producer) is not str or producer not in PRODUCER_PARAMETERS
            or any((given[name] is not None) != (name in PRODUCER_PARAMETERS[producer]) for name in given)
            or type(sessions) not in (tuple, list) or any(type(s) is not SessionSpec for s in sessions)
            or not sessions or type(runs) not in (tuple, list)
            or any(type(r) is not tuple or len(r) != 4 for r in runs) or not runs):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Explicit producer, its parameters, sessions and runs required")
    context = json.dumps({
        "schema": CONTEXT_SCHEMA, "instrument_id": instrument_id, "calendar_id": calendar_id,
        "grid_id": grid_id, "revision": revision, "sessions": [asdict(s) for s in sessions],
        "runs": [{"session_id": r[0], "start_ns": r[1], "step_ns": r[2], "count": r[3]} for r in runs],
        "anchor_index": anchor_index, "target_index": target_index, "mode": mode,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    chunks = tuple(context[i:i + 4096] for i in range(0, len(context), 4096))
    params = [Parameter(name, given[name]) for name in PRODUCER_PARAMETERS[producer]]
    params += [Parameter("convention_version", CONVENTION_LABELS[producer] if convention_version is None
                         else convention_version),
               Parameter("evidence_limit", evidence_limit), Parameter("context_schema", CONTEXT_SCHEMA),
               Parameter("context_sha256", hashlib.sha256(context.encode("ascii")).hexdigest()),
               Parameter("context_chunks", len(chunks))]
    params += [Parameter(f"context_{i:03}", chunk) for i, chunk in enumerate(chunks)]
    target_id = runs[-1][0]
    target = next((s for s in sessions if s.session_id == target_id), sessions[-1])
    return ConfigSpec(CONFIG_IDENTITIES[producer], ALGORITHM_VERSION, tuple(params), target,
                      WindowSpec(len(sessions), target.session_id, tuple(s.session_id for s in sessions),
                                 "completed_eod"), availability, adjustment, price_unit)


@dataclass(frozen=True)
class ChannelsInputs:
    """One nullable `bars` role holding the ordered BAR chunks of the governed grid (one per session).

    `bars=None` is missing delivery. Origins are explicit caller declarations, not
    capability or rights evidence. Nothing here orders, merges or repairs chunks.
    """
    bars: tuple[CanonicalBatch, ...] | None = None
    provenance: tuple[str, ...] = ("unavailable",)

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 1:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly one channels origin required")
        origin = self.provenance[0]
        if type(origin) is not str or origin not in _ORIGINS or (self.bars is None) != (origin == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
        if self.bars is not None:
            if type(self.bars) is not tuple:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete tuple of BAR chunks required")
            for batch in self.bars:
                if type(batch) is not CanonicalBatch or batch.kind is not DataKind.BAR:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Channels role requires BAR batches")
                validate_batch(batch, required_fields=())
            if len({b.metadata.source.input_id for b in self.bars}) != len(self.bars):
                raise ContractError(ErrorCode.DUPLICATE, "Distinct channels chunk input IDs required")
            if len({b.metadata.namespace for b in self.bars}) > 1:
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One channels namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return ROLES

    @property
    def slots(self) -> tuple[tuple[CanonicalBatch, ...] | None, ...]:
        return (self.bars,)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return () if self.bars is None else self.bars


__all__ = ["ChannelsInputs", "make_channels_batch", "make_slot_coverage", "make_channels_config",
           "BAR_COLUMNS", "PRODUCER_PARAMETERS", "PRODUCER_FEATURES", "FEATURE_UNITS", "FEATURE_DTYPES",
           "CONVENTION_LABELS", "CONFIG_IDENTITIES", "MAPPING_VERSION", "ALGORITHM_VERSION",
           "CONTRACT_VERSION", "CONTEXT_SCHEMA"]


# Original synthetic supplied series keyed by the contract's own fixture ids (inputs only: no expected
# values). p producer, q its operation parameters, s price scale, x slots per governed session, a anchor
# slot (the first slot of the last session), ev evidence_limit, abs = columns missing from the whole
# delivery, none = absent delivery. slots are [high, low, close, state]; the compact states are priced,
# gap, empty, null, future and unknown. The prefix fixtures are plain stand-alone fixtures.
_SYNTHETIC = json.loads('''{
    "ICH-01": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "ICH-02": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[7],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"]]},
    "ICH-03": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[2],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"]]},
    "ICH-04": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1100,1050,1090,"priced"],[1120,1060,1110,"priced"],[900,880,890,"priced"],[950,880,940,"priced"]]},
    "ICH-05": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"future"],[1040,1000,1035,"future"],[1060,1030,1055,"future"],[1070,1040,1060,"future"]]},
    "ICH-06": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"gap"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "ICH-07": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"abs":["high","low"],"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "ICH-08": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[null,1030,1055,"null"],[1070,1040,1060,"priced"]]},
    "ICH-09": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"]]},
    "ICH-11": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[6,6],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "ICH-12": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[null,null,null,"empty"],[1070,1040,1060,"priced"]]},
    "ICH-13": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":1000,"none":1,"slots":[]},
    "ICH-14": {"p":"ichimoku","q":{"conversion_period":9,"base_period":26,"leading_b_period":52,"displacement":26},"s":2,"x":[80],"a":0,"ev":1000,"slots":[[10010,9990,10000,"priced"],[10078,10038,10063,"priced"],[10035,10000,10015,"priced"],[10103,10048,10078,"priced"],[10060,10010,10030,"priced"],[10017,9972,9982,"priced"],[10085,10020,10045,"priced"],[10007,9982,9997,"priced"],[10194,10149,10179,"priced"],[10032,9992,10012,"priced"],[9989,9954,9964,"priced"],[10176,10121,10146,"priced"],[10014,9964,9979,"priced"],[10201,10131,10161,"priced"],[10123,10093,10113,"priced"],[9961,9936,9946,"priced"],[10148,10103,10128,"priced"],[10105,10065,10080,"priced"],[10173,10113,10143,"priced"],[10130,10075,10095,"priced"],[9968,9918,9928,"priced"],[10120,10085,10110,"priced"],[10077,10047,10062,"priced"],[9915,9865,9895,"priced"],[10102,10057,10077,"priced"],[10059,10019,10029,"priced"],[10127,10067,10092,"priced"],[10084,10029,10044,"priced"],[10006,9966,9996,"priced"],[10074,10039,10059,"priced"],[10031,10001,10011,"priced"],[10218,10168,10193,"priced"],[10056,10011,10026,"priced"],[10013,9948,9978,"priced"],[10200,10140,10160,"priced"],[10003,9983,9993,"priced"],[10190,10150,10175,"priced"],[10028,9993,10008,"priced"],[9985,9930,9960,"priced"],[10172,10122,10142,"priced"],[10010,9965,9975,"priced"],[10197,10132,10157,"priced"],[10119,10094,10109,"priced"],[9957,9912,9942,"priced"],[10144,10104,10124,"priced"],[10101,10066,10076,"priced"],[9939,9884,9909,"priced"],[10126,10076,10091,"priced"],[10083,10013,10043,"priced"],[10116,10086,10106,"priced"],[10073,10048,10058,"priced"],[10030,9985,10010,"priced"],[10098,10058,10073,"priced"],[10055,9995,10025,"priced"],[10123,10068,10088,"priced"],[10080,10030,10040,"priced"],[10002,9967,9992,"priced"],[10070,10040,10055,"priced"],[10027,9977,10007,"priced"],[10214,10169,10189,"priced"],[10052,10012,10022,"priced"],[10009,9949,9974,"priced"],[10196,10141,10156,"priced"],[9999,9959,9989,"priced"],[10186,10151,10171,"priced"],[10143,10113,10123,"priced"],[9981,9931,9956,"priced"],[10168,10123,10138,"priced"],[10125,10060,10090,"priced"],[9963,9903,9923,"priced"],[10115,10095,10105,"priced"],[9953,9913,9938,"priced"],[10140,10105,10120,"priced"],[10097,10042,10072,"priced"],[9935,9885,9905,"priced"],[10122,10077,10087,"priced"],[10079,10014,10039,"priced"],[10112,10087,10102,"priced"],[10069,10024,10054,"priced"],[10026,9986,10006,"priced"]]},
    "ICH-15": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[8],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"]]},
    "ICH-16": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":4},"s":2,"x":[12],"a":0,"ev":5,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "ICH-17": {"p":"ichimoku","q":{"conversion_period":3,"base_period":5,"leading_b_period":8,"displacement":6},"s":2,"x":[6,6],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "KEL-01": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "KEL-02": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[3],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"]]},
    "KEL-03": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"gap"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "KEL-04": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"]]},
    "KEL-05": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[6,6],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "KEL-06": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[null,1040,1060,"null"]]},
    "KEL-07": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":2,"atr_multiplier_den":3},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "KEL-08": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"future"]]},
    "KEL-09": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[10],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"]]},
    "KEL-10": {"p":"keltner","q":{"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":14,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"future"]]},
    "DON-01": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "DON-02": {"p":"donchian","q":{"period":4},"s":2,"x":[3],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"]]},
    "DON-03": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[null,1030,1055,"null"],[1070,1040,1060,"priced"]]},
    "DON-04": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"gap"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "DON-05": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"]]},
    "DON-06": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"future"]]},
    "DON-07": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"none":1,"slots":[]},
    "DON-08": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"gap"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "DON-09": {"p":"donchian","q":{"period":4},"s":2,"x":[10],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"]]},
    "DON-10": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":0,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "DON-11": {"p":"donchian","q":{"period":4},"s":2,"x":[12],"a":0,"ev":1000,"abs":["high","low"],"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "PIV-01": {"p":"pivot_levels","q":{},"s":2,"x":[6,4],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1015,1000,1010,"priced"],[1030,1005,1020,"priced"],[1025,1010,1015,"priced"],[1040,1012,1038,"priced"]]},
    "PIV-02": {"p":"pivot_levels","q":{},"s":2,"x":[6,4],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1015,1000,1010,"gap"],[1030,1005,1020,"future"],[1025,1010,1015,"unknown"],[null,null,null,"empty"]]},
    "PIV-03": {"p":"pivot_levels","q":{},"s":2,"x":[6,4],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"gap"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1015,1000,1010,"priced"],[1030,1005,1020,"priced"],[1025,1010,1015,"priced"],[1040,1012,1038,"priced"]]},
    "PIV-04": {"p":"pivot_levels","q":{},"s":2,"x":[4],"a":0,"ev":1000,"slots":[[1015,1000,1010,"priced"],[1030,1005,1020,"priced"],[1025,1010,1015,"priced"],[1040,1012,1038,"priced"]]},
    "PIV-05": {"p":"pivot_levels","q":{},"s":2,"x":[2,2],"a":2,"ev":1000,"slots":[[10000,200,5000,"priced"],[5000,100,100,"priced"],[1015,1000,1010,"priced"],[1030,1005,1020,"priced"]]},
    "PIV-06": {"p":"pivot_levels","q":{},"s":2,"x":[3,3,2],"a":6,"ev":1000,"slots":[[2000,1900,1950,"priced"],[2000,1900,1950,"priced"],[2000,1900,1950,"priced"],[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1015,1000,1010,"priced"],[1030,1005,1020,"priced"]]},
    "PIV-08": {"p":"pivot_levels","q":{},"s":2,"x":[6,4],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"future"],[1015,1000,1010,"priced"],[1030,1005,1020,"priced"],[1025,1010,1015,"priced"],[1040,1012,1038,"priced"]]},
    "PIV-09": {"p":"pivot_levels","q":{},"s":2,"x":[3,2],"a":3,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"]]},
    "PIV-10": {"p":"pivot_levels","q":{},"s":2,"x":[6,1],"a":6,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1015,1000,1010,"priced"]]},
    "PIV-11": {"p":"pivot_levels","q":{},"s":2,"x":[6,4],"a":6,"ev":4,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"future"],[1015,1000,1010,"priced"],[1030,1005,1020,"priced"],[1025,1010,1015,"priced"],[1040,1012,1038,"priced"]]},
    "PCT-01": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "PCT-02": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[8],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1010,1010,1010,"priced"],[1020,1020,1020,"priced"],[1000,1000,1000,"priced"],[1010,1010,1010,"priced"],[1020,1020,1020,"priced"],[1000,1000,1000,"priced"],[1010,1010,1010,"priced"]]},
    "PCT-03": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[8],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"]]},
    "PCT-04": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[8],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1100,1100,1100,"priced"]]},
    "PCT-05": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[8],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1100,1100,1100,"priced"],[1000,1000,1000,"priced"],[1100,1100,1100,"priced"],[1000,1000,1000,"priced"],[1050,1050,1050,"priced"],[1050,1050,1050,"priced"],[1050,1050,1050,"priced"]]},
    "PCT-06": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":1,"min_population":1},"s":2,"x":[4],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1010,1010,1010,"priced"],[1000,1000,1000,"priced"],[1030,1030,1030,"priced"]]},
    "PCT-07": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[6],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1010,1010,1010,"priced"],[1020,1020,1020,"priced"],[1000,1000,1000,"priced"],[1010,1010,1010,"priced"],[1020,1020,1020,"priced"]]},
    "PCT-08": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"gap"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "PCT-09": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"gap"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "PCT-10": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":0,"x":[7],"a":0,"ev":1000,"abs":["high","low"],"slots":[[null,null,1152921504606846975,"priced"],[null,null,1152921504606846976,"priced"],[null,null,1152921504606846977,"priced"],[null,null,1152921504606846978,"priced"],[null,null,1152921504606846979,"priced"],[null,null,1152921504606846980,"priced"],[null,null,1152921504606846981,"priced"]]},
    "PCT-12": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":2},"s":2,"x":[6],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1010,1010,1010,"priced"],[1000,1000,1000,"priced"],[1030,1030,1030,"priced"],[1000,1000,1000,"priced"],[1050,1050,1050,"priced"]]},
    "PCT-13": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":2},"s":2,"x":[4],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1010,1010,1010,"priced"],[1000,1000,1000,"priced"],[1030,1030,1030,"priced"]]},
    "PCT-11": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"unknown"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "PCT-14": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[9],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"]]},
    "PCT-15": {"p":"band_width_percentile","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"population_size":4,"min_population":4},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"unknown"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "SQ-01": {"p":"bollinger_keltner_squeeze","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "SQ-02": {"p":"bollinger_keltner_squeeze","q":{"band_period":2,"band_k_num":2,"band_k_den":1,"ema_period":1,"atr_period":1,"atr_multiplier_num":1,"atr_multiplier_den":1},"s":0,"x":[6],"a":0,"ev":1000,"slots":[[24,21,21,"priced"],[31,24,29,"priced"],[27,23,27,"priced"],[37,31,36,"priced"],[42,37,39,"priced"],[36,33,35,"priced"]]},
    "SQ-03": {"p":"bollinger_keltner_squeeze","q":{"band_period":2,"band_k_num":1,"band_k_den":1,"ema_period":1,"atr_period":1,"atr_multiplier_num":1,"atr_multiplier_den":2},"s":0,"x":[6],"a":0,"ev":1000,"slots":[[39,36,37,"priced"],[37,31,33,"priced"],[35,28,33,"priced"],[33,31,32,"priced"],[23,21,22,"priced"],[32,26,27,"priced"]]},
    "SQ-10": {"p":"bollinger_keltner_squeeze","q":{"band_period":2,"band_k_num":1,"band_k_den":1,"ema_period":1,"atr_period":1,"atr_multiplier_num":3,"atr_multiplier_den":1},"s":0,"x":[6],"a":0,"ev":1000,"slots":[[26,23,25,"priced"],[42,36,40,"priced"],[28,23,26,"priced"],[41,35,36,"priced"],[30,28,28,"priced"],[28,28,28,"priced"]]},
    "SQ-04": {"p":"bollinger_keltner_squeeze","q":{"band_period":2,"band_k_num":2,"band_k_den":1,"ema_period":2,"atr_period":2,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":0,"x":[6],"a":0,"ev":1000,"slots":[[36,30,33,"priced"],[21,20,21,"priced"],[22,18,22,"priced"],[38,34,37,"priced"],[40,34,38,"priced"],[24,23,23,"priced"]]},
    "SQ-05": {"p":"bollinger_keltner_squeeze","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"],[1000,1000,1000,"priced"]]},
    "SQ-06": {"p":"bollinger_keltner_squeeze","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[3],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"]]},
    "SQ-07": {"p":"bollinger_keltner_squeeze","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"gap"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]},
    "SQ-08": {"p":"bollinger_keltner_squeeze","q":{"band_period":2,"band_k_num":3,"band_k_den":2,"ema_period":2,"atr_period":2,"atr_multiplier_num":1,"atr_multiplier_den":2},"s":0,"x":[6],"a":0,"ev":1000,"slots":[[31,29,30,"priced"],[31,29,30,"priced"],[31,29,30,"priced"],[31,29,30,"priced"],[31,29,30,"priced"],[41,39,40,"priced"]]},
    "SQ-09": {"p":"bollinger_keltner_squeeze","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"future"]]},
    "SQ-11": {"p":"bollinger_keltner_squeeze","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[10],"a":0,"ev":1000,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"]]},
    "SQ-12": {"p":"bollinger_keltner_squeeze","q":{"band_period":3,"band_k_num":2,"band_k_den":1,"ema_period":3,"atr_period":3,"atr_multiplier_num":3,"atr_multiplier_den":2},"s":2,"x":[12],"a":0,"ev":20,"slots":[[1010,990,1000,"priced"],[1030,1000,1020,"priced"],[1040,1010,1030,"priced"],[1050,1020,1040,"priced"],[1045,1015,1025,"priced"],[1035,1005,1015,"priced"],[1020,990,1000,"priced"],[1000,970,985,"priced"],[1010,975,1005,"priced"],[1040,1000,1035,"priced"],[1060,1030,1055,"priced"],[1070,1040,1060,"priced"]]}
}''')
SYNTHETIC_CHANNELS_CASES = tuple(_SYNTHETIC)
_STEP_NS = 10
_VOLUME = 100  # positive volume of every supplied ordinary bar, as the contract fixes it
_KNOWN_NS = 5  # known_at of causal rows


def _case(case_id: str) -> dict[str, Any]:
    if type(case_id) is not str or case_id not in _SYNTHETIC:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic channels case")
    return cast(dict[str, Any], _SYNTHETIC[case_id])


def _session_ids(counts: Sequence[int]) -> list[str]:
    return [f"S{i}" for i in range(len(counts) - 1)] + ["S"]


def synthetic_channels_features(case_id: str) -> tuple[str, ...]:
    """The output ids of the fixture's producer: the complete fixed header set, lexical."""
    return PRODUCER_FEATURES[_case(case_id)["p"]]


def synthetic_channels_config(case_id: str) -> ConfigSpec:
    """Detached synthetic ef2.<producer> config for a contract fixture (reset epoch).

    Entity X in namespace SYN, ten-ns grid of one slot per supplied position. Sessions S0, S1, ... then S
    hold the fixture's slots per session (a single session is S); the anchor is the first slot of the last
    session. The target is the last slot, K = evaluation = the end of the last slot (also the last session
    close), raw basis, USD at the fixture scale. evidence_limit is the fixture's. These grid and entity
    choices are not contract-specified (listed for the worker).
    """
    case = _case(case_id)
    counts = case["x"]
    sessions, runs, cursor = [], [], 0
    for session_id, count in zip(_session_ids(counts), counts):
        sessions.append(SessionSpec("SYN", session_id, cursor * _STEP_NS, (cursor + count) * _STEP_NS, "UTC"))
        runs.append((session_id, cursor * _STEP_NS, _STEP_NS, count))
        cursor += count
    end = cursor * _STEP_NS
    return make_channels_config(
        producer=case["p"], instrument_id="X", calendar_id="synthetic-calendar", grid_id="ten-ns-grid",
        revision="revision1", sessions=sessions, runs=runs, anchor_index=case["a"], target_index=cursor - 1,
        mode="reset", **case["q"], availability=AvailabilitySpec(end, end, end),
        adjustment=AdjustmentSpec(), price_unit=PriceUnit(case["s"], "USD"), evidence_limit=case["ev"])


def synthetic_channels_fixture(case_id: str, *, empty_form: str = "row") -> ChannelsInputs:
    """Original synthetic OHLCV slots of one contract fixture as BAR chunks; nothing is computed.

    One chunk per governed session (bars-000 is the first session; the pivots need the preceding
    session's chunk). priced slots carry volume 100 known at 5. gap is a declared incomplete slot
    without a row (the contract's compact gap values are not supplied); empty (observed-empty) is a
    zero-volume all-null-OHLC row with complete coverage (empty_form="row", default) or complete
    coverage of expected 0 without a row ("coverage"); null is a row with null volume and the listed
    OHLC field null (a positive-volume bar with a null OHLC cell is invalid); future is known after K
    and unknown has known_at null. Columns the fixture lists as absent are omitted from the whole
    delivery and "none" delivery is bars=None.
    """
    if empty_form not in ("row", "coverage"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "empty_form must be row or coverage")
    case = _case(case_id)
    if case.get("none"):
        return ChannelsInputs(None, ("unavailable",))
    counts = case["x"]
    ids = _session_ids(counts)
    absent = set(case.get("abs", ()))
    end_k = sum(counts) * _STEP_NS
    rows: list[list[tuple[Cell, ...]]] = [[] for _ in counts]
    entries: list[list[IntervalCoverage]] = [[] for _ in counts]
    bounds, cursor = [], 0
    for count in counts:
        bounds.append((cursor, cursor + count))
        cursor += count
    for index, (high, low, close, state) in enumerate(case["slots"]):
        start, end = index * _STEP_NS, (index + 1) * _STEP_NS
        part = next(i for i, (first, last) in enumerate(bounds) if first <= index < last)
        row: dict[str, Cell] | None = None
        if state in ("priced", "future", "unknown"):
            known = {"priced": _KNOWN_NS, "future": end_k + 50, "unknown": None}[state]
            row = {"high": high, "low": low, "close": close, "volume": _VOLUME, "known_at_ns": known}
        elif state == "null":
            row = {"high": high, "low": low, "close": close, "volume": None, "known_at_ns": _KNOWN_NS}
        elif state == "empty" and empty_form == "row":
            row = {"high": None, "low": None, "close": None, "volume": 0, "known_at_ns": _KNOWN_NS}
        if row is not None:
            cells = (("instrument_id", "X"), ("session_id", ids[part]), ("start_ns", start),
                     ("end_ns", end), *row.items())
            rows[part].append(tuple(v for k, v in cells if k not in absent))
            entries[part].append(make_slot_coverage(index, start, end, expected=1, observed=1, complete=True))
        elif state == "empty":
            entries[part].append(make_slot_coverage(index, start, end, expected=0, observed=0, complete=True))
        elif state == "gap":
            entries[part].append(make_slot_coverage(index, start, end, expected=1, observed=0, complete=False))
        else:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Unknown compact slot state")
    columns = tuple(c for c in BAR_COLUMNS if c not in absent)
    batches: list[CanonicalBatch] = []
    for part, (first, last) in enumerate(bounds):
        expected = sum(cast(int, e.coverage.expected) for e in entries[part])
        coverage = Coverage(expected, len(rows[part]),
                            all(e.coverage.complete for e in entries[part]) and expected == len(rows[part]))
        metadata = BatchMetadata(
            "SYN", SourceBinding("SYN-BARS", "snap1", MAPPING_VERSION, f"bars-{part:03}"), coverage,
            PriceUnit(case["s"], "USD"), scope=InputScope(first * _STEP_NS, last * _STEP_NS, "synthetic-v1"),
            interval_coverage=tuple(entries[part]))
        batches.append(make_channels_batch(columns, tuple(rows[part]), metadata=metadata))
    return ChannelsInputs(tuple(batches), ("synthetic",))


__all__ += ["SYNTHETIC_CHANNELS_CASES", "synthetic_channels_features", "synthetic_channels_config",
            "synthetic_channels_fixture"]
