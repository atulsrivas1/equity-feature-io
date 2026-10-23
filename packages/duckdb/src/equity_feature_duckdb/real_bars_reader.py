"""Bounded READ-ONLY reader of stored 1-minute bars for the regular BAR price demo.

Opens one existing DuckDB source with ``read_only=True`` and ``threads=1``, runs one
parameterized SELECT for one symbol and one date, and returns canonical inputs with
explicit per-role provenance. It never writes, copies or modifies a source file, makes
no network call and performs no price mathematics. Observed values are converted
losslessly or the call refuses.

Only the BAR role is observed. The calendar, the population-completeness proof and
every original known-at clock are absent from the stored source and are therefore
explicit SYNTHETIC stipulations, labelled as such in the returned provenance. No rights
or original-source parity claim is made.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date as _date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, ConfigSpec, ContractError, Coverage, DataKind, ErrorCode,
    InputScope, PriceUnit, SourceBinding,
)

from .regular_bar_prices import (
    RegularBarPriceInputs, make_regular_bar_population_proof, make_regular_bar_price_batch,
)

_TABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*")
_SYMBOL = re.compile(r"[A-Za-z0-9._-]{1,32}")
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
_TS = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_BAR_NS = 60_000_000_000
_NAMESPACE = "REAL-BARS-DEMO"
_SESSION = "S"
_ADJ = {"action_snapshot": "none", "anchor": "none", "basis": "raw", "policy_version": "raw-v1"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _refuse(message: str) -> ContractError:
    return ContractError(ErrorCode.INVALID_SCHEMA, message)


def _ns(stamp: str) -> int:
    # Second-precision text with trailing Z only; fractional-second rows refuse (coverage narrows).
    if _TS.fullmatch(stamp) is None:
        raise _refuse("Unsupported stored timestamp text")
    moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(moment.timestamp()) * 1_000_000_000


def _coefficient(value: object, scale: int) -> int:
    """Exact integer coefficient of a stored DOUBLE at the declared decimal scale."""
    if type(value) is not float or value != value or value in (float("inf"), float("-inf")):
        raise _refuse("Finite stored price required")
    scaled = Decimal(repr(value)).scaleb(scale)
    if scaled != scaled.to_integral_value():
        raise _refuse("Stored price is not exact at the declared scale")
    return int(scaled)


@dataclass(frozen=True)
class RealRegularBarSource:
    """Canonical inputs, matching config and an auditable provenance summary."""
    inputs: RegularBarPriceInputs
    config: ConfigSpec
    instrument_id: str
    session_id: str
    rows: int
    provenance: Mapping[str, str]
    synthetic_labels: tuple[str, ...]
    observed_fields: tuple[str, ...]


def read_real_regular_bars(database: Path, table: str, symbol: str, date: str, row_cap: int, *,
                           session_open_utc: str = "13:30", session_close_utc: str = "20:00",
                           price_scale: int = 3, currency: str = "USD") -> RealRegularBarSource:
    """Read one symbol/date slice of stored 1-minute bars, read-only and bounded.

    ``session_open_utc`` / ``session_close_utc`` define the SYNTHETIC calendar window;
    only bars whose stored start lies inside it are selected. ``row_cap`` is a hard
    limit: more matching rows than the cap refuses rather than truncating.
    """
    import duckdb
    if (not isinstance(database, Path) or not database.is_absolute() or not database.is_file()
            or type(table) is not str or _TABLE.fullmatch(table) is None
            or type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(date) is not str or type(row_cap) is not int or not 1 <= row_cap <= 5000
            or type(price_scale) is not int or not 0 <= price_scale <= 8
            or type(currency) is not str or not currency.strip()
            or _CLOCK.fullmatch(session_open_utc) is None or _CLOCK.fullmatch(session_close_utc) is None
            or session_open_utc >= session_close_utc):
        raise _refuse("Absolute existing database, schema.table, symbol, ISO date, row cap and UTC window required")
    day = _date.fromisoformat(date)
    iso = day.isoformat()
    open_text, close_text = f"{iso}T{session_open_utc}:00Z", f"{iso}T{session_close_utc}:00Z"
    open_ns, close_ns = _ns(open_text), _ns(close_text)
    connection = duckdb.connect(str(database), read_only=True, config={"threads": 1})
    try:
        stored = connection.execute(
            f"SELECT ts_utc, instrument_id, open, high, low, close, volume FROM {table} "
            "WHERE \"date\" = ? AND symbol = ? AND ts_utc >= ? AND ts_utc < ? ORDER BY ts_utc LIMIT ?",
            [day, symbol, open_text, close_text, row_cap + 1]).fetchall()
    finally:
        connection.close()
    if not stored:
        raise _refuse("No stored bars for the requested symbol/date/window; nothing is invented")
    if len(stored) > row_cap:
        raise ContractError(ErrorCode.BOUNDS, "Matching rows exceed the explicit row cap")
    if len({row[1] for row in stored}) != 1 or len({row[0] for row in stored}) != len(stored):
        raise ContractError(ErrorCode.DUPLICATE, "One instrument and unique bar starts required")
    starts = [_ns(row[0]) for row in stored]
    rows = tuple(
        ("{}".format(symbol), _SESSION, start, start + _BAR_NS,
         _coefficient(row[2], price_scale), _coefficient(row[3], price_scale),
         _coefficient(row[4], price_scale), _coefficient(row[5], price_scale),
         int(row[6]), start + _BAR_NS)
        for start, row in zip(starts, stored))
    names = ("instrument_id", "session_id", "start_ns", "end_ns", "open", "high", "low", "close",
             "volume", "known_at_ns")
    # ``known_at_ns`` is NOT stored in the source: SYNTHETIC stipulation = bar end.
    if starts[-1] + _BAR_NS > close_ns:
        raise ContractError(ErrorCode.BOUNDS, "Bar extends beyond the synthetic regular window")
    unit = PriceUnit(price_scale, currency)
    adjustment = AdjustmentSpec(**_ADJ)
    path_source = SourceBinding(source_id="duckdb-backed:" + table, snapshot_id="unversioned-read-only-view",
                                mapping_version="real-bars-map1", input_id="bars")
    bars = make_regular_bar_price_batch(DataKind.BAR, names, rows, metadata=BatchMetadata(
        namespace=_NAMESPACE, source=path_source, coverage=Coverage(len(rows), len(rows), True),
        price_unit=unit, adjustment=adjustment, sampling="none", quantity_unit="shares",
        ordering="declared", duplicate_policy="reject",
        scope=InputScope(open_ns, close_ns, "supplied_path", False, False), interval_coverage=()))
    calendar = {"calendar_id": "SYNTHETIC-CALENDAR", "early_close": False, "revision": "R1",
                "scheduled_close_ns": close_ns, "segments": [["regular", open_ns, close_ns]],
                "sessions": [[_SESSION, iso, open_ns, close_ns]], "target_date": iso, "timezone": "UTC"}
    context = {"calendar": calendar, "producer": "regular_bar_prices",
               "selection": {"phase_profile": "regular_no_auctions1", "sampling": "completed_bar_close"},
               "version": "ef1-context1"}
    config = ConfigSpec.from_json(_json({
        "adjustment": _ADJ, "algorithm_version": "v1",
        "availability": {"evaluation_ns": close_ns, "knowledge_cutoff_ns": close_ns,
                         "market_cutoff_ns": close_ns, "mode": "known_at", "reconstruction_reason": None},
        "identity": "ef1.regular_bar_prices",
        "parameters": [{"name": "ef1_context_json", "value": _json(context)}],
        "price_unit": {"currency": currency, "scale": price_scale}, "schema_version": "1",
        "session": {"close_ns": close_ns, "early_close": False, "include_closing_auction": False,
                    "include_opening_auction": False, "intervals": [], "namespace": _NAMESPACE,
                    "open_ns": open_ns, "scheduled_close_ns": close_ns, "session_id": _SESSION,
                    "timezone_label": "UTC"},
        "window": {"anchor": "completed_eod", "count": 1, "governed_sessions": [_SESSION],
                   "target_session_id": _SESSION}}))
    calendar_batch = make_regular_bar_price_batch(
        DataKind.REFERENCE,
        ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns",
         "effective_end_ns", "text", "known_at_ns"),
        ((symbol, _SESSION, "c1:" + hashlib.sha256(_json(calendar).encode("ascii")).hexdigest(),
          "ef1.calendar.provenance", open_ns, close_ns, "supplied_schedule", open_ns),),
        metadata=BatchMetadata(
            namespace=_NAMESPACE, source=SourceBinding("SYNTHETIC-CALENDAR", "R1", "ef1-reference-map1", "calendar"),
            coverage=Coverage(1, 1, True), price_unit=None, adjustment=adjustment, sampling="none",
            quantity_unit="shares", ordering="declared", duplicate_policy="reject", scope=None,
            interval_coverage=()))
    proof_source = SourceBinding("SYNTHETIC-POPULATION", "R1", "real-bars-map1", "population")
    projection = hashlib.sha256(_json({
        "version": "ef1-gap-membership-projection1", "kind": "bar",
        "membership_columns": ["instrument_id", "session_id", "start_ns", "end_ns", "volume_present", "volume_class"],
        "rows": [[symbol, _SESSION, row[2], row[3], True, "positive" if row[8] > 0 else "zero"]
                 for row in rows]}).encode("ascii")).hexdigest()
    proof_text = _json({
        "adjustment": _ADJ, "complete": True, "eligibility_policy": "supplied_path", "end_ns": close_ns,
        "include_closing_auction": False, "include_opening_auction": False, "instrument_id": symbol,
        "knowledge_cutoff_ns": close_ns, "market_cutoff_ns": close_ns, "namespace": _NAMESPACE,
        "path_source": {"input_id": path_source.input_id, "mapping_version": path_source.mapping_version,
                        "snapshot_id": path_source.snapshot_id, "source_id": path_source.source_id},
        "phase_profile": "regular_no_auctions1", "population_sha256": projection,
        "price_unit": {"currency": currency, "scale": price_scale}, "producer": "regular_bar_prices",
        "profile_id": "regular-bar-membership-asof1",
        "proof_source": {"input_id": proof_source.input_id, "mapping_version": proof_source.mapping_version,
                         "snapshot_id": proof_source.snapshot_id, "source_id": proof_source.source_id},
        "row_count": len(rows), "sampling": "completed_bar_close", "session_id": _SESSION,
        "start_ns": open_ns, "version": "ef1-regular-bar-population1"})
    proof = make_regular_bar_population_proof({
        "instrument_id": symbol, "session_id": _SESSION,
        "reference_id": "rbp1:" + hashlib.sha256(proof_text.encode("ascii")).hexdigest(),
        "fact_kind": "ef1.regular_bar.population.v1", "effective_start_ns": open_ns,
        "effective_end_ns": close_ns, "text": proof_text, "known_at_ns": close_ns},
        metadata=BatchMetadata(
            namespace=_NAMESPACE, source=proof_source, coverage=Coverage(1, 1, True), price_unit=None,
            adjustment=adjustment, sampling="none", quantity_unit="shares", ordering="declared",
            duplicate_policy="reject", scope=None, interval_coverage=()))
    inputs = RegularBarPriceInputs(calendar_batch, bars, proof,
                                   provenance=("synthetic", "duckdb_backed_observed", "synthetic"))
    return RealRegularBarSource(
        inputs=inputs, config=config, instrument_id=symbol, session_id=_SESSION, rows=len(rows),
        provenance={"calendar_provenance": "synthetic", "bars": "duckdb_backed_observed",
                    "population_proof": "synthetic"},
        synthetic_labels=("calendar (session window and revision)", "population-completeness proof",
                          "bar known-at clocks (stipulated equal to bar end)", "knowledge/market cutoff (session close)",
                          "bar duration (60 s from the stored 1-minute schema)", "currency and raw adjustment declaration"),
        observed_fields=("instrument symbol", "bar start timestamp", "open", "high", "low", "close", "volume"))


__all__ = ["RealRegularBarSource", "read_real_regular_bars"]
