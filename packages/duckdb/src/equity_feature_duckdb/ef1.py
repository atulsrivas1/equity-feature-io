"""Explicit EF1 canonical source composition; no acquisition or feature mathematics.

Synthetic fixtures are original public examples. Supplying canonical observations
does not authenticate their origin, coverage, calendar, availability or rights.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import cast

from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, CanonicalBatch, Column, ContractError, Coverage,
    DataKind, ErrorCode, InputScope, PriceUnit, SourceBinding, validate_batch,
)
from equity_feature_contracts.inputs import Cell, I64_MAX, I64_MIN

_DEFINITION_KEYS = frozenset(("anchor_id", "reset_id", "start_ns", "selection_policy_id", "revision"))
_MODES = frozenset(("duckdb_backed_observed", "synthetic", "unavailable"))
_CALENDAR_KEYS = frozenset(("calendar_id", "revision", "timezone", "target_date", "sessions",
                            "segments", "scheduled_close_ns", "early_close"))


def _label(value: object) -> str:
    if (type(value) is not str or not value.strip() or len(value) > 128
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
            or len(value.encode("utf-8")) > 512):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Bounded EF1 identity required")
    return value


def _ns(value: object) -> int:
    if type(value) is not int or not I64_MIN <= value <= I64_MAX:
        raise ContractError(ErrorCode.BOUNDS, "Exact int64 UTC nanoseconds required")
    return value


def anchor_definition_bytes(definition: Mapping[str, object]) -> bytes:
    """Freeze the contract's exact definition; no acquired evidence in this object."""
    if not isinstance(definition, Mapping) or set(definition) != _DEFINITION_KEYS:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact EF1 anchor definition required")
    owned = dict(definition)
    for key in _DEFINITION_KEYS - {"start_ns"}:
        _label(owned[key])
    _ns(owned["start_ns"])
    return json.dumps(owned, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def make_anchor_provenance(
    definition: Mapping[str, object], *, namespace: str, instrument_id: str,
    session_id: str, source_id: str, input_id: str, known_at_ns: int | None,
    end_ns: int | None = None,
) -> CanonicalBatch:
    """Convert an explicitly supplied anchor declaration into its real REF row.

    This constructor preserves null/original known-at. It neither discovers an
    anchor nor certifies authority; callers must not invent declaration evidence.
    """
    encoded = anchor_definition_bytes(definition)
    start = _ns(definition["start_ns"])
    if known_at_ns is not None:
        _ns(known_at_ns)
    if end_ns is not None and _ns(end_ns) <= start:
        raise ContractError(ErrorCode.BOUNDS, "Positive anchor validity interval required")
    for value in (namespace, instrument_id, session_id, source_id, input_id):
        _label(value)
    source = SourceBinding(source_id, str(definition["revision"]), "ef1-reference-map1", input_id)
    columns = (
        Column("instrument_id", (instrument_id,)), Column("session_id", (session_id,)),
        Column("reference_id", ("a1:" + hashlib.sha256(encoded).hexdigest(),)),
        Column("fact_kind", ("ef1.anchor.provenance",)),
        Column("effective_start_ns", (start,)), Column("effective_end_ns", (end_ns,)),
        Column("text", ("supplied_anchor",)), Column("known_at_ns", (known_at_ns,)),
    )
    result = CanonicalBatch(DataKind.REFERENCE, columns,
                            BatchMetadata(namespace, source, Coverage(1, 1, True), None))
    validate_batch(result)
    return result


@dataclass(frozen=True)
class AnchorInputs:
    """Explicit market/proof slots, including missing and covered-empty delivery."""
    mode: str
    market: CanonicalBatch | None
    anchor_provenance: CanonicalBatch | None
    market_provenance: str
    anchor_provenance_mode: str

    def __post_init__(self) -> None:
        if type(self.mode) is not str or self.mode not in ("trades", "bars_actual_notional"):
            raise ContractError(ErrorCode.UNSUPPORTED_SAMPLING, "Supported EF1 anchor sampling required")
        kind = DataKind.TRADE if self.mode == "trades" else DataKind.BAR
        for batch, provenance, expected in (
            (self.market, self.market_provenance, kind),
            (self.anchor_provenance, self.anchor_provenance_mode, DataKind.REFERENCE),
        ):
            if type(provenance) is not str or provenance not in _MODES or (batch is None) != (provenance == "unavailable"):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Explicit source mode must match delivery")
            if batch is not None:
                if type(batch) is not CanonicalBatch or batch.kind != expected:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Canonical role kind mismatch")
                validate_batch(batch)
        if self.market is not None and self.anchor_provenance is not None:
            if (self.market.metadata.namespace != self.anchor_provenance.metadata.namespace
                    or self.market.metadata.source.input_id == self.anchor_provenance.metadata.source.input_id):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Distinct actual canonical bindings required")

    @property
    def roles(self) -> tuple[str, str]:
        return ("trades" if self.mode == "trades" else "bars", "anchor_provenance")

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in (self.market, self.anchor_provenance) if batch is not None)


