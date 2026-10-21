"""Lossless supplied endpoint inputs; no acquisition, authentication or gap math."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from equity_feature_contracts import (
    BatchMetadata, CanonicalBatch, Column, ConfigSpec, ContractError, DataKind, ErrorCode,
    validate_batch,
)
from equity_feature_contracts.inputs import Cell

_ROLES = ("calendar_provenance", "path", "prior_close", "population_proof")
_ORIGINS = frozenset(("synthetic", "duckdb_backed_observed", "unavailable"))
_PROOF_COLUMNS = ("instrument_id", "session_id", "reference_id", "fact_kind",
                  "effective_start_ns", "effective_end_ns", "text", "known_at_ns")


def make_gap_endpoint_batch(kind: DataKind, column_order: tuple[str, ...],
                            rows: tuple[tuple[Cell, ...], ...], *,
                            metadata: BatchMetadata) -> CanonicalBatch:
    """Convert exact supplied rectangular cells, retaining order and metadata.

    No sorting, filtering, field filling, unit conversion, timestamp inference or
    proof canonicalization occurs. Closed proof grammar and mathematical identity
    admission belong to the pure endpoint producer. Generic canonical validation
    may refuse an invalid original row before that callback is reached.
    """
    if (type(kind) is not DataKind
            or kind not in (DataKind.REFERENCE, DataKind.TRADE, DataKind.BAR, DataKind.DAILY)
            or type(column_order) is not tuple
            or any(type(name) is not str for name in column_order)
            or type(rows) is not tuple
            or any(type(row) is not tuple or len(row) != len(column_order) for row in rows)
            or type(metadata) is not BatchMetadata):
        raise ContractError(ErrorCode.INVALID_SCHEMA, "Exact supplied endpoint rectangle required")
    result = CanonicalBatch(kind, tuple(Column(name, tuple(row[i] for row in rows))
                                       for i, name in enumerate(column_order)), metadata)
    validate_batch(result, required_fields=())
    return result


def make_gap_population_proof(row: Mapping[str, Cell], *,
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
    return make_gap_endpoint_batch(DataKind.REFERENCE, _PROOF_COLUMNS,
                                   (tuple(row[name] for name in _PROOF_COLUMNS),),
                                   metadata=metadata)


@dataclass(frozen=True)
class GapEndpointInputs:
    """Four fixed nullable slots; present-only batches never replace pure slots.

    Origins are explicit caller declarations, not capability or rights evidence.
    Observed-source admission remains unqualified. Retain real source identities;
    use explicit unavailable delivery when a truthful proof cannot be supplied.
    """
    calendar_provenance: CanonicalBatch | None = None
    path: CanonicalBatch | None = None
    prior_close: CanonicalBatch | None = None
    population_proof: CanonicalBatch | None = None
    provenance: tuple[str, ...] = ("unavailable",) * 4

    def __post_init__(self) -> None:
        if type(self.provenance) is not tuple or len(self.provenance) != 4:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "Exactly four endpoint origins required")
        kinds = ((DataKind.REFERENCE,), (DataKind.TRADE, DataKind.BAR),
                 (DataKind.DAILY,), (DataKind.REFERENCE,))
        for batch, origin, allowed in zip(self.slots, self.provenance, kinds):
            if (type(origin) is not str or origin not in _ORIGINS
                    or (batch is None) != (origin == "unavailable")):
                raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "Origin must match actual delivery")
            if batch is not None:
                if type(batch) is not CanonicalBatch or batch.kind not in allowed:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "Endpoint role kind mismatch")
                validate_batch(batch, required_fields=())
        if len({b.metadata.source.input_id for b in self.batches}) != len(self.batches):
            raise ContractError(ErrorCode.DUPLICATE, "Distinct endpoint input IDs required")
        if len({b.metadata.namespace for b in self.batches}) > 1:
            raise ContractError(ErrorCode.INCONSISTENT_IDENTITY, "One endpoint namespace required")

    @property
    def roles(self) -> tuple[str, ...]:
        return _ROLES

    @property
    def slots(self) -> tuple[CanonicalBatch | None, ...]:
        return (self.calendar_provenance, self.path, self.prior_close, self.population_proof)

    @property
    def batches(self) -> tuple[CanonicalBatch, ...]:
        return tuple(batch for batch in self.slots if batch is not None)


__all__ = ["GapEndpointInputs", "make_gap_endpoint_batch", "make_gap_population_proof"]


# Original synthetic source declarations copied from the independent frozen oracle.
_SYNTHETIC = '{"E01_up_reversal":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":14,"knowledge_cutoff_ns":14,"market_cutoff_ns":14,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.path_gap_endpoint","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"P\\",\\"2026-10-19\\",-10,0],[\\"S\\",\\"2026-10-20\\",10,30]],\\"target_date\\":\\"2026-10-20\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"path_gap_endpoint\\",\\"selection\\":{\\"sampling\\":\\"eligible_trade\\"},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":0},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":2,"governed_sessions":["P","S"],"target_session_id":"S"}},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:dee0e2480123766cb9c051c1f38e5d3ac98e0c788aff175f733a1ea55c14cf61"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[-10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[-10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"SYN-CALENDAR"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X","X"]},{"name":"session_id","values":["S","S","S"]},{"name":"event_ns","values":[10,11,12]},{"name":"order_key","values":[0,0,0]},{"name":"event_id","values":["a","b","c"]},{"name":"eligible","values":[true,true,true]},{"name":"price","values":[12,10,11]},{"name":"size","values":[1,1,1]},{"name":"known_at_ns","values":[10,11,12]}],"kind":"trade","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":3,"observed":3},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":0},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":14,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"path","mapping_version":"ef1-path-map1","snapshot_id":"R1","source_id":"SYN-PATH"}},"schema_version":"1"},"role":"path"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["P"]},{"name":"start_ns","values":[-10]},{"name":"end_ns","values":[0]},{"name":"close","values":[10]},{"name":"known_at_ns","values":[0]}],"kind":"daily","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":0},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":0,"include_closing_auction":false,"include_opening_auction":false,"start_ns":-10},"source":{"input_id":"prior","mapping_version":"ef1-path-map1","snapshot_id":"R1","source_id":"SYN-DAILY"}},"schema_version":"1"},"role":"prior_close"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["pop1:ac4a12380f4d89145f6cfe4a0a60feeddbe0dd955f4773a82984411f2071f5fd"]},{"name":"fact_kind","values":["ef1.gap.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[14]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":14,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":14,\\"market_cutoff_ns\\":14,\\"namespace\\":\\"SYN\\",\\"path_source\\":{\\"input_id\\":\\"path\\",\\"mapping_version\\":\\"ef1-path-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-PATH\\"},\\"population_sha256\\":\\"6dc72c9e50e64c6d1fa5be7964db406e4c6a55e31dfda2f2ded0e5c4305d75a6\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":0},\\"profile_id\\":\\"gap-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population\\",\\"mapping_version\\":\\"ef1-gap-population-map1\\",\\"snapshot_id\\":\\"SYN-GAP-POPULATION-R1\\",\\"source_id\\":\\"SYN-GAP-POPULATION\\"},\\"row_count\\":3,\\"sampling\\":\\"eligible_trade\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"version\\":\\"ef1-gap-population1\\"}"]},{"name":"known_at_ns","values":[14]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population","mapping_version":"ef1-gap-population-map1","snapshot_id":"SYN-GAP-POPULATION-R1","source_id":"SYN-GAP-POPULATION"}},"schema_version":"1"},"role":"population_proof"}]},"E26_bar_close_at_cutoff":{"config":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"algorithm_version":"v1","availability":{"evaluation_ns":14,"knowledge_cutoff_ns":14,"market_cutoff_ns":14,"mode":"known_at","reconstruction_reason":null},"identity":"ef1.path_gap_endpoint","parameters":[{"name":"ef1_context_json","value":"{\\"calendar\\":{\\"calendar_id\\":\\"SYN-CAL\\",\\"early_close\\":false,\\"revision\\":\\"R1\\",\\"scheduled_close_ns\\":30,\\"segments\\":[[\\"regular\\",10,30]],\\"sessions\\":[[\\"P\\",\\"2026-10-19\\",-10,0],[\\"S\\",\\"2026-10-20\\",10,30]],\\"target_date\\":\\"2026-10-20\\",\\"timezone\\":\\"UTC\\"},\\"producer\\":\\"path_gap_endpoint\\",\\"selection\\":{\\"sampling\\":\\"completed_bar_close\\"},\\"version\\":\\"ef1-context1\\"}"}],"price_unit":{"currency":"USD","scale":0},"schema_version":"1","session":{"close_ns":30,"early_close":false,"include_closing_auction":false,"include_opening_auction":false,"intervals":[],"namespace":"SYN","open_ns":10,"scheduled_close_ns":30,"session_id":"S","timezone_label":"UTC"},"window":{"anchor":"completed_eod","count":2,"governed_sessions":["P","S"],"target_session_id":"S"}},"role_slots":[{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["c1:dee0e2480123766cb9c051c1f38e5d3ac98e0c788aff175f733a1ea55c14cf61"]},{"name":"fact_kind","values":["ef1.calendar.provenance"]},{"name":"effective_start_ns","values":[-10]},{"name":"effective_end_ns","values":[30]},{"name":"text","values":["supplied_schedule"]},{"name":"known_at_ns","values":[-10]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"calendar","mapping_version":"ef1-reference-map1","snapshot_id":"R1","source_id":"SYN-CALENDAR"}},"schema_version":"1"},"role":"calendar_provenance"},{"batch":{"columns":[{"name":"instrument_id","values":["X","X"]},{"name":"session_id","values":["S","S"]},{"name":"start_ns","values":[10,11]},{"name":"end_ns","values":[11,14]},{"name":"open","values":[12,12]},{"name":"high","values":[12,12]},{"name":"low","values":[12,9]},{"name":"close","values":[12,11]},{"name":"volume","values":[1,1]},{"name":"known_at_ns","values":[11,14]}],"kind":"bar","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":2,"observed":2},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":0},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":14,"include_closing_auction":false,"include_opening_auction":false,"start_ns":10},"source":{"input_id":"path","mapping_version":"ef1-path-map1","snapshot_id":"R1","source_id":"SYN-PATH"}},"schema_version":"1"},"role":"path"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["P"]},{"name":"start_ns","values":[-10]},{"name":"end_ns","values":[0]},{"name":"close","values":[10]},{"name":"known_at_ns","values":[0]}],"kind":"daily","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":{"currency":"USD","scale":0},"quantity_unit":"shares","sampling":"none","scope":{"eligibility_policy":"supplied_path","end_ns":0,"include_closing_auction":false,"include_opening_auction":false,"start_ns":-10},"source":{"input_id":"prior","mapping_version":"ef1-path-map1","snapshot_id":"R1","source_id":"SYN-DAILY"}},"schema_version":"1"},"role":"prior_close"},{"batch":{"columns":[{"name":"instrument_id","values":["X"]},{"name":"session_id","values":["S"]},{"name":"reference_id","values":["pop1:9314f95882dc724eb3660cc3fe71f906bd28f55b63efae4ee577f137f9444938"]},{"name":"fact_kind","values":["ef1.gap.population.v1"]},{"name":"effective_start_ns","values":[10]},{"name":"effective_end_ns","values":[14]},{"name":"text","values":["{\\"adjustment\\":{\\"action_snapshot\\":\\"none\\",\\"anchor\\":\\"none\\",\\"basis\\":\\"raw\\",\\"policy_version\\":\\"raw-v1\\"},\\"complete\\":true,\\"eligibility_policy\\":\\"supplied_path\\",\\"end_ns\\":14,\\"include_closing_auction\\":false,\\"include_opening_auction\\":false,\\"instrument_id\\":\\"X\\",\\"knowledge_cutoff_ns\\":14,\\"market_cutoff_ns\\":14,\\"namespace\\":\\"SYN\\",\\"path_source\\":{\\"input_id\\":\\"path\\",\\"mapping_version\\":\\"ef1-path-map1\\",\\"snapshot_id\\":\\"R1\\",\\"source_id\\":\\"SYN-PATH\\"},\\"population_sha256\\":\\"257509ac48880a291e5851a3cc00c26bc56f55d5be25ca678a969e4c914fe2f0\\",\\"price_unit\\":{\\"currency\\":\\"USD\\",\\"scale\\":0},\\"profile_id\\":\\"gap-membership-asof1\\",\\"proof_source\\":{\\"input_id\\":\\"population\\",\\"mapping_version\\":\\"ef1-gap-population-map1\\",\\"snapshot_id\\":\\"SYN-GAP-POPULATION-R1\\",\\"source_id\\":\\"SYN-GAP-POPULATION\\"},\\"row_count\\":2,\\"sampling\\":\\"completed_bar_close\\",\\"session_id\\":\\"S\\",\\"start_ns\\":10,\\"version\\":\\"ef1-gap-population1\\"}"]},{"name":"known_at_ns","values":[14]}],"kind":"reference","metadata":{"adjustment":{"action_snapshot":"none","anchor":"none","basis":"raw","policy_version":"raw-v1"},"coverage":{"complete":true,"expected":1,"observed":1},"duplicate_policy":"reject","interval_coverage":[],"namespace":"SYN","ordering":"declared","price_unit":null,"quantity_unit":"shares","sampling":"none","scope":null,"source":{"input_id":"population","mapping_version":"ef1-gap-population-map1","snapshot_id":"SYN-GAP-POPULATION-R1","source_id":"SYN-GAP-POPULATION"}},"schema_version":"1"},"role":"population_proof"}]}}'


def _synthetic_packet(case_id: str) -> dict[str, object]:
    import json
    from typing import cast
    packets = cast(dict[str, dict[str, object]], json.loads(_SYNTHETIC))
    if type(case_id) is not str or case_id not in packets:
        raise ContractError(ErrorCode.INVALID_CONFIG, "Unknown explicit synthetic endpoint case")
    return packets[case_id]


def synthetic_gap_endpoint_config(case_id: str = "E01_up_reversal") -> ConfigSpec:
    """Detached literal config for an explicitly synthetic trade or bar example."""
    import json
    from equity_feature_contracts import ConfigSpec
    return ConfigSpec.from_json(json.dumps(_synthetic_packet(case_id)["config"],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))


def synthetic_gap_endpoint_fixture(case_id: str = "E01_up_reversal") -> GapEndpointInputs:
    """Literal source facts, including an independently stipulated proof timeline.

    These are original synthetic examples, never renamed observed input. No output
    oracle, population generation or inference from event/file time occurs here.
    """
    from typing import Any, cast
    from equity_feature_contracts import AdjustmentSpec, Coverage, InputScope, PriceUnit, SourceBinding
    packet = cast(dict[str, Any], _synthetic_packet(case_id))
    batches = []
    for slot in packet["role_slots"]:
        raw = slot["batch"]
        m = raw["metadata"]
        metadata = BatchMetadata(namespace=m["namespace"], source=SourceBinding(**m["source"]),
            coverage=Coverage(**m["coverage"]), price_unit=None if m["price_unit"] is None else PriceUnit(**m["price_unit"]),
            adjustment=AdjustmentSpec(**m["adjustment"]), sampling=m["sampling"], quantity_unit=m["quantity_unit"],
            ordering=m["ordering"], duplicate_policy=m["duplicate_policy"],
            scope=None if m["scope"] is None else InputScope(**m["scope"]), interval_coverage=())
        batches.append(make_gap_endpoint_batch(DataKind(raw["kind"]), tuple(c["name"] for c in raw["columns"]),
            tuple(zip(*(c["values"] for c in raw["columns"]))), metadata=metadata))
    return GapEndpointInputs(batches[0], batches[1], batches[2], batches[3],
                             provenance=("synthetic",) * 4)


__all__ += ["synthetic_gap_endpoint_config", "synthetic_gap_endpoint_fixture"]
