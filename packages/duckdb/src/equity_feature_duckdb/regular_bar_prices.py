"""Lossless supplied regular BAR inputs; no acquisition or price mathematics."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from equity_feature_contracts import (
    BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, DataKind, ErrorCode,
    validate_batch,
)
from equity_feature_contracts.inputs import Cell

_ROLES = ("calendar_provenance", "bars", "population_proof")
_ORIGINS = frozenset(("synthetic", "duckdb_backed_observed", "unavailable"))
_PROOF_COLUMNS = ("instrument_id", "session_id", "reference_id", "fact_kind",
                  "effective_start_ns", "effective_end_ns", "text", "known_at_ns")


def make_regular_bar_price_batch(kind: DataKind, column_order: tuple[str, ...],
                            rows: tuple[tuple[Cell, ...], ...], *,
                            metadata: BatchMetadata) -> CanonicalBatch:
    """Convert exact supplied rectangular cells, retaining order and metadata.

    No sorting, filtering, field filling, unit conversion, timestamp inference or
    proof canonicalization occurs. Closed proof grammar and mathematical identity
    admission belong to the pure regular BAR producer. Generic canonical validation
    may refuse an invalid original row before that callback is reached.
    """
    if (type(kind) is not DataKind
            or kind not in (DataKind.REFERENCE, DataKind.BAR)
            or type(column_order) is not tuple
            or any(type(name) is not str for name in column_order)
            or type(rows) is not tuple
            or any(type(row) is not tuple or len(row) != len(column_order) for row in rows)
            or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied regular BAR rectangle required")
    result = CanonicalBatch(kind, tuple(Column(name, tuple(row[i] for row in rows))
                                       for i, name in enumerate(column_order)), metadata)
    validate_batch(result, required_fields=())
    return result


def make_regular_bar_population_proof(row: Mapping[str, Cell], *,
                              metadata: BatchMetadata) -> CanonicalBatch:
    """Convert one ALREADY SUPPLIED proof record without generating its truth.

    The caller supplies all eight cells including original text, reference digest,
    effective bounds and original known-at (including null). Computing a record
    now cannot establish that a source snapshot or membership existed at K.
    This helper never hashes observations or backdates declarations. Original
    JSON bytes survive, including malformed semantic controls for pure admission.
    """
    if not isinstance(row, Mapping) or set(row) != set(_PROOF_COLUMNS):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "All original proof cells required")
    return make_regular_bar_price_batch(DataKind.REFERENCE, _PROOF_COLUMNS,
                                   (tuple(row[name] for name in _PROOF_COLUMNS),),
                                   metadata=metadata)


@dataclass(frozen=True)
class RegularBarPriceInputs:
    """Three fixed nullable slots; present-only batches never replace pure slots.

    Origins are explicit caller declarations, not capability or rights evidence.
    Observed-source admission remains unqualified. Retain real source identities;
    use explicit unavailable delivery when a truthful proof cannot be supplied.
    """
    calendar_provenance: CanonicalBatch | None = None
    bars: CanonicalBatch | None = None
    population_proof: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable",) * 3

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 3:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly three regular BAR origins required")
        kinds = ((DataKind.REFERENCE,), (DataKind.BAR,), (DataKind.REFERENCE,))
        for batch, origin, allowed in zip(self.slots, self.provenance, kinds):
            if (type(origin) is not str or origin not in _ORIGINS
                    or (batch is None) != (origin == "unavailable")):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
            if batch is not None:
                if type(batch) is not CanonicalBatch or batch.kind not in allowed:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Regular BAR role kind mismatch")
                validate_batch(batch, required_fields=())
        if len({b.metadata.source.input_id for b in self.batches}) != len(self.batches):
            raise ContractError(ErrorCode.DUPLICATE, "Distinct regular BAR input IDs required")
        if len({b.metadata.namespace for b in self.batches}) > 1:
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One regular BAR namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return _ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.calendar_provenance, self.bars, self.population_proof)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in self.slots if batch is not None)


__all__ = ["RegularBarPriceInputs", "make_regular_bar_price_batch", "make_regular_bar_population_proof"]


# Original supplied synthetic facts from the independently frozen 100-case oracle.
# No expected results, projection generator or mathematical output is embedded.
_SYNTHETIC = '{"R01_two_independent_endpoints":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":14,"knowledge_cutoff_ns":14,"market_cutoff_ns":14,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.regular_bar_prices","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"S\\",\\"2026-10-20\\",10,30]],\\"target_date\\":\\"2026-10-20\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"regular_bar_prices\\",\\"selection\\":{\\"phase_profile\\":\\"regular_no_auctions1\\",\\"sampling\\":\\"completed_bar_close\\"},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":2},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":1,"governed_sessions":["S"],"target_session_id":"S"}},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:97b10ecabd7dbe43ce93fb7db74b448720c5903638aca175494f6a893a761b58"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"SYN-CALENDAR"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"start_ns","values":[10,11,12]},{"name":"end_ns","values":[11,12,14]},{"name":"open","values":[1200,1100,1300]},{"name":"close","values":[1210,1150,1250]},{"name":"volume","values":[1,1,1]},{"name":"known_at_ns","values":[11,12,14]}],"kind":"bar","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":14,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"bars","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-BARS"}},"schema_version":"1"},"role":"bars"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["rbp1:c8bdaf43496c62d3a20bee160973a84e3c0c9a31bb9d105f1a47edde0dc55c37"]},{"name":"fact_kind","values":["ef1.regular_bar.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[14]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":14,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":14,\\"market_cutoff_ns\\":14,\\"namespace\\":\\"SYN\\",\\"path_source\\":{\\"input_id\\":\\"bars\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-BARS\\"},\\"phase_profile\\":\\"regular_no_auctions1\\",\\"population_sha256\\":\\"24e419ccb8841e0d53f025d6b0b76511b06b30115f61d66fc525e8eb99951605\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":2},\\"producer\\":\\"regular_bar_prices\\",\\"profile_id\\":\\"regular-bar-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-POPULATION\\"},\\"row_count\\":3,\\"sampling\\":\\"completed_bar_close\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"version\\":\\"ef1-regular-bar-population1\\"}"]},{"name":"known_at_ns","values":[14]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-POPULATION"}},"schema_version":"1"},"role":"population_proof"}]},"R08_unknown_before_first":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":14,"knowledge_cutoff_ns":14,"market_cutoff_ns":14,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.regular_bar_prices","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"S\\",\\"2026-10-20\\",10,30]],\\"target_date\\":\\"2026-10-20\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"regular_bar_prices\\",\\"selection\\":{\\"phase_profile\\":\\"regular_no_auctions1\\",\\"sampling\\":\\"completed_bar_close\\"},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":2},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":1,"governed_sessions":["S"],"target_session_id":"S"}},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:97b10ecabd7dbe43ce93fb7db74b448720c5903638aca175494f6a893a761b58"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"SYN-CALENDAR"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"start_ns","values":[10,11,12]},{"name":"end_ns","values":[11,12,14]},{"name":"open","values":[1200,1100,1300]},{"name":"close","values":[1210,1150,1250]},{"name":"volume","values":[null,1,1]},{"name":"known_at_ns","values":[11,12,14]}],"kind":"bar","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":14,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"bars","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-BARS"}},"schema_version":"1"},"role":"bars"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["rbp1:1c1e8ae47769ac515ac79155426813ee78df16aaa1b8005e8184f2988246cd6e"]},{"name":"fact_kind","values":["ef1.regular_bar.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[14]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":14,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":14,\\"market_cutoff_ns\\":14,\\"namespace\\":\\"SYN\\",\\"path_source\\":{\\"input_id\\":\\"bars\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-BARS\\"},\\"phase_profile\\":\\"regular_no_auctions1\\",\\"population_sha256\\":\\"43adeffa8d79fc4669699bcf9c935019852299c226fa8cf3cbe8b15a384a7a6d\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":2},\\"producer\\":\\"regular_bar_prices\\",\\"profile_id\\":\\"regular-bar-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population\\",\\"mapping_version\\":\\"fixture-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-POPULATION\\"},\\"row_count\\":3,\\"sampling\\":\\"completed_bar_close\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"version\\":\\"ef1-regular-bar-population1\\"}"]},{"name":"known_at_ns","values":[14]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population","mapping_version":"fixture-map1","snapshot_id":"R1","source_id":"SYN-POPULATION"}},"schema_version":"1"},"role":"population_proof"}]}}'


def _synthetic_packet(case_id: str) -> dict[str, object]:
    import json
    from typing import cast
    packets = cast(dict[str, dict[str, object]], json.loads(_SYNTHETIC))
    if type(case_id) is not str or case_id not in packets:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic regular BAR case")
    return packets[case_id]


def synthetic_regular_bar_price_config(case_id: str = "R01_two_independent_endpoints") -> ConfigSpec:
    """Detached literal config for an explicitly synthetic completed-BAR example."""
    import json
    return ConfigSpec.from_json(json.dumps(_synthetic_packet(case_id)["config"],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))


def synthetic_regular_bar_price_fixture(case_id: str = "R01_two_independent_endpoints") -> RegularBarPriceInputs:
    """Original synthetic facts and stipulated membership/proof publication clocks.

    This fixture supplies no observed-source capability or rights evidence. It
    never derives membership, endpoints or original availability from price time.
    """
    from typing import Any, cast
    from equity_feature_contracts import (
        AdjustmentSpec, Coverage, InputScope, IntervalCoverage, PriceUnit, SourceBinding,
    )
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
        batches.append(make_regular_bar_price_batch(DataKind(raw["kind"]), tuple(c["name"] for c in columns),
            tuple(zip(*(c["values"] for c in columns))), metadata=metadata))
    return RegularBarPriceInputs(batches[0], batches[1], batches[2],
        provenance=tuple("unavailable" if b is None else "synthetic" for b in batches))


__all__ += ["synthetic_regular_bar_price_config", "synthetic_regular_bar_price_fixture"]
