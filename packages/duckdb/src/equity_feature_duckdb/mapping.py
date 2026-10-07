"""Explicit owned retained-source mapping; no I/O or inferred source admission."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
import hashlib
import json
import re
from typing import cast

from equity_feature_contracts import (
    BatchMetadata, CanonicalBatch, Column, ContractError, DataKind, PriceUnit,
    quantize_float_prices, validate_batch,
)
from equity_feature_contracts.inputs import I64_MIN, I64_MAX
from .resolver import _count, _fail, _text
from equity_feature_contracts.adapters import SourceErrorCode


def parse_utc_ns(value: object) -> int:
    """Exact int64 ns or lexical UTC ISO timestamp; no float epoch conversion."""
    if type(value) is int:
        if not I64_MIN <= value <= I64_MAX:
            _fail("Timestamp outside int64")
        return value
    if type(value) is not str:
        _fail("Exact UTC timestamp required")
    match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2})[T ]([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?(?:Z|\+00:00)", value)
    if match is None:
        _fail("Exact UTC timestamp required")
    try:
        days = (date.fromisoformat(match[1]) - date(1970, 1, 1)).days
    except ValueError:
        _fail("Invalid UTC calendar date")
    hour, minute, second = (int(match[i]) for i in (2, 3, 4))
    if hour > 23 or minute > 59 or second > 59:
        _fail("Invalid UTC time")
    fraction = int((match[5] or "").ljust(9, "0"))
    result = ((days * 24 + hour) * 3600 + minute * 60 + second) * 10**9 + fraction
    if not I64_MIN <= result <= I64_MAX:
        _fail("Timestamp outside int64")
    return result


@dataclass(frozen=True)
class MappingPolicy:
    source_schema: str
    price_unit: PriceUnit
    interpretation: str
    rounding: str
    instrument_ids: tuple[tuple[int, str], ...]
    source_clock: str
    eligibility_policy: str | None = None
    eligible_default: bool | None = None
    max_rows: int = 10000

    def __post_init__(self) -> None:
        if self.source_schema not in ("trades", "tbbo", "ohlcv-1m", "ohlcv-1d"):
            _fail("Unsupported retained schema", SourceErrorCode.UNSUPPORTED)
        if type(self.price_unit) is not PriceUnit or self.interpretation not in ("binary64_exact", "decimal_repr") or self.rounding not in ("exact", "half_even"):
            _fail("Explicit unit and price conversion policies required")
        expected_clock = "event" if self.source_schema in ("trades", "tbbo") else "receive_aggregation"
        if self.source_clock != expected_clock:
            _fail("Explicit compatible source clock required", SourceErrorCode.UNSUPPORTED)
        if type(self.instrument_ids) not in (tuple, list) or not self.instrument_ids:
            _fail("Concrete instrument identity mapping required")
        pairs: list[tuple[int, str]] = []
        for pair in self.instrument_ids:
            if type(pair) not in (tuple, list) or len(pair) != 2:
                _fail("Explicit source/canonical instrument pair required")
            pairs.append((_count(pair[0]), _text(pair[1])))
        if len({a for a, _ in pairs}) != len(pairs) or len({b for _, b in pairs}) != len(pairs):
            _fail("Unique source/canonical instruments required")
        object.__setattr__(self, "instrument_ids", tuple(pairs))
        _count(self.max_rows, positive=True)
        if self.eligibility_policy is not None:
            _text(self.eligibility_policy)
        if self.eligible_default is not None and (type(self.eligible_default) is not bool or self.eligibility_policy is None):
            _fail("Governed Boolean eligibility assertion required")


@dataclass(frozen=True)
class RowOccurrence:
    source_token: str
    original_row: int
    order_key: int

    def __post_init__(self) -> None:
        _text(self.source_token)
        _count(self.original_row)
        _count(self.order_key)

    @property
    def event_id(self) -> str:
        payload = json.dumps([self.source_token, self.original_row], separators=(",", ":"))
        return "occurrence:" + hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class PriceConversion:
    field: str
    interpretation: str
    rounding: str
    rounded_cells: int


@dataclass(frozen=True)
class MappingReport:
    version: str
    digest: str
    rows: int
    price_conversions: tuple[PriceConversion, ...]
    unmapped_fields: tuple[str, ...]
    interval_clock: str
    eligibility_policy: str | None
    eligibility_source: str


@dataclass(frozen=True)
class MappedSource:
    batch: CanonicalBatch
    report: MappingReport


def map_columns(policy: MappingPolicy, columns: dict[str, tuple[object, ...] | list[object]], *,
                metadata: BatchMetadata, occurrences: tuple[RowOccurrence, ...],
                sessions: tuple[str, ...]) -> MappedSource:
    """Map a bounded concrete population. Caller supplies sessions/source evidence."""
    if type(policy) is not MappingPolicy or type(metadata) is not BatchMetadata or type(columns) is not dict:
        _fail("Concrete typed mapping input required")
    if any(type(k) is not str or type(v) not in (tuple, list) for k, v in columns.items()):
        _fail("Concrete named source columns required")
    for key in columns:
        _text(key)
    if "ts_utc" not in columns or "instrument_id" not in columns:
        _fail("Source time and instrument columns required")
    lengths = {len(v) for v in columns.values()}
    if len(lengths) != 1:
        _fail("Equal source column lengths required")
    rows = len(columns["ts_utc"])
    if rows > policy.max_rows:
        _fail("Mapping row limit exceeded", SourceErrorCode.LIMIT)
    if type(occurrences) not in (tuple, list) or len(occurrences) != rows or any(type(x) is not RowOccurrence for x in occurrences):
        _fail("One typed occurrence per row required")
    if len({x.event_id for x in occurrences}) != rows:
        _fail("Duplicate original occurrence")
    if type(sessions) not in (tuple, list) or len(sessions) != rows:
        _fail("One explicit session per row required")
    for session in sessions:
        _text(session)
    if metadata.price_unit != policy.price_unit:
        _fail("Mapping price unit conflicts with metadata")
    if metadata.adjustment.basis != "raw":
        _fail("Retained mapping supports raw inputs only", SourceErrorCode.UNSUPPORTED)
    if metadata.scope is not None and policy.eligibility_policy is not None and metadata.scope.eligibility_policy != policy.eligibility_policy:
        _fail("Eligibility policy conflicts with supplied scope")
    kind = {"trades": DataKind.TRADE, "tbbo": DataKind.QUOTE, "ohlcv-1m": DataKind.BAR, "ohlcv-1d": DataKind.DAILY}[policy.source_schema]
    if metadata.sampling != ("trade_snapshot" if kind == DataKind.QUOTE else "none"):
        _fail("Unsupported retained sampling", SourceErrorCode.UNSUPPORTED)
    try:
        ids = dict(policy.instrument_ids)
        instruments = tuple(ids[_count(x)] for x in columns["instrument_id"])
    except KeyError:
        _fail("Unmapped source instrument", SourceErrorCode.UNAVAILABLE)
    times = tuple(parse_utc_ns(x) for x in columns["ts_utc"])
    output = [Column("instrument_id", instruments), Column("session_id", tuple(sessions))]
    used = {"ts_utc", "instrument_id"}
    eligibility_source = "not_applicable"
    clock = "event"
    if kind in (DataKind.TRADE, DataKind.QUOTE):
        output += [Column("event_ns", times), Column("order_key", tuple(x.order_key for x in occurrences)),
                   Column("event_id", tuple(x.event_id for x in occurrences))]
        if kind == DataKind.TRADE:
            if policy.eligibility_policy is None:
                _fail("Trade eligibility evidence unavailable", SourceErrorCode.UNAVAILABLE)
            if "eligible" in columns:
                if policy.eligible_default is not None or any(type(x) is not bool for x in columns["eligible"]):
                    _fail("Unambiguous Boolean eligibility required")
                eligible = cast(tuple[bool, ...], tuple(columns["eligible"]))
                used.add("eligible")
                eligibility_source = "column"
            elif policy.eligible_default is not None:
                eligible = (policy.eligible_default,) * rows
                eligibility_source = "caller_assertion"
            else:
                _fail("Trade eligibility evidence unavailable", SourceErrorCode.UNAVAILABLE)
            output.append(Column("eligible", eligible))
    else:
        interval = (60 if kind == DataKind.BAR else 86400) * 10**9
        if any(x % interval != 0 or x > I64_MAX - interval for x in times):
            _fail("Whole UTC source intervals required")
        output += [Column("start_ns", times), Column("end_ns", tuple(x + interval for x in times))]
        clock = "receive_aggregation_UTC_minute" if kind == DataKind.BAR else "receive_aggregation_UTC_day"
    price_names = ("price",) if kind == DataKind.TRADE else ("bid", "ask") if kind == DataKind.QUOTE else ("open", "high", "low", "close")
    integer_names = ("size",) if kind == DataKind.TRADE else ("bid_size", "ask_size") if kind == DataKind.QUOTE else ("volume",)
    conversions: list[PriceConversion] = []
    try:
        for name in price_names:
            if name not in columns:
                continue
            converted = quantize_float_prices(cast(tuple[float | None, ...], tuple(columns[name])),
                unit=policy.price_unit, interpretation=policy.interpretation, rounding=policy.rounding)
            output.append(Column(name, converted.values))
            used.add(name)
            conversions.append(PriceConversion(name, converted.interpretation, converted.rounding, converted.rounded_cells))
        for name in integer_names:
            if name in columns:
                output.append(Column(name, tuple(None if x is None else _count(x) for x in columns[name])))
                used.add(name)
        if kind == DataKind.TRADE and "condition" in columns:
            if any(x is not None and type(x) is not str for x in columns["condition"]):
                _fail("String trade condition required")
            output.append(Column("condition", cast(tuple[str | None, ...], tuple(columns["condition"]))))
            used.add("condition")
        if "known_at_ns" in columns:
            output.append(Column("known_at_ns", tuple(None if x is None else parse_utc_ns(x) for x in columns["known_at_ns"])))
            used.add("known_at_ns")
        payload = dict(version="retained-map1", policy=asdict(policy), columns=[asdict(x) for x in output],
                       metadata=asdict(metadata), occurrences=[asdict(x) for x in occurrences],
                       unmapped_fields=sorted(set(columns)-used), clock=clock, eligibility_source=eligibility_source)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        source = replace(metadata.source, mapping_version=metadata.source.mapping_version+":retained-map1:"+digest,
                         input_id=metadata.source.input_id+":mapped:"+digest)
        batch = CanonicalBatch(kind, tuple(output), replace(metadata, source=source))
        validate_batch(batch)
    except ContractError:
        _fail("Canonical mapping admission failed")
    report = MappingReport("retained-map1", digest, rows, tuple(conversions), tuple(sorted(set(columns)-used)),
                           clock, policy.eligibility_policy, eligibility_source)
    return MappedSource(batch, report)
