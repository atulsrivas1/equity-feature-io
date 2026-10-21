"""Lossless supplied regular first-trade inputs; no acquisition or price mathematics."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from equity_feature_contracts import (
    BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, DataKind, ErrorCode,
    validate_batch,
)
from equity_feature_contracts.inputs import Cell

_ROLES = ("calendar_provenance", "trades", "population_proof")
_ORIGINS = frozenset(("synthetic", "duckdb_backed_observed", "unavailable"))
_PROOF_COLUMNS = ("instrument_id", "session_id", "reference_id", "fact_kind",
                  "effective_start_ns", "effective_end_ns", "text", "known_at_ns")


def make_regular_first_trade_price_batch(kind: DataKind, column_order: tuple[str, ...],
                            rows: tuple[tuple[Cell, ...], ...], *,
                            metadata: BatchMetadata) -> CanonicalBatch:
    """Convert exact supplied rectangular cells, retaining order and metadata.

    No sorting, filtering, field filling, unit conversion, timestamp inference or
    proof canonicalization occurs. Closed proof grammar and mathematical identity
    admission belong to the pure regular first-trade producer. Generic canonical validation
    may refuse an invalid original row before that callback is reached.
    """
    if (type(kind) is not DataKind
            or kind not in (DataKind.REFERENCE, DataKind.TRADE)
            or type(column_order) is not tuple
            or any(type(name) is not str for name in column_order)
            or type(rows) is not tuple
            or any(type(row) is not tuple or len(row) != len(column_order) for row in rows)
            or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied regular first-trade rectangle required")
    result = CanonicalBatch(kind, tuple(Column(name, tuple(row[i] for row in rows))
                                       for i, name in enumerate(column_order)), metadata)
    validate_batch(result, required_fields=())
    return result


def make_regular_trade_population_proof(row: Mapping[str, Cell], *,
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
    return make_regular_first_trade_price_batch(DataKind.REFERENCE, _PROOF_COLUMNS,
                                   (tuple(row[name] for name in _PROOF_COLUMNS),),
                                   metadata=metadata)


@dataclass(frozen=True)
class RegularFirstTradePriceInputs:
    """Three fixed nullable slots; present-only batches never replace pure slots.

    Origins are explicit caller declarations, not capability or rights evidence.
    Observed-source admission remains unqualified. Retain real source identities;
    use explicit unavailable delivery when a truthful proof cannot be supplied.
    """
    calendar_provenance: CanonicalBatch | None = None
    trades: CanonicalBatch | None = None
    population_proof: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable",) * 3

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 3:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly three regular first-trade origins required")
        kinds = ((DataKind.REFERENCE,), (DataKind.TRADE,), (DataKind.REFERENCE,))
        for batch, origin, allowed in zip(self.slots, self.provenance, kinds):
            if (type(origin) is not str or origin not in _ORIGINS
                    or (batch is None) != (origin == "unavailable")):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
            if batch is not None:
                if type(batch) is not CanonicalBatch or batch.kind not in allowed:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Regular first-trade role kind mismatch")
                validate_batch(batch, required_fields=())
        if len({b.metadata.source.input_id for b in self.batches}) != len(self.batches):
            raise ContractError(ErrorCode.DUPLICATE, "Distinct regular first-trade input IDs required")
        if len({b.metadata.namespace for b in self.batches}) > 1:
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One regular first-trade namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return _ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.calendar_provenance, self.trades, self.population_proof)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in self.slots if batch is not None)


__all__ = ["RegularFirstTradePriceInputs", "make_regular_first_trade_price_batch", "make_regular_trade_population_proof"]


# Original synthetic supplied facts/config only; independent oracle expectations are not embedded.
_SYNTHETIC = '{"R001":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":14,"knowledge_cutoff_ns":14,"market_cutoff_ns":14,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.regular_first_trade_price","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"S\\",\\"2026-10-21\\",10,30]],\\"target_date\\":\\"2026-10-21\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"regular_first_trade_price\\",\\"selection\\":{\\"phase_profile\\":\\"regular_no_auctions1\\",\\"sampling\\":\\"eligible_trade\\"},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":2},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":1,"governed_sessions":["S"],"target_session_id":"S"}},"entity":{"instrument_id":"X","session_id":"S"},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:8b8d169ebc2583e10b52894d44526f7cfafa361d4b6f4dc0dd8506f653139440"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar_provenance-1","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"synthetic-calendar_provenance"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"event_ns","values":[10,11,12]},{"name":"order_key","values":[0,1,2]},{"name":"event_id","values":["t0","t1","t2"]},{"name":"eligible","values":[false,true,true]},{"name":"price","values":[99,101,103]},{"name":"size","values":[0,5,4]},{"name":"condition","values":["regular","regular","regular"]},{"name":"known_at_ns","values":[10,11,12]}],"kind":"trade","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":14,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"trades-1","mapping_version":"synthetic-map1","snapshot_id":"SYN1","source_id":"synthetic-trades"}},"schema_version":"1"},"role":"trades"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["rtp1:cd7b3c3a863d5acbcad0db84e58381954d8e22eddff8853194cb29b8f8ca9a67"]},{"name":"fact_kind","values":["ef1.regular_trade.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[14]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":14,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":14,\\"market_cutoff_ns\\":14,\\"namespace\\":\\"SYN\\",\\"phase_profile\\":\\"regular_no_auctions1\\",\\"population_sha256\\":\\"fe8b27b364a3cf186078471ebb2b79366250d8b4664fa6ffe6c283340d03a845\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":2},\\"producer\\":\\"regular_first_trade_price\\",\\"profile_id\\":\\"regular-trade-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population_proof-1\\",\\"mapping_version\\":\\"synthetic-map1\\",\\"snapshot_id\\":\\"SYN1\\",\\"source_id\\":\\"synthetic-population_proof\\"},\\"row_count\\":3,\\"sampling\\":\\"eligible_trade\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"trades_source\\":{\\"input_id\\":\\"trades-1\\",\\"mapping_version\\":\\"synthetic-map1\\",\\"snapshot_id\\":\\"SYN1\\",\\"source_id\\":\\"synthetic-trades\\"},\\"version\\":\\"ef1-regular-trade-population1\\"}"]},{"name":"known_at_ns","values":[14]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population_proof-1","mapping_version":"synthetic-map1","snapshot_id":"SYN1","source_id":"synthetic-population_proof"}},"schema_version":"1"},"role":"population_proof"}],"synthetic":true},"R019":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":14,"knowledge_cutoff_ns":14,"market_cutoff_ns":14,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.regular_first_trade_price","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"S\\",\\"2026-10-21\\",10,30]],\\"target_date\\":\\"2026-10-21\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"regular_first_trade_price\\",\\"selection\\":{\\"phase_profile\\":\\"regular_no_auctions1\\",\\"sampling\\":\\"eligible_trade\\"},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":2},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":1,"governed_sessions":["S"],"target_session_id":"S"}},"entity":{"instrument_id":"X","session_id":"S"},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:8b8d169ebc2583e10b52894d44526f7cfafa361d4b6f4dc0dd8506f653139440"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar_provenance-1","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"synthetic-calendar_provenance"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"event_ns","values":[10,11,12]},{"name":"order_key","values":[0,1,2]},{"name":"event_id","values":["t0","t1","t2"]},{"name":"eligible","values":[false,true,true]},{"name":"price","values":[99,101,103]},{"name":"size","values":[0,5,4]},{"name":"condition","values":["regular","regular","regular"]},{"name":"known_at_ns","values":[10,15,12]}],"kind":"trade","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":2},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":14,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"trades-1","mapping_version":"synthetic-map1","snapshot_id":"SYN1","source_id":"synthetic-trades"}},"schema_version":"1"},"role":"trades"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["rtp1:cd7b3c3a863d5acbcad0db84e58381954d8e22eddff8853194cb29b8f8ca9a67"]},{"name":"fact_kind","values":["ef1.regular_trade.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[14]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":14,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":14,\\"market_cutoff_ns\\":14,\\"namespace\\":\\"SYN\\",\\"phase_profile\\":\\"regular_no_auctions1\\",\\"population_sha256\\":\\"fe8b27b364a3cf186078471ebb2b79366250d8b4664fa6ffe6c283340d03a845\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":2},\\"producer\\":\\"regular_first_trade_price\\",\\"profile_id\\":\\"regular-trade-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population_proof-1\\",\\"mapping_version\\":\\"synthetic-map1\\",\\"snapshot_id\\":\\"SYN1\\",\\"source_id\\":\\"synthetic-population_proof\\"},\\"row_count\\":3,\\"sampling\\":\\"eligible_trade\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"trades_source\\":{\\"input_id\\":\\"trades-1\\",\\"mapping_version\\":\\"synthetic-map1\\",\\"snapshot_id\\":\\"SYN1\\",\\"source_id\\":\\"synthetic-trades\\"},\\"version\\":\\"ef1-regular-trade-population1\\"}"]},{"name":"known_at_ns","values":[14]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population_proof-1","mapping_version":"synthetic-map1","snapshot_id":"SYN1","source_id":"synthetic-population_proof"}},"schema_version":"1"},"role":"population_proof"}],"synthetic":true}}'


def _synthetic_packet(case_id: str) -> dict[str, object]:
    import json
    from typing import cast
    packets = cast(dict[str, dict[str, object]], json.loads(_SYNTHETIC))
    if type(case_id) is not str or case_id not in packets:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic regular first-trade case")
    return packets[case_id]


def synthetic_regular_first_trade_price_config(case_id: str = "R001") -> ConfigSpec:
    """Detached literal config for an explicitly synthetic first-trade example."""
    import json
    return ConfigSpec.from_json(json.dumps(_synthetic_packet(case_id)["config"],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))


def synthetic_regular_first_trade_price_fixture(case_id: str = "R001") -> RegularFirstTradePriceInputs:
    """Original synthetic facts and stipulated membership/proof publication clocks.

    This fixture supplies no observed-source capability or rights evidence. It
    never derives membership, firstness or original availability from price time.
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
        batches.append(make_regular_first_trade_price_batch(DataKind(raw["kind"]), tuple(c["name"] for c in columns),
            tuple(zip(*(c["values"] for c in columns))), metadata=metadata))
    return RegularFirstTradePriceInputs(batches[0], batches[1], batches[2],
        provenance=tuple("unavailable" if b is None else "synthetic" for b in batches))


__all__ += ["synthetic_regular_first_trade_price_config", "synthetic_regular_first_trade_price_fixture"]
