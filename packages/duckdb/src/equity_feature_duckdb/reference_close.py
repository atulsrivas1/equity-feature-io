"""Lossless supplied close-reconciliation inputs; no acquisition, BPS or comparison mathematics."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from collections.abc import Mapping

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec,
    ContractError, DataKind, ErrorCode, Parameter, PriceUnit, SessionSpec, WindowSpec,
    validate_batch,
)
from equity_feature_contracts.inputs import Cell

# Frozen ef1-close-compare1 roles: the first three are the regular-BAR roles unchanged.
_ROLES = ("calendar_provenance", "bars", "population_proof", "authoritative_close")
_ORIGINS = frozenset(("synthetic", "duckdb_backed_observed", "unavailable"))
_PROOF_COLUMNS = ("instrument_id", "session_id", "reference_id", "fact_kind",
                  "effective_start_ns", "effective_end_ns", "text", "known_at_ns")
# Required authoritative-close cells; factor columns are optional and only passed through.
_CLOSE_COLUMNS = ("instrument_id", "session_id", "reference_id", "fact_kind",
                  "effective_start_ns", "effective_end_ns", "text", "price", "known_at_ns")
_CLOSE_OPTIONAL = ("factor_num", "factor_den")


def make_reference_close_batch(kind: DataKind, column_order: tuple[str, ...],
                               rows: tuple[tuple[Cell, ...], ...], *,
                               metadata: BatchMetadata) -> CanonicalBatch:
    """Convert exact supplied rectangular cells, retaining order and metadata.

    No sorting, filtering, field filling, unit conversion, timestamp inference or
    proof canonicalization occurs. Admission of the authoritative close (identity,
    revision, effective instant, basis, coverage, denominator validity) belongs to
    the pure reference-close producer. Generic canonical validation may refuse an
    invalid original row before that callback is reached.
    """
    if (type(kind) is not DataKind
            or kind not in (DataKind.REFERENCE, DataKind.BAR)
            or type(column_order) is not tuple
            or any(type(name) is not str for name in column_order)
            or type(rows) is not tuple
            or any(type(row) is not tuple or len(row) != len(column_order) for row in rows)
            or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied reference-close rectangle required")
    result = CanonicalBatch(kind, tuple(Column(name, tuple(row[i] for row in rows))
                                       for i, name in enumerate(column_order)), metadata)
    validate_batch(result, required_fields=())
    return result


def make_reference_close_population_proof(row: Mapping[str, Cell], *,
                                          metadata: BatchMetadata) -> CanonicalBatch:
    """Convert one ALREADY SUPPLIED regular-BAR population proof record unchanged.

    The proof family is the regular-BAR one (ef1.regular_bar.population.v1); this
    helper generates no proof or membership hash and does not establish causal truth.
    """
    if not isinstance(row, Mapping) or set(row) != set(_PROOF_COLUMNS):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "All original proof cells required")
    return make_reference_close_batch(DataKind.REFERENCE, _PROOF_COLUMNS,
                                      (tuple(row[name] for name in _PROOF_COLUMNS),),
                                      metadata=metadata)


def make_authoritative_close_reference_id(scope_id: str, source_close_id: str) -> str:
    """Encode the supplied scope and opaque source close identity as k1:B(scope):B(id).

    B is reversible unpadded base64url of UTF8. This only encodes two identities the
    caller supplied; length, scope-equality and uniqueness checks belong to the pure producer.
    """
    if type(scope_id) is not str or type(source_close_id) is not str:
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Supplied scope and source close identity strings required")

    def b64(text: str) -> str:
        return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")
    return "k1:" + b64(scope_id) + ":" + b64(source_close_id)


def make_authoritative_close(row: Mapping[str, Cell], *, metadata: BatchMetadata) -> CanonicalBatch:
    """Convert ONE ALREADY SUPPLIED authoritative-close record, cells unchanged.

    Requires the nine cells instrument_id, session_id, reference_id, fact_kind,
    effective_start_ns, effective_end_ns, text, price, known_at_ns; factor_num and
    factor_den are optional and passed through verbatim if present (the producer
    refuses populated factors). The price is the supplied integer coefficient at the
    config PriceUnit scale: no rescale, no currency conversion, no fill, no inference
    of the close instant, revision (text), known-at or basis, and never a caller-computed
    substitute. Revision binding (text == snapshot_id) is checked by the pure producer.
    """
    if (not isinstance(row, Mapping) or not set(_CLOSE_COLUMNS) <= set(row)
            or not set(row) <= set(_CLOSE_COLUMNS + _CLOSE_OPTIONAL)):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "All original authoritative-close cells required")
    names = _CLOSE_COLUMNS + tuple(n for n in _CLOSE_OPTIONAL if n in row)
    return make_reference_close_batch(DataKind.REFERENCE, names,
                                      (tuple(row[name] for name in names),), metadata=metadata)


def make_reference_close_config(*, calendar: Mapping[str, object], scope_id: str,
                                tolerance_bps_num: int, tolerance_bps_den: int,
                                session: SessionSpec, window: WindowSpec,
                                availability: AvailabilitySpec, price_unit: PriceUnit,
                                adjustment: AdjustmentSpec) -> ConfigSpec:
    """Build the ef1.reference_close ConfigSpec from caller-supplied explicit inputs.

    Serializes the context envelope (canonical ASCII JSON) with the policy label
    ef1-close-compare1 and the caller's exact tolerance pair. There is no default
    tolerance and no reduction or validation of the pair here; the pure decoder owns
    reducedness, ranges, scope equality and calendar/session consistency.
    """
    if (type(scope_id) is not str or type(tolerance_bps_num) is not int
            or type(tolerance_bps_den) is not int or not isinstance(calendar, Mapping)):
        raise ContractError(ErrorCode.INVALID_CONFIG, "Explicit calendar, scope and integer tolerance pair required")
    text = json.dumps({
        "calendar": calendar, "producer": "reference_close",
        "selection": {"phase_profile": "regular_no_auctions1", "policy_version": "ef1-close-compare1",
                      "sampling": "completed_bar_close", "scope_id": scope_id,
                      "tolerance_bps_den": tolerance_bps_den, "tolerance_bps_num": tolerance_bps_num},
        "version": "ef1-context1"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return ConfigSpec("ef1.reference_close", "v1", (Parameter("ef1_context_json", text),),
                      session, window, availability, adjustment, price_unit)


@dataclass(frozen=True)
class ReferenceCloseInputs:
    """Four fixed nullable slots; present-only batches never replace pure slots.

    Origins are explicit caller declarations, not capability or rights evidence.
    The calculated close is NOT a slot: the producer selects it from bars. Never
    supply a caller-computed value in place of a missing authoritative close; use
    explicit unavailable delivery instead.
    """
    calendar_provenance: CanonicalBatch | None = None
    bars: CanonicalBatch | None = None
    population_proof: CanonicalBatch | None = None
    authoritative_close: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable",) * 4

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 4:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly four reference-close origins required")
        kinds = ((DataKind.REFERENCE,), (DataKind.BAR,), (DataKind.REFERENCE,), (DataKind.REFERENCE,))
        for batch, origin, allowed in zip(self.slots, self.provenance, kinds):
            if (type(origin) is not str or origin not in _ORIGINS
                    or (batch is None) != (origin == "unavailable")):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
            if batch is not None:
                if type(batch) is not CanonicalBatch or batch.kind not in allowed:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Reference-close role kind mismatch")
                validate_batch(batch, required_fields=())
        if len({b.metadata.source.input_id for b in self.batches}) != len(self.batches):
            raise ContractError(ErrorCode.DUPLICATE, "Distinct reference-close input IDs required")
        if len({b.metadata.namespace for b in self.batches}) > 1:
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One reference-close namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return _ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.calendar_provenance, self.bars, self.population_proof, self.authoritative_close)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in self.slots if batch is not None)


__all__ = ["ReferenceCloseInputs", "make_reference_close_batch", "make_reference_close_population_proof",
           "make_authoritative_close_reference_id", "make_authoritative_close", "make_reference_close_config"]


# Original synthetic supplied facts/config only; independent oracle expectations are not embedded.
# Calendar, bars and the regular-BAR population proof follow the regular_bar_prices R01 packet,
# with the market/knowledge cutoff at the actual close (30) so the regular prefix is complete.
_SYNTHETIC = '{"C01_within_tolerance":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":30,"knowledge_cutoff_ns":30,"market_cutoff_ns":30,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.reference_close","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"S\\",\\"2026-10-20\\",10,30]],\\"target_date\\":\\"2026-10-20\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"reference_close\\",\\"selection\\":{\\"phase_profile\\":\\"regular_no_auctions1\\",\\"policy_version\\":\\"ef1-close-compare1\\",\\"sampling\\":\\"completed_bar_close\\",\\"scope_id\\":\\"ef1-close-synthetic\\",\\"tolerance_bps_den\\":1,\\"tolerance_bps_num\\":10},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":2},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":1,"governed_sessions":["S"],"target_session_id":"S"}},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:97b10ecabd7dbe43ce93fb7db74b448720c5903638aca175494f6a893a761b58"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"SYN-CALENDAR"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"start_ns","values":[10,11,12]},{"name":"end_ns","values":[11,12,30]},{"name":"open","values":[1200,1100,1300]},{"name":"close","values":[1210,1150,1250]},{"name":"volume","values":[1,1,1]},{"name":"known_at_ns","values":[11,12,30]}],"kind":"bar","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":30,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"bars","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-BARS"}},"schema_version":"1"},"role":"bars"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["rbp1:1fcddea27299c0e900188e727d29a9f028ea2aecc6a6903c9d45a9ae1965d630"]},{"name":"fact_kind","values":["ef1.regular_bar.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":30,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":30,\\"market_cutoff_ns\\":30,\\"namespace\\":\\"SYN\\",\\"path_source\\":{\\"input_id\\":\\"bars\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-BARS\\"},\\"phase_profile\\":\\"regular_no_auctions1\\",\\"population_sha256\\":\\"0ccdd09617acbc2923807facce1f3e66455ef548ff020a51425352632a7b4729\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":2},\\"producer\\":\\"regular_bar_prices\\",\\"profile_id\\":\\"regular-bar-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-POPULATION\\"},\\"row_count\\":3,\\"sampling\\":\\"completed_bar_close\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"version\\":\\"ef1-regular-bar-population1\\"}"]},{"name":"known_at_ns","values":[30]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-POPULATION"}},"schema_version":"1"},"role":"population_proof"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["k1:ZWYxLWNsb3NlLXN5bnRoZXRpYw:U1lOLUNMT1NFLTE"]},{"name":"fact_kind","values":["ef1.close.authoritative"]},{"name":"effective_start_ns","values":[30]},{"name":"effective_end_ns","values":[null]},{"name":"text","values":["A1"]},{"name":"price","values":[1250]},{"name":"known_at_ns","values":[30]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"authoritative_close","mapping_version":"ef1-reference-map1","snapshot_id":"A1","source_id":"SYN-AUTH-CLOSE"}},"schema_version":"1"},"role":"authoritative_close"}]},"C02_outside_tolerance":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":30,"knowledge_cutoff_ns":30,"market_cutoff_ns":30,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.reference_close","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"S\\",\\"2026-10-20\\",10,30]],\\"target_date\\":\\"2026-10-20\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"reference_close\\",\\"selection\\":{\\"phase_profile\\":\\"regular_no_auctions1\\",\\"policy_version\\":\\"ef1-close-compare1\\",\\"sampling\\":\\"completed_bar_close\\",\\"scope_id\\":\\"ef1-close-synthetic\\",\\"tolerance_bps_den\\":1,\\"tolerance_bps_num\\":10},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":2},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":1,"governed_sessions":["S"],"target_session_id":"S"}},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:97b10ecabd7dbe43ce93fb7db74b448720c5903638aca175494f6a893a761b58"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"SYN-CALENDAR"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"start_ns","values":[10,11,12]},{"name":"end_ns","values":[11,12,30]},{"name":"open","values":[1200,1100,1300]},{"name":"close","values":[1210,1150,1250]},{"name":"volume","values":[1,1,1]},{"name":"known_at_ns","values":[11,12,30]}],"kind":"bar","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":30,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"bars","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-BARS"}},"schema_version":"1"},"role":"bars"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["rbp1:1fcddea27299c0e900188e727d29a9f028ea2aecc6a6903c9d45a9ae1965d630"]},{"name":"fact_kind","values":["ef1.regular_bar.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":30,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":30,\\"market_cutoff_ns\\":30,\\"namespace\\":\\"SYN\\",\\"path_source\\":{\\"input_id\\":\\"bars\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-BARS\\"},\\"phase_profile\\":\\"regular_no_auctions1\\",\\"population_sha256\\":\\"0ccdd09617acbc2923807facce1f3e66455ef548ff020a51425352632a7b4729\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":2},\\"producer\\":\\"regular_bar_prices\\",\\"profile_id\\":\\"regular-bar-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-POPULATION\\"},\\"row_count\\":3,\\"sampling\\":\\"completed_bar_close\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"version\\":\\"ef1-regular-bar-population1\\"}"]},{"name":"known_at_ns","values":[30]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-POPULATION"}},"schema_version":"1"},"role":"population_proof"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["k1:ZWYxLWNsb3NlLXN5bnRoZXRpYw:U1lOLUNMT1NFLTE"]},{"name":"fact_kind","values":["ef1.close.authoritative"]},{"name":"effective_start_ns","values":[30]},{"name":"effective_end_ns","values":[null]},{"name":"text","values":["A1"]},{"name":"price","values":[1260]},{"name":"known_at_ns","values":[30]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"authoritative_close","mapping_version":"ef1-reference-map1","snapshot_id":"A1","source_id":"SYN-AUTH-CLOSE"}},"schema_version":"1"},"role":"authoritative_close"}]},"C03_absent_authoritative_close":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":30,"knowledge_cutoff_ns":30,"market_cutoff_ns":30,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.reference_close","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"S\\",\\"2026-10-20\\",10,30]],\\"target_date\\":\\"2026-10-20\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"reference_close\\",\\"selection\\":{\\"phase_profile\\":\\"regular_no_auctions1\\",\\"policy_version\\":\\"ef1-close-compare1\\",\\"sampling\\":\\"completed_bar_close\\",\\"scope_id\\":\\"ef1-close-synthetic\\",\\"tolerance_bps_den\\":1,\\"tolerance_bps_num\\":10},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":2},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":1,"governed_sessions":["S"],"target_session_id":"S"}},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:97b10ecabd7dbe43ce93fb7db74b448720c5903638aca175494f6a893a761b58"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"SYN-CALENDAR"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"start_ns","values":[10,11,12]},{"name":"end_ns","values":[11,12,30]},{"name":"open","values":[1200,1100,1300]},{"name":"close","values":[1210,1150,1250]},{"name":"volume","values":[1,1,1]},{"name":"known_at_ns","values":[11,12,30]}],"kind":"bar","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":30,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"bars","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-BARS"}},"schema_version":"1"},"role":"bars"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["rbp1:1fcddea27299c0e900188e727d29a9f028ea2aecc6a6903c9d45a9ae1965d630"]},{"name":"fact_kind","values":["ef1.regular_bar.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":30,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":30,\\"market_cutoff_ns\\":30,\\"namespace\\":\\"SYN\\",\\"path_source\\":{\\"input_id\\":\\"bars\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-BARS\\"},\\"phase_profile\\":\\"regular_no_auctions1\\",\\"population_sha256\\":\\"0ccdd09617acbc2923807facce1f3e66455ef548ff020a51425352632a7b4729\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":2},\\"producer\\":\\"regular_bar_prices\\",\\"profile_id\\":\\"regular-bar-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-POPULATION\\"},\\"row_count\\":3,\\"sampling\\":\\"completed_bar_close\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"version\\":\\"ef1-regular-bar-population1\\"}"]},{"name":"known_at_ns","values":[30]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-POPULATION"}},"schema_version":"1"},"role":"population_proof"},{"batch":null,"role":"authoritative_close"}]}}'


def _synthetic_packet(case_id: str) -> dict[str, object]:
    import json
    from typing import cast
    packets = cast(dict[str, dict[str, object]], json.loads(_SYNTHETIC))
    if type(case_id) is not str or case_id not in packets:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic reference-close case")
    return packets[case_id]


def synthetic_reference_close_config(case_id: str = "C01_within_tolerance") -> ConfigSpec:
    """Detached literal config for an explicitly synthetic close-reconciliation example."""
    import json
    return ConfigSpec.from_json(json.dumps(_synthetic_packet(case_id)["config"],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))


def synthetic_reference_close_fixture(case_id: str = "C01_within_tolerance") -> ReferenceCloseInputs:
    """Original synthetic facts; the supplied close is a stipulated synthetic fact.

    This fixture supplies no observed-source capability or rights evidence. It never
    derives the calculated close, BPS or a tolerance verdict, and C03 delivers no
    authoritative close at all (explicitly unavailable).
    """
    from typing import Any, cast
    from equity_feature_contracts import Coverage, InputScope, IntervalCoverage, SourceBinding
    packet = cast(dict[str, Any], _synthetic_packet(case_id))
    batches: list[CanonicalBatch | None] = []
    for slot in packet["role_slots"]:
        raw = slot["batch"]
        if raw is None:
            batches.append(None)
            continue
        if raw["schema_version"] != "1":
            raise ContractError(ErrorCode.INCOMPATIBLE_VERSION, "Canonical schema 1 required")
        m = raw["metadata"]
        metadata = BatchMetadata(namespace=m["namespace"], source=SourceBinding(**m["source"]),
            coverage=Coverage(**m["coverage"]), price_unit=None if m["price_unit"] is None else PriceUnit(**m["price_unit"]),
            adjustment=AdjustmentSpec(**m["adjustment"]), sampling=m["sampling"], quantity_unit=m["quantity_unit"],
            ordering=m["ordering"], duplicate_policy=m["duplicate_policy"],
            scope=None if m["scope"] is None else InputScope(**m["scope"]),
            interval_coverage=tuple(IntervalCoverage(**{**item, "coverage": Coverage(**item["coverage"])})
                                    for item in m["interval_coverage"]))
        columns = raw["columns"]
        if len({len(c["values"]) for c in columns}) > 1:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Original rectangle required")
        batches.append(make_reference_close_batch(DataKind(raw["kind"]), tuple(c["name"] for c in columns),
            tuple(zip(*(c["values"] for c in columns))), metadata=metadata))
    return ReferenceCloseInputs(batches[0], batches[1], batches[2], batches[3],
        provenance=tuple("unavailable" if b is None else "synthetic" for b in batches))


__all__ += ["synthetic_reference_close_config", "synthetic_reference_close_fixture"]