def synthetic_anchor_fixture(case_id: str = "A01", *, mode: str = "trades") -> AnchorInputs:
    """Literal ef1-contract1 A01/A02 inputs; no calculated output oracle here.

    A01-missing-notional is the frozen A01 bars subcase. A03 deliberately has no
    packet: its zero-duration request must fail before constructing InputScope.
    """
    if case_id == "A03":
        raise ContractError(ErrorCode.BOUNDS, "Anchor must precede cutoff; no zero-duration source scope")
    if case_id not in ("A01", "A02", "A01-missing-notional"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown synthetic fixture")
    if mode not in ("trades", "bars_actual_notional") or (
            case_id == "A01-missing-notional" and mode != "bars_actual_notional"):
        raise ContractError(ErrorCode.UNSUPPORTED_SAMPLING, "Fixture sampling mismatch")
    definition = {"anchor_id": "A", "reset_id": "R", "start_ns": 10,
                  "selection_policy_id": "supplied-v1", "revision": "R1"}
    proof = make_anchor_provenance(definition, namespace="SYN", instrument_id="X", session_id="S",
                                   source_id="F", input_id="synthetic-proof-" + case_id,
                                   known_at_ns=10)
    rows: tuple[tuple[Cell, ...], ...]
    names: tuple[str, ...]
    if mode == "trades":
        names = ("event_ns", "order_key", "event_id", "eligible", "price", "size", "known_at_ns")
        rows = () if case_id == "A02" else ((10, 0, "a", True, 1000, 2, 10), (15, 1, "b", True, 1300, 1, 15))
        kind = DataKind.TRADE
    else:
        names = ("start_ns", "end_ns", "open", "high", "low", "close", "volume", "actual_notional", "known_at_ns")
        notional = None if case_id == "A01-missing-notional" else 3300
        rows = () if case_id == "A02" else ((10, 20, 1000, 1300, 1000, 1300, 3, notional, 20),)
        kind = DataKind.BAR
    count = len(rows)
    columns = (Column("instrument_id", ("X",) * count), Column("session_id", ("S",) * count)) + tuple(
        Column(name, tuple(row[index] for row in rows)) for index, name in enumerate(names))
    source = SourceBinding("F", "R1", "ef1-reference-map1", "synthetic-market-" + case_id + "-" + mode)
    metadata = BatchMetadata("SYN", source, Coverage(count, count, True), PriceUnit(2, "USD"),
                             AdjustmentSpec(), scope=InputScope(10, 20, "synthetic-explicit-eligibility"))
    return AnchorInputs(mode, CanonicalBatch(kind, columns, metadata), proof, "synthetic", "synthetic")


def separate_output_path(output_path: Path, source_paths: tuple[Path, ...]) -> Path:
    """Resolve caller paths and reject aliases before constructing any sink.

    Does not create/open a database. Callers still qualify local filesystem,
    destination branding, leases and rights through the existing sink contract.
    """
    if not isinstance(output_path, Path) or not output_path.is_absolute() or type(source_paths) is not tuple:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Absolute output and concrete source paths required")
    if any(not isinstance(path, Path) or not path.is_absolute() for path in source_paths):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Absolute source paths required")
    try:
        output = output_path.resolve()
        for source in source_paths:
            original = source.resolve()
            if output == original or (output.exists() and original.exists() and output.samefile(original)):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Output destination aliases an input source")
        return output
    except OSError:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Source/destination path resolution failed") from None


def _calendar_document(calendar: Mapping[str, object]) -> tuple[dict[str, object], tuple[tuple[int, int], ...]]:
    """Validate and detach only the supplied schedule; never infer calendar facts."""
    if not isinstance(calendar, Mapping) or set(calendar) != _CALENDAR_KEYS:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact EF1 calendar definition required")
    owned = dict(calendar)
    for key in ("calendar_id", "revision", "timezone"):
        _label(owned[key])
    target_date = _calendar_date(owned["target_date"])
    sessions = _calendar_rows(owned["sessions"], width=4, maximum=64)
    segments = _calendar_rows(owned["segments"], width=3, maximum=3)
    session_rows: list[list[Cell]] = []
    segment_rows: list[list[Cell]] = []
    bounds: list[tuple[int, int]] = []
    identifiers: set[str] = set()
    target_bounds: tuple[int, int] | None = None
    previous_end: int | None = None
    previous_date: str | None = None
    for row in sessions:
        identifier, civil_date = _label(row[0]), _calendar_date(row[1])
        start, end = _ns(row[2]), _ns(row[3])
        if (start >= end or (previous_end is not None and start < previous_end)
                or (previous_date is not None and civil_date < previous_date)):
            raise ContractError(ErrorCode.INVALID_ORDER, "Ordered disjoint supplied sessions required")
        if identifier in identifiers:
            raise ContractError(ErrorCode.DUPLICATE, "Duplicate supplied session identity")
        identifiers.add(identifier)
        if civil_date == target_date:
            if target_bounds is not None:
                raise ContractError(ErrorCode.DUPLICATE, "Ambiguous supplied target date")
            target_bounds = (start, end)
        session_rows.append([identifier, civil_date, start, end])
        bounds.append((start, end))
        previous_end, previous_date = end, civil_date
    previous_end = None
    phases: set[str] = set()
    previous_phase = -1
    regular: tuple[int, int] | None = None
    for row in segments:
        phase = _label(row[0])
        start, end = _ns(row[1]), _ns(row[2])
        if phase not in ("premarket", "regular", "postmarket") or phase in phases:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Unique declared calendar phase required")
        phase_order = ("premarket", "regular", "postmarket").index(phase)
        if phase_order <= previous_phase:
            raise ContractError(ErrorCode.INVALID_ORDER, "Declared calendar phase order required")
        if start >= end or (previous_end is not None and start < previous_end):
            raise ContractError(ErrorCode.INVALID_ORDER, "Ordered disjoint supplied segments required")
        phases.add(phase)
        if phase == "regular":
            regular = (start, end)
        segment_rows.append([phase, start, end])
        bounds.append((start, end))
        previous_end = end
        previous_phase = phase_order
    scheduled = _ns(owned["scheduled_close_ns"])
    early = owned["early_close"]
    if regular is None or target_bounds != regular or type(early) is not bool or scheduled < regular[1] or early != (regular[1] < scheduled):
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Supplied target schedule operands disagree")
    owned["sessions"], owned["segments"] = session_rows, segment_rows
    return owned, tuple(bounds)


def _calendar_rows(value: object, *, width: int, maximum: int) -> tuple[tuple[object, ...], ...]:
    if type(value) not in (list, tuple):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete supplied calendar rows required")
    rows = cast(list[object] | tuple[object, ...], value)
    if not 1 <= len(rows) <= maximum:
        raise ContractError(ErrorCode.BOUNDS, "Supplied calendar row bound exceeded")
    owned: list[tuple[object, ...]] = []
    for row in rows:
        if type(row) not in (list, tuple):
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete supplied calendar row required")
        cells = cast(list[object] | tuple[object, ...], row)
        if len(cells) != width:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied calendar row width required")
        owned.append(tuple(cells))
    return tuple(owned)


def _calendar_date(value: object) -> str:
    label = _label(value)
    try:
        parsed = date.fromisoformat(label)
    except ValueError:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Explicit ISO calendar date required") from None
    if parsed.isoformat() != label:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Canonical ISO calendar date required")
    return label


def calendar_definition_bytes(calendar: Mapping[str, object]) -> bytes:
    """Exact canonical ASCII calendar bytes, including early/scheduled-close facts."""
    owned, _ = _calendar_document(calendar)
    encoded = json.dumps(owned, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(encoded) > 4096:
        raise ContractError(ErrorCode.BOUNDS, "EF1 calendar exceeds context byte bound")
    return encoded


def make_calendar_provenance(
    calendar: Mapping[str, object], *, namespace: str, instrument_id: str,
    session_id: str, source_id: str, input_id: str, known_at_ns: int | None,
    start_ns: int, end_ns: int,
) -> CanonicalBatch:
    """Map an actual supplied schedule declaration without inventing availability."""
    owned, bounds = _calendar_document(calendar)
    encoded = calendar_definition_bytes(owned)
    start, end = _ns(start_ns), _ns(end_ns)
    if start >= end or any(start > lower or end < upper for lower, upper in bounds):
        raise ContractError(ErrorCode.BOUNDS, "Calendar proof must cover all supplied schedule bounds")
    if known_at_ns is not None:
        _ns(known_at_ns)
    for value in (namespace, instrument_id, session_id, source_id, input_id):
        _label(value)
    sessions = _calendar_rows(owned["sessions"], width=4, maximum=64)
    if not any(row[0] == session_id and row[1] == owned["target_date"] for row in sessions):
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Calendar proof target session mismatch")
    columns = (
        Column("instrument_id", (instrument_id,)), Column("session_id", (session_id,)),
        Column("reference_id", ("c1:" + hashlib.sha256(encoded).hexdigest(),)),
        Column("fact_kind", ("ef1.calendar.provenance",)), Column("text", ("supplied_schedule",)),
        Column("effective_start_ns", (start,)), Column("effective_end_ns", (end,)),
        Column("known_at_ns", (known_at_ns,)),
    )
    source = SourceBinding(source_id, _label(owned["revision"]), "ef1-reference-map1", input_id)
    result = CanonicalBatch(DataKind.REFERENCE, columns,
                            BatchMetadata(namespace, source, Coverage(1, 1, True), None))
    validate_batch(result)
    return result


@dataclass(frozen=True)
class ClockInputs:
    """One actual calendar-proof slot or explicit missing delivery, no fallback."""
    calendar_provenance: CanonicalBatch | None
    provenance: str

    def __post_init__(self) -> None:
        if type(self.provenance) is not str or self.provenance not in _MODES or (self.calendar_provenance is None) != (self.provenance == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Explicit clock source mode must match delivery")
        if self.calendar_provenance is not None:
            if type(self.calendar_provenance) is not CanonicalBatch or self.calendar_provenance.kind != DataKind.REFERENCE:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Canonical calendar reference required")
            validate_batch(self.calendar_provenance)

    @property
    def roles(self) -> tuple[str, ...]:
        return ("calendar_provenance",)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return () if self.calendar_provenance is None else (self.calendar_provenance,)


def synthetic_clock_calendar() -> dict[str, object]:
    """Original finite C01 schedule; return a fresh owned definition on each call."""
    return {"calendar_id": "C01", "revision": "R1", "timezone": "UTC", "target_date": "2026-01-02",
            "sessions": [["S", "2026-01-02", 10, 30]],
            "segments": [["premarket", 0, 10], ["regular", 10, 30], ["postmarket", 30, 40]],
            "scheduled_close_ns": 40, "early_close": True}


def synthetic_clock_fixture(*, known_at_ns: int | None = 5) -> ClockInputs:
    """C01's original explicit synthetic proof; no clock calculation or time lookup."""
    proof = make_calendar_provenance(synthetic_clock_calendar(), namespace="SYN", instrument_id="X",
        session_id="S", source_id="F", input_id="synthetic-clock-C01", known_at_ns=known_at_ns,
        start_ns=0, end_ns=40)
    return ClockInputs(proof, "synthetic")


__all__ = ["AnchorInputs", "anchor_definition_bytes", "make_anchor_provenance",
           "separate_output_path", "synthetic_anchor_fixture", "ClockInputs",
           "calendar_definition_bytes", "make_calendar_provenance", "synthetic_clock_calendar",
           "synthetic_clock_fixture"]

# Status conversion is additive. Existing anchor/calendar source behavior above
# deliberately remains unchanged.
from base64 import urlsafe_b64decode, urlsafe_b64encode

_STATUS_ROLES = ("calendar_provenance", "status_states", "status_prefix", "status_validity")
_STATUS_DIMENSIONS = {"trading": ("t", ("active", "halted", "closed")),
                      "quoting": ("q", ("enabled", "disabled")), "ssr": ("s", ("on", "off"))}


def _status_label(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Nonempty exact status identity required")
    if (len(value) > 128 or len(value.encode("utf-8", errors="surrogatepass")) > 512
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ContractError(ErrorCode.BOUNDS, "Unsafe or over-limit status identity")
    return value


def _status_b64(value: str) -> str:
    return urlsafe_b64encode(_status_label(value).encode("utf-8")).decode("ascii").rstrip("=")


def _status_unb64(token: str) -> str:
    if not token or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in token):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Canonical unpadded base64url required")
    try:
        raw = urlsafe_b64decode(token + "=" * ((-len(token)) % 4))
        value = raw.decode("utf-8")
    except (ValueError, UnicodeError):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Invalid UTF8 base64url identity") from None
    if urlsafe_b64encode(raw).decode("ascii").rstrip("=") != token:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Noncanonical base64url identity")
    return _status_label(value)


def _status_dimension(dimension: str) -> str:
    if type(dimension) is not str or dimension not in _STATUS_DIMENSIONS:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Closed status dimension required")
    return _STATUS_DIMENSIONS[dimension][0]


@dataclass(frozen=True)
class StatusState:
    """One original publisher event; sequence and knowledge are never generated."""
    sequence: int
    event_id: str
    effective_start_ns: int
    effective_end_ns: int | None
    text: str
    known_at_ns: int | None


@dataclass(frozen=True)
class StatusCertificate:
    """An actual supplied complete-prefix or validity declaration."""
    certificate_id: str
    effective_start_ns: int
    effective_end_ns: int
    known_at_ns: int | None


def _status_reference(rows: tuple[tuple[Cell, ...], ...], *, metadata: BatchMetadata,
                      instrument_id: str, session_id: str) -> CanonicalBatch:
    _status_label(instrument_id)
    _status_label(session_id)
    names = ("reference_id", "fact_kind", "effective_start_ns", "effective_end_ns", "text", "known_at_ns")
    count = len(rows)
    if count > 4096:
        raise ContractError(ErrorCode.BOUNDS, "Status REFERENCE row bound exceeded")
    columns = (Column("instrument_id", (instrument_id,) * count),
               Column("session_id", (session_id,) * count)) + tuple(
        Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    batch = CanonicalBatch(DataKind.REFERENCE, columns, metadata)
    validate_batch(batch)
    return batch


def make_status_states(rows: tuple[StatusState, ...], *, dimension: str, epoch: str,
                       metadata: BatchMetadata, instrument_id: str, session_id: str) -> CanonicalBatch:
    """Map supplied state events in original order with explicit caller coverage.

    A sequence gap conveys no completeness. Unknown/future known-at survives.
    This factory performs no selection, cutoff filtering or status mathematics.
    """
    code = _status_dimension(dimension)
    encoded_epoch = _status_b64(epoch)
    if type(rows) is not tuple or any(type(row) is not StatusState for row in rows):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete original status events required")
    mapped: list[tuple[Cell, ...]] = []
    for row in rows:
        if type(row.sequence) is not int or not 0 <= row.sequence <= I64_MAX:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact nonnegative int64 sequence required")
        reference = _status_label(f"s1:{code}:{encoded_epoch}:{row.sequence:019d}:{_status_b64(row.event_id)}")
        mapped.append((reference, "ef1.status." + dimension, row.effective_start_ns,
                       row.effective_end_ns, row.text, row.known_at_ns))
    batch = _status_reference(tuple(mapped), metadata=metadata,
                              instrument_id=instrument_id, session_id=session_id)
    _status_validate_role(batch, "status_states")
    return batch


def make_status_proof(rows: tuple[StatusCertificate, ...], *, role: str, dimension: str,
                      epoch: str, target_input_id: str, metadata: BatchMetadata,
                      instrument_id: str, session_id: str) -> CanonicalBatch:
    """Map original dedicated proof declarations, never infer proof population."""
    if role not in ("status_prefix", "status_validity"):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Dedicated status proof role required")
    code = _status_dimension(dimension)
    encoded_epoch, target = _status_b64(epoch), _status_b64(target_input_id)
    if type(rows) is not tuple or any(type(row) is not StatusCertificate for row in rows):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Concrete original certificates required")
    kind = "ef1.status." + ("prefix_complete" if role == "status_prefix" else "validity")
    mapped: list[tuple[Cell, ...]] = []
    for row in rows:
        reference = _status_label(f"p1:{code}:{encoded_epoch}:{target}:{_status_b64(row.certificate_id)}")
        mapped.append((reference, kind, row.effective_start_ns, row.effective_end_ns, code, row.known_at_ns))
    batch = _status_reference(tuple(mapped), metadata=metadata,
                              instrument_id=instrument_id, session_id=session_id)
    _status_validate_role(batch, role)
    return batch


def _status_validate_role(batch: CanonicalBatch, role: str) -> tuple[set[tuple[str, str]], set[str]]:
    """Validate conversion identity only; semantic certificate admission is pure-core work."""
    if batch.row_count > 4096:
        raise ContractError(ErrorCode.BOUNDS, "Status REFERENCE row bound exceeded")
    if batch.metadata.coverage.observed != batch.row_count:
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Actual observed count must match original rows")
    validate_batch(batch)
    if batch.kind != DataKind.REFERENCE:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Status slots require canonical REFERENCE")
    source = batch.metadata.source
    for value in (batch.metadata.namespace, source.source_id, source.snapshot_id, source.input_id):
        _status_label(value)
    if source.mapping_version != "ef1-reference-map1":
        raise ContractError(ErrorCode.INCOMPATIBLE_VERSION, "Exact EF1 reference mapping required")
    columns = {column.name: column.values for column in batch.columns}
    if any(name in columns for name in ("price", "factor_num", "factor_den")):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Status references have no numerical payload")
    identities: set[tuple[str, str]] = set()
    targets: set[str] = set()
    previous: int | None = None
    previous_start: int | None = None
    texts = columns.get("text", (None,) * batch.row_count)
    ends = columns.get("effective_end_ns", (None,) * batch.row_count)
    for i in range(batch.row_count):
        for name in ("instrument_id", "session_id", "reference_id"):
            _status_label(columns[name][i])
        if role == "calendar_provenance":
            if columns["fact_kind"][i] != "ef1.calendar.provenance" or texts[i] != "supplied_schedule":
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Calendar role vocabulary required")
            continue
        reference = cast(str, columns["reference_id"][i])
        parts = reference.split(":")
        if len(parts) != 5 or parts[1] not in ("t", "q", "s"):
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Closed status identity grammar required")
        code, epoch = parts[1], _status_unb64(parts[2])
        identities.add((code, epoch))
        start = _ns(columns["effective_start_ns"][i])
        end = ends[i]
        if end is not None and _ns(end) <= start:
            raise ContractError(ErrorCode.BOUNDS, "Positive supplied effective interval required")
        if role == "status_states":
            if parts[0] != "s1" or len(parts[3]) != 19 or any(c not in "0123456789" for c in parts[3]) or int(parts[3]) > I64_MAX:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact s1 seq19 identity required")
            sequence = int(parts[3])
            _status_unb64(parts[4])
            if previous is not None and sequence <= previous:
                raise ContractError(ErrorCode.DUPLICATE if sequence == previous else ErrorCode.INVALID_ORDER,
                                    "Strict original publisher sequence required")
            if previous_start is not None and start < previous_start:
                raise ContractError(ErrorCode.INVALID_ORDER, "Original effective times must not descend")
            previous, previous_start = sequence, start
            dimension = next(name for name, spec in _STATUS_DIMENSIONS.items() if spec[0] == code)
            if columns["fact_kind"][i] != "ef1.status." + dimension or texts[i] not in _STATUS_DIMENSIONS[dimension][1]:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Closed status state vocabulary required")
        else:
            if parts[0] != "p1":
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact p1 certificate identity required")
            targets.add(_status_unb64(parts[3]))
            _status_unb64(parts[4])
            kind = "ef1.status." + ("prefix_complete" if role == "status_prefix" else "validity")
            if columns["fact_kind"][i] != kind or texts[i] != code:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Dedicated proof vocabulary required")
            if end is None:
                raise ContractError(ErrorCode.BOUNDS, "Finite status proof interval required")
    if len(identities) > 1 or len(targets) > 1:
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One supplied dimension/epoch/target required")
    return identities, targets


@dataclass(frozen=True)
class StatusInputs:
    """Exact role positions and actual originals; None is missing, empty is present."""
    calendar_provenance: CanonicalBatch | None
    status_states: CanonicalBatch | None
    status_prefix: CanonicalBatch | None
    status_validity: CanonicalBatch | None
    provenance: tuple[str, str, str, str]

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 4:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Four explicit provenance modes required")
        identities: set[tuple[str, str]] = set()
        relations: set[tuple[str, str, str]] = set()
        namespaces: set[str] = set()
        entities: set[tuple[Cell, Cell]] = set()
        input_ids: set[str] = set()
        status_modes: set[str] = set()
        status_sources: set[tuple[str, str]] = set()
        for role, batch, mode in zip(self.roles, self.slots, self.provenance, strict=True):
            if type(mode) is not str or mode not in _MODES or (batch is None) != (mode == "unavailable"):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Explicit role source mode must match delivery")
            if batch is None:
                continue
            if type(batch) is not CanonicalBatch:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Actual canonical batch or None required")
            if role != "calendar_provenance":
                status_modes.add(mode)
            declared, targets = _status_validate_role(batch, role)
            identities.update(declared)
            source = batch.metadata.source
            if role != "calendar_provenance":
                status_sources.add((source.source_id, source.snapshot_id))
            if source.input_id in input_ids:
                raise ContractError(ErrorCode.DUPLICATE, "Distinct actual input bindings required")
            input_ids.add(source.input_id)
            namespaces.add(batch.metadata.namespace)
            cols = {column.name: column.values for column in batch.columns}
            entities.update(zip(cols["instrument_id"], cols["session_id"], strict=True))
            if role == "status_states":
                relations.add((source.input_id, source.source_id, source.snapshot_id))
            elif role != "calendar_provenance":
                relations.update((target, source.source_id, source.snapshot_id) for target in targets)
        if (len(status_modes) > 1 or len(status_sources) > 1 or len(identities) > 1
                or len(relations) > 1 or len(namespaces) > 1 or len(entities) > 1):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Coherent actual status target/source/revision required")
        if sum(batch.row_count for batch in self.batches) > 4096:
            raise ContractError(ErrorCode.BOUNDS, "Aggregate status REFERENCE row bound exceeded")

    @property
    def roles(self) -> tuple[str, str, str, str]:
        return _STATUS_ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.calendar_provenance, self.status_states, self.status_prefix, self.status_validity)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in self.slots if batch is not None)


def synthetic_status_context(case: str = "S01") -> dict[str, object]:
    """Original S01-S03 selection only; no acquired state/availability in context."""
    if case not in ("S01", "S02", "S03"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown synthetic status fixture")
    dimension, code = ("trading", "t") if case == "S01" else ("ssr", "s")
    seed = "YQ" if case == "S03" else "c2VlZA"
    return {"version": "ef1-context1", "producer": "status", "calendar": synthetic_clock_calendar(),
            "selection": {"dimension": dimension, "epoch": "e", "max_age_ns": None,
                          "seed_reference_id": f"s1:{code}:ZQ:0000000000000000000:{seed}"}}


def synthetic_status_fixture(case: str = "S01") -> StatusInputs:
    """Literal public source cases, distinct from expected numerical result fixtures."""
    synthetic_status_context(case)  # Reject unknown case without inventing a default.
    dimension = "trading" if case == "S01" else "ssr"
    rows: tuple[StatusState, ...]
    if case == "S01":
        rows = (StatusState(0, "seed", 8, None, "active", 8),
                StatusState(1, "halt", 12, None, "halted", 12),
                StatusState(2, "resume", 16, None, "active", 16))
        start, prefix_end, validity_end, known = 8, 20, 21, 8
    elif case == "S02":
        rows = (StatusState(0, "seed", 5, None, "on", 5),)
        start, prefix_end, validity_end, known = 5, 16, 17, 5
    else:
        rows = (StatusState(0, "a", 5, None, "on", 5), StatusState(1, "b", 5, None, "off", 5))
        start, prefix_end, validity_end, known = 5, 20, 21, 5
    states = make_status_states(rows, dimension=dimension, epoch="e", instrument_id="X", session_id="S",
        metadata=BatchMetadata("SYN", SourceBinding("F", "R1", "ef1-reference-map1", "st"),
                               Coverage(len(rows), len(rows), True), None))
    proofs = []
    for role, certificate, end, input_id in (("status_prefix", "pref", prefix_end, "status-prefix"),
                                              ("status_validity", "valid", validity_end, "status-validity")):
        proofs.append(make_status_proof((StatusCertificate(certificate, start, end, known),),
            role=role, dimension=dimension, epoch="e", target_input_id="st", instrument_id="X", session_id="S",
            metadata=BatchMetadata("SYN", SourceBinding("F", "R1", "ef1-reference-map1", input_id),
                                   Coverage(1, 1, True), None)))
    return StatusInputs(synthetic_clock_fixture().calendar_provenance, states, proofs[0], proofs[1],
                        ("synthetic", "synthetic", "synthetic", "synthetic"))

__all__ += ["StatusState", "StatusCertificate", "StatusInputs", "make_status_states",
            "make_status_proof", "synthetic_status_context", "synthetic_status_fixture"]

# Sampled path conversion is additive; existing producers above are unchanged.
def _validate_path_slots(slots: tuple[CanonicalBatch | None, ...],
                         provenance: tuple[str, ...]) -> None:
    if type(provenance) is not tuple or len(provenance) != len(slots):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact path provenance tuple required")
    present: list[CanonicalBatch] = []
    for index, (batch, mode) in enumerate(zip(slots, provenance)):
        if type(mode) is not str or mode not in _MODES or (batch is None) != (mode == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Path source mode must match actual delivery")
        if batch is None:
            continue
        kinds = ((DataKind.REFERENCE,), (DataKind.TRADE, DataKind.BAR), (DataKind.DAILY,))[index]
        if type(batch) is not CanonicalBatch or batch.kind not in kinds:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Canonical path role kind mismatch")
        validate_batch(batch, required_fields=())
        present.append(batch)
    if (len({b.metadata.source.input_id for b in present}) != len(present)
            or len({b.metadata.namespace for b in present}) > 1):
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Distinct actual path bindings in one namespace required")


@dataclass(frozen=True)
class PathGapInputs:
    """Present-only role-ordered actual inputs; origins are caller declarations."""
    calendar_provenance: CanonicalBatch | None = None
    path: CanonicalBatch | None = None
    prior_close: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable", "unavailable", "unavailable")

    def __post_init__(self) -> None:
        _validate_path_slots((self.calendar_provenance, self.path, self.prior_close), self.provenance)

    @property
    def roles(self) -> tuple[str, ...]:
        return ("calendar_provenance", "path", "prior_close")

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(b for b in (self.calendar_provenance, self.path, self.prior_close) if b is not None)


@dataclass(frozen=True)
class PathDriveInputs:
    """Calendar and sampled path, with omitted delivery preserved as omission."""
    calendar_provenance: CanonicalBatch | None = None
    path: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable", "unavailable")

    def __post_init__(self) -> None:
        _validate_path_slots((self.calendar_provenance, self.path), self.provenance)

    @property
    def roles(self) -> tuple[str, ...]:
        return ("calendar_provenance", "path")

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(b for b in (self.calendar_provenance, self.path) if b is not None)


def make_path_prior_close(row: Mapping[str, Cell], *, metadata: BatchMetadata,
                          instrument_id: str, session_id: str) -> CanonicalBatch:
    """Convert exactly one explicitly selected DAILY row without field dropping.

    Times, optional operands and original known-at are supplied canonical cells.
    This does not select a previous day, manufacture coverage, quantize prices,
    infer auction flags or repair invalid original OHLC/volume.
    """
    fields = ("start_ns", "end_ns", "open", "high", "low", "close", "volume",
              "actual_notional", "known_at_ns")
    if (not isinstance(row, Mapping) or not {"start_ns", "end_ns"} <= set(row)
            or set(row) - set(fields) or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Explicit canonical DAILY row required")
    _label(instrument_id)
    _label(session_id)
    result = CanonicalBatch(DataKind.DAILY,
        (Column("instrument_id", (instrument_id,)), Column("session_id", (session_id,)))
        + tuple(Column(name, (row[name],)) for name in fields if name in row), metadata)
    validate_batch(result, required_fields=())
    return result


def _synthetic_path_context(producer: str, sampling: str) -> dict[str, object]:
    sessions: list[list[object]] = [["S", "2026-10-20", 10, 30]]
    if producer == "path_gap":
        sessions.insert(0, ["P", "2026-10-19", -10, 0])
    selection: dict[str, object] = {"sampling": sampling}
    if producer == "path_drive":
        selection["duration_ns"] = 5
    return {"version": "ef1-context1", "producer": producer,
        "calendar": {"calendar_id": "SYN-CAL", "revision": "R1", "timezone": "UTC",
            "target_date": "2026-10-20", "sessions": sessions,
            "segments": [["regular", 10, 30]], "scheduled_close_ns": 30, "early_close": False},
        "selection": selection}


def synthetic_path_gap_context(case: str = "G01") -> dict[str, object]:
    """Fresh literal reviewed G01/G02/G03 context; no implicit source discovery."""
    if case not in ("G01", "G02", "G03"):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown synthetic gap case")
    return _synthetic_path_context("path_gap", "completed_bar_close" if case == "G02" else "eligible_trade")


def synthetic_path_drive_context(case: str = "D01") -> dict[str, object]:
    if case != "D01":
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown synthetic drive case")
    return _synthetic_path_context("path_drive", "eligible_trade")


def _synthetic_path_proof(context: Mapping[str, object], start: int) -> CanonicalBatch:
    calendar = cast(Mapping[str, object], context["calendar"])
    proof = make_calendar_provenance(calendar, namespace="SYN", instrument_id="X", session_id="S",
        source_id="SYN-CALENDAR", input_id="calendar", known_at_ns=-10, start_ns=start, end_ns=30)
    # Freeze the amendment's explicit source-column order; no result codec changes.
    names = ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns",
             "effective_end_ns", "text", "known_at_ns")
    return CanonicalBatch(proof.kind, tuple(c for name in names for c in proof.columns if c.name == name), proof.metadata)


def _synthetic_path_batch(rows: tuple[tuple[Cell, ...], ...], *, bar: bool, end: int) -> CanonicalBatch:
    names = (("start_ns", "end_ns", "open", "high", "low", "close", "volume", "known_at_ns") if bar else
             ("event_ns", "order_key", "event_id", "eligible", "price", "size", "known_at_ns"))
    count = len(rows)
    columns = (Column("instrument_id", ("X",) * count), Column("session_id", ("S",) * count)) + tuple(
        Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    metadata = BatchMetadata("SYN", SourceBinding("SYN-PATH", "R1", "ef1-path-map1", "path"),
        Coverage(count, count, True), PriceUnit(0, "USD"), AdjustmentSpec(),
        scope=InputScope(10, end, "supplied_path"))
    return CanonicalBatch(DataKind.BAR if bar else DataKind.TRADE, columns, metadata)


def synthetic_path_gap_fixture(case: str = "G01") -> PathGapInputs:
    """Original literal reviewed source populations, separate from result goldens."""
    context = synthetic_path_gap_context(case)
    if case == "G02":
        rows: tuple[tuple[Cell, ...], ...] = ((10, 12, 12, 13, 9, 11, 2, 12),)
    elif case == "G03":
        rows = ((10, 0, "a", True, 10, 1, 10), (11, 1, "b", True, 11, 1, 11), (12, 2, "c", True, 12, 1, 12))
    else:
        rows = ((10, 0, "a", True, 12, 1, 10), (11, 1, "b", True, 11, 1, 11), (12, 2, "c", True, 9, 1, 12))
    prior = make_path_prior_close({"start_ns": -10, "end_ns": 0, "close": 12 if case == "G03" else 10,
        "known_at_ns": 0}, metadata=BatchMetadata("SYN", SourceBinding("SYN-DAILY", "R1", "ef1-path-map1", "prior"),
        Coverage(1, 1, True), PriceUnit(0, "USD"), AdjustmentSpec(), scope=InputScope(-10, 0, "supplied_path")),
        instrument_id="X", session_id="P")
    return PathGapInputs(_synthetic_path_proof(context, -10),
        _synthetic_path_batch(rows, bar=case == "G02", end=12 if case == "G02" else 13), prior, ("synthetic",) * 3)


def synthetic_path_drive_fixture(case: str = "D01") -> PathDriveInputs:
    context = synthetic_path_drive_context(case)
    rows: tuple[tuple[Cell, ...], ...] = ((10, 0, "a", True, 10, 1, 10),
        (12, 1, "b", True, 12, 1, 12), (14, 2, "c", True, 11, 1, 14))
    return PathDriveInputs(_synthetic_path_proof(context, -10),
        _synthetic_path_batch(rows, bar=False, end=15), ("synthetic",) * 2)


__all__ += ["PathGapInputs", "PathDriveInputs", "make_path_prior_close",
            "synthetic_path_gap_context", "synthetic_path_drive_context",
            "synthetic_path_gap_fixture", "synthetic_path_drive_fixture"]

# Supplied REFERENCE conversion: no assessments, transformations or acquisition.
_REFERENCE_CLASS_ROLES = ("classification_facts", "classification_history", "classification_projection")
_REFERENCE_ACTION_ROLES = ("market", "action_facts", "action_history", "action_projection",
                           "source_representation", "source_quantity_basis")
_REFERENCE_KINDS = {"sector_membership": "s", "universe_membership": "u", "industry_membership": "i"}
_REFERENCE_PROOFS = {
    "classification_history": ("ef1.classification.history", ("historical", "current_only", "unknown")),
    "classification_projection": ("ef1.reference.projection", ("complete", "partial", "unknown")),
    "action_history": ("ef1.action.history", ("historical", "current_only", "unknown")),
    "action_projection": ("ef1.reference.projection", ("complete", "partial", "unknown")),
    "source_representation": ("ef1.action.representation", ("raw", "caller_transformed")),
    "source_quantity_basis": ("ef1.action.quantity_basis", ("raw_shares", "split_shares")),
}


def _reference_text(value: Cell) -> None:
    # EF1-REF-A2: body text is not an identity. Preserve blanks, null and spacing.
    if value is None:
        return
    if (type(value) is not str or len(value) > 128
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
            or len(value.encode("utf-8")) > 512):
        raise ContractError(ErrorCode.BOUNDS, "Bounded original reference text required")


def _reference_role(batch: CanonicalBatch, role: str) -> tuple[set[str], set[tuple[str, str]]]:
    validate_batch(batch, required_fields=())
    if batch.kind != DataKind.REFERENCE:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Explicit EF1 REFERENCE mapping required")
    if batch.metadata.source.mapping_version != "ef1-reference-map1":
        raise ContractError(ErrorCode.INCOMPATIBLE_VERSION, "Unsupported reference mapping")
    if batch.metadata.coverage.observed != batch.row_count:
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Actual reference population mismatch")
    if batch.metadata.ordering != "declared" or batch.metadata.duplicate_policy != "reject":
        raise ContractError(ErrorCode.INVALID_ORDER, "Ordered unique reference population required")
    for value in (batch.metadata.namespace, batch.metadata.source.source_id,
                  batch.metadata.source.snapshot_id, batch.metadata.source.input_id):
        _label(value)
    cols = {c.name: c.values for c in batch.columns}
    targets: set[str] = set()
    declarations: set[tuple[str, str]] = set()
    for i in range(batch.row_count):
        for name in ("instrument_id", "session_id", "reference_id", "fact_kind"):
            _label(cols[name][i])
        reference = cast(str, cols["reference_id"][i])
        kind = cols["fact_kind"][i]
        text = cols.get("text", (None,) * batch.row_count)[i]
        _reference_text(text)
        for payload in ("price", "factor_num", "factor_den"):
            if role != "action_facts" and cols.get(payload, (None,) * batch.row_count)[i] is not None:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Reference text/proof cannot carry numeric payload")
        if role == "classification_facts":
            if kind not in _REFERENCE_KINDS:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Closed classification kind required")
            continue
        if role == "action_facts":
            if text is not None or cols.get("price", (None,) * batch.row_count)[i] is not None:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Action factor has no text/price payload")
            if (kind not in ("split_factor", "dividend_factor")
                    or cols.get("effective_end_ns", (None,) * batch.row_count)[i] is not None
                    or any(type(cols.get(name, (None,) * batch.row_count)[i]) is not int
                           or cast(int, cols.get(name, (None,) * batch.row_count)[i]) <= 0
                           for name in ("factor_num", "factor_den"))):
                raise ContractError(ErrorCode.UNSUPPORTED_ADJUSTMENT, "Exact supplied positive action factor required")
            continue
        expected_kind, vocabulary = _REFERENCE_PROOFS[role]
        if kind != expected_kind or text not in vocabulary:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Closed supplied proof vocabulary required")
        if cols.get("effective_end_ns", (None,) * batch.row_count)[i] is None:
            raise ContractError(ErrorCode.BOUNDS, "Finite proof interval required")
        parts = reference.split(":")
        if role == "classification_history":
            if len(parts) != 5 or parts[0] != "h1" or parts[1] not in ("s", "u", "i"):
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact classification history grammar required")
            declarations.add((parts[1], _status_unb64(parts[2])))
            targets.add(_status_unb64(parts[3]))
            _status_unb64(parts[4])
        elif role == "action_history":
            if len(parts) != 4 or parts[0] != "a1":
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact action history grammar required")
            declarations.add(("action", _status_unb64(parts[1])))
            targets.add(_status_unb64(parts[2]))
            _status_unb64(parts[3])
        else:
            prefix = "r1" if role.endswith("projection") else "q1"
            if len(parts) != 3 or parts[0] != prefix:
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact bound proof grammar required")
            targets.add(_status_unb64(parts[1]))
            _status_unb64(parts[2])
        if batch.metadata.source.input_id in targets:
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Proof cannot name itself")
    if len(targets) > 1 or len(declarations) > 1:
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One declared proof target/scope required")
    return targets, declarations


def _validate_reference_slots(roles: tuple[str, ...], slots: tuple[CanonicalBatch | None, ...],
                              provenance: tuple[str, ...]) -> None:
    if type(provenance) is not tuple or len(provenance) != len(slots):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact reference provenance tuple required")
    ids: set[str] = set()
    namespaces: set[str] = set()
    entities: set[tuple[Cell, Cell]] = set()
    relations: dict[str, set[tuple[str, str, str]]] = {"facts": set(), "market": set()}
    source_pairs: dict[str, set[tuple[str, str]]] = {"facts": set(), "market": set()}
    population = 0
    for role, batch, mode in zip(roles, slots, provenance, strict=True):
        if type(mode) is not str or mode not in _MODES or (batch is None) != (mode == "unavailable"):
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Actual delivery and provenance must agree")
        if batch is None:
            continue
        if type(batch) is not CanonicalBatch:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Original CanonicalBatch or None required")
        source = batch.metadata.source
        if source.input_id in ids:
            raise ContractError(ErrorCode.DUPLICATE, "Distinct actual input bindings required")
        ids.add(source.input_id)
        namespaces.add(batch.metadata.namespace)
        cols = {c.name: c.values for c in batch.columns}
        group = "market" if role in ("market", "source_representation", "source_quantity_basis") else "facts"
        # Empty delivery still declares an actual publisher/revision. Bind that
        # metadata independently of row-level target IDs; never invent a target.
        source_pairs[group].add((source.source_id, source.snapshot_id))
        if role == "market":
            if batch.kind not in (DataKind.TRADE, DataKind.BAR, DataKind.DAILY):
                raise ContractError(ErrorCode.INVALID_SCHEMA, "Action market must be TRADE/BAR/DAILY")
            validate_batch(batch, required_fields=())
            relations["market"].add((source.input_id, source.source_id, source.snapshot_id))
        else:
            targets, _ = _reference_role(batch, role)
            population += batch.row_count
            if role in ("classification_facts", "action_facts"):
                targets = {source.input_id}
            relations[group].update((target, source.source_id, source.snapshot_id) for target in targets)
        entities.update(zip(cols["instrument_id"], cols["session_id"], strict=True))
    if (len(namespaces) > 1 or len(entities) > 1 or any(len(v) > 1 for v in relations.values())
            or any(len(v) > 1 for v in source_pairs.values())):
        raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Coherent actual target/entity/source/revision required")
    if population > 4096:
        raise ContractError(ErrorCode.BOUNDS, "Aggregate REFERENCE row bound exceeded")


@dataclass(frozen=True)
class ReferenceClassificationInputs:
    """Exact nullable slots; incomplete/empty/late originals remain original."""
    classification_facts: CanonicalBatch | None = None
    classification_history: CanonicalBatch | None = None
    classification_projection: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable",) * 3

    def __post_init__(self) -> None:
        _validate_reference_slots(self.roles, self.slots, self.provenance)

    @property
    def roles(self) -> tuple[str, ...]:
        return _REFERENCE_CLASS_ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.classification_facts, self.classification_history, self.classification_projection)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in self.slots if batch is not None)


@dataclass(frozen=True)
class ReferenceActionInputs:
    """Six fixed actual slots, mixed market kind and explicit per-role origins."""
    market: CanonicalBatch | None = None
    action_facts: CanonicalBatch | None = None
    action_history: CanonicalBatch | None = None
    action_projection: CanonicalBatch | None = None
    source_representation: CanonicalBatch | None = None
    source_quantity_basis: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable",) * 6

    def __post_init__(self) -> None:
        _validate_reference_slots(self.roles, self.slots, self.provenance)

    @property
    def roles(self) -> tuple[str, ...]:
        return _REFERENCE_ACTION_ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.market, self.action_facts, self.action_history, self.action_projection,
                self.source_representation, self.source_quantity_basis)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in self.slots if batch is not None)


def make_reference_rows(rows: tuple[Mapping[str, Cell], ...], *, role: str,
                        metadata: BatchMetadata, instrument_id: str, session_id: str) -> CanonicalBatch:
    """Map explicit original canonical cells, retaining every supplied field.

    Columns may be absent only when absent throughout the supplied population;
    inconsistent row shapes reject instead of manufacturing null observations.
    No sorting, filtering, date selection, knowledge repair or factor application.
    """
    if type(rows) is not tuple or len(rows) > 4096 or role not in _REFERENCE_CLASS_ROLES + _REFERENCE_ACTION_ROLES[1:]:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Bounded concrete reference rows and closed role required")
    _label(instrument_id)
    _label(session_id)
    fields = ("reference_id", "fact_kind", "effective_start_ns", "effective_end_ns", "text",
              "price", "factor_num", "factor_den", "known_at_ns")
    required = {"reference_id", "fact_kind", "effective_start_ns"}
    keys = set(rows[0]) if rows and isinstance(rows[0], Mapping) else (required | {"effective_end_ns", "text", "known_at_ns"})
    if not required <= keys or keys - set(fields) or any(not isinstance(r, Mapping) or set(r) != keys for r in rows):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact consistent canonical reference row fields required")
    batch = CanonicalBatch(DataKind.REFERENCE,
        (Column("instrument_id", (instrument_id,) * len(rows)), Column("session_id", (session_id,) * len(rows)))
        + tuple(Column(name, tuple(row[name] for row in rows)) for name in fields if name in keys), metadata)
    _reference_role(batch, role)
    return batch


@dataclass(frozen=True)
class ReferenceCertificate:
    """Original publisher proof, never generated from observed membership/actions."""
    certificate_id: str
    effective_start_ns: int
    effective_end_ns: int
    text: str
    known_at_ns: int | None


def make_reference_proof(rows: tuple[ReferenceCertificate, ...], *, role: str,
                         target_input_id: str, metadata: BatchMetadata, instrument_id: str,
                         session_id: str, scope_id: str | None = None,
                         fact_kind: str | None = None) -> CanonicalBatch:
    if role not in _REFERENCE_PROOFS or type(rows) is not tuple or len(rows) > 4096:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Closed role and bounded actual proof tuple required")
    target = _status_b64(target_input_id)
    if role == "classification_history":
        if fact_kind not in _REFERENCE_KINDS or scope_id is None:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Explicit classification kind/scope required")
        prefix = "h1:" + _REFERENCE_KINDS[cast(str, fact_kind)] + ":" + _status_b64(scope_id) + ":" + target
    elif role == "action_history":
        if scope_id is None:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Explicit action scope required")
        prefix = "a1:" + _status_b64(scope_id) + ":" + target
    else:
        prefix = ("r1:" if role.endswith("projection") else "q1:") + target
    originals: list[Mapping[str, Cell]] = []
    for row in rows:
        if type(row) is not ReferenceCertificate:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Actual supplied certificate required")
        originals.append({"reference_id": prefix + ":" + _status_b64(row.certificate_id),
            "fact_kind": _REFERENCE_PROOFS[role][0], "effective_start_ns": row.effective_start_ns,
            "effective_end_ns": row.effective_end_ns, "text": row.text, "known_at_ns": row.known_at_ns})
    return make_reference_rows(tuple(originals), role=role, metadata=metadata,
                               instrument_id=instrument_id, session_id=session_id)


def _synthetic_reference_metadata(input_id: str, count: int) -> BatchMetadata:
    return BatchMetadata("fixture", SourceBinding("synthetic", "R1", "ef1-reference-map1", input_id),
                         Coverage(count, count, True), None)


def synthetic_reference_classification_context(case: str = "R01", *, fact_kind: str = "sector_membership") -> dict[str, object]:
    if case not in ("R01", "R02") or fact_kind not in _REFERENCE_KINDS:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit classification fixture")
    return {"version": "ef1-context1", "producer": "reference_classification", "calendar": None,
            "selection": {"fact_kind": fact_kind, "scope_id": "U", "effective_ns": 20}}


def synthetic_reference_classification_fixture(case: str = "R01", *, fact_kind: str = "sector_membership") -> ReferenceClassificationInputs:
    synthetic_reference_classification_context(case, fact_kind=fact_kind)
    rows: tuple[Mapping[str, Cell], ...] = () if case == "R02" else (
        {"reference_id": "a", "fact_kind": fact_kind, "effective_start_ns": 0,
         "effective_end_ns": 20, "text": "A", "known_at_ns": 5},
        {"reference_id": "b", "fact_kind": fact_kind, "effective_start_ns": 20,
         "effective_end_ns": 40, "text": "B", "known_at_ns": 5})
    facts = make_reference_rows(rows, role="classification_facts", metadata=_synthetic_reference_metadata("cl", len(rows)),
        instrument_id="X", session_id="S")
    history = make_reference_proof((ReferenceCertificate("h", 0, 40, "historical", 5),),
        role="classification_history", target_input_id="cl", scope_id="U", fact_kind=fact_kind,
        metadata=_synthetic_reference_metadata("ch", 1), instrument_id="X", session_id="S")
    projection = make_reference_proof((ReferenceCertificate("p", 0, 40, "complete", 5),),
        role="classification_projection", target_input_id="cl", metadata=_synthetic_reference_metadata("cp", 1),
        instrument_id="X", session_id="S")
    return ReferenceClassificationInputs(facts, history, projection, ("synthetic",) * 3)


def synthetic_reference_action_context(case: str = "R03") -> dict[str, object]:
    if case != "R03":
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit action fixture")
    return {"version": "ef1-context1", "producer": "reference_action", "calendar": None,
        "selection": {"scope_id": "U", "scope_start_ns": 0, "scope_end_ns": 21,
            "policy": {"adjustment": {"basis": "split", "anchor": "anchor20", "action_snapshot": "R1",
                "policy_version": "split-factors-v1"}, "anchor_ns": 20, "dividend_convention": "none",
                "quantity_basis": "split_shares", "representation": "apply_factors", "schema_version": "1"}}}


def synthetic_reference_action_fixture(case: str = "R03") -> ReferenceActionInputs:
    synthetic_reference_action_context(case)
    market = CanonicalBatch(DataKind.TRADE, tuple(Column(name, (value,)) for name, value in (
        ("instrument_id", "X"), ("session_id", "S"), ("event_ns", 10), ("order_key", 0),
        ("event_id", "t"), ("eligible", True), ("price", 100), ("size", 10), ("known_at_ns", 10))),
        BatchMetadata("fixture", SourceBinding("synthetic", "R1", "ef1-market-map1", "mk"),
                      Coverage(1, 1, True), PriceUnit(0, "USD"), AdjustmentSpec(),
                      scope=InputScope(10, 20, "supplied_action")))
    facts = make_reference_rows(({"reference_id": "split", "fact_kind": "split_factor", "effective_start_ns": 20,
        "effective_end_ns": None, "factor_num": 1, "factor_den": 2, "known_at_ns": 20},), role="action_facts",
        metadata=_synthetic_reference_metadata("ac", 1), instrument_id="X", session_id="S")
    proofs = []
    for role, target, cert, text, input_id in (
        ("action_history", "ac", "h", "historical", "ah"), ("action_projection", "ac", "p", "complete", "ap"),
        ("source_representation", "mk", "r", "raw", "sr"), ("source_quantity_basis", "mk", "q", "raw_shares", "sq")):
        proofs.append(make_reference_proof((ReferenceCertificate(cert, 0, 21, text, 20),), role=role,
            target_input_id=target, scope_id="U" if role == "action_history" else None,
            metadata=_synthetic_reference_metadata(input_id, 1), instrument_id="X", session_id="S"))
    return ReferenceActionInputs(market, facts, proofs[0], proofs[1], proofs[2], proofs[3], ("synthetic",) * 6)


__all__ += ["ReferenceClassificationInputs", "ReferenceActionInputs", "ReferenceCertificate",
            "make_reference_rows", "make_reference_proof", "synthetic_reference_classification_context",
            "synthetic_reference_classification_fixture", "synthetic_reference_action_context",
            "synthetic_reference_action_fixture"]
