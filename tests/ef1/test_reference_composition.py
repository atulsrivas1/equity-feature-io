"""Independent frozen reference packets and unchanged full-result sink boundary.

Authored under the runtime reservation; these are prospective checks, not results.
"""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, Coverage,
    DataKind, EntityKey, InputScope, IntervalCoverage, PriceUnit, SourceBinding,
)
from equity_feature_duckdb.ef1 import (
    ReferenceActionInputs, ReferenceClassificationInputs,
    synthetic_reference_action_fixture, synthetic_reference_classification_fixture,
)
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import compute_ef1

PACKETS = Path(__file__).with_name("reference_contract_packets.json")
PACKET_SHA = "5160d91fc966137a1728c6c26dde15d6772ea35811efc4ea9832b2f7460a28f0"


def document():
    raw = PACKETS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKET_SHA
    return json.loads(raw)["canonical_literal_packets"]


def normalized(value):
    return json.loads(json.dumps(asdict(value)))


def original_batch(raw):
    if raw is None:
        return None
    meta = dict(raw["metadata"])
    meta["source"] = SourceBinding(**meta["source"])
    meta["coverage"] = Coverage(**meta["coverage"])
    meta["adjustment"] = AdjustmentSpec(**meta["adjustment"])
    meta["price_unit"] = None if meta["price_unit"] is None else PriceUnit(**meta["price_unit"])
    meta["scope"] = None if meta["scope"] is None else InputScope(**meta["scope"])
    meta["interval_coverage"] = tuple(IntervalCoverage(**{**row, "coverage": Coverage(**row["coverage"])})
                                      for row in meta["interval_coverage"])
    return CanonicalBatch(DataKind(raw["kind"]), tuple(Column(c["name"], tuple(c["values"])) for c in raw["columns"]),
                          BatchMetadata(**meta))


def packet_inputs(packet):
    slots = tuple(original_batch(row["batch"]) for row in packet["role_slots"])
    modes = tuple("unavailable" if batch is None else "synthetic" for batch in slots)
    cls = ReferenceActionInputs if len(slots) == 6 else ReferenceClassificationInputs
    return cls(*slots, modes)


def calculate(packet):
    inputs = packet_inputs(packet)
    config = ConfigSpec.from_json(packet["canonical_config_json"])
    assert config.digest() == packet["config_digest"]
    return compute_ef1(inputs.slots, config, entity=EntityKey(**packet["entity"]))


class ReferenceCompositionTests(unittest.TestCase):
    def test_all_55_independent_full_packets_and_complete_result_projection(self):
        packets = document()
        self.assertEqual(len(packets), 55)
        self.assertEqual(len({p["id"] for p in packets}), 55)
        for packet in packets:
            with self.subTest(case=packet["id"]):
                actual = calculate(packet)
                self.assertEqual(normalized(actual), packet["expected_result"])
                originals = {r["role"]: r["batch"]["metadata"] for r in packet["role_slots"] if r["batch"] is not None}
                self.assertEqual({i.role: normalized(i.metadata) for i in actual.metadata.inputs}, originals)

    def test_synthetic_fixtures_match_original_r01_r02_r03_full_sources(self):
        packets = {p["id"]: p for p in document()}
        for name, actual in (("R01", synthetic_reference_classification_fixture()),
                             ("R02", synthetic_reference_classification_fixture("R02")),
                             ("R03", synthetic_reference_action_fixture())):
            with self.subTest(case=name):
                expected = packet_inputs(packets[name + "-CANONICAL"])
                self.assertEqual(actual, expected)

    def test_all_55_full_sink_readbacks_idempotence_reopen_and_causal_witnesses(self):
        limits = SinkRequirements(max_results=1, max_chunk_bytes=1048576, max_total_bytes=1048576,
                                  max_result_cells=3, max_evidence_rows=128)
        for packet in document():
            with self.subTest(case=packet["id"]), TemporaryDirectory() as temp:
                result = calculate(packet)
                self.assertEqual(normalized(result), packet["expected_result"])
                publication = prepare_publication((result,), destination_scope="synthetic-reference",
                    generation_id=packet["id"], job_id="reference-fixture", partition_id="X-S", limits=limits)
                output = Path(temp) / "new-reference-results.duckdb"
                with DuckDBSink(output, "synthetic-reference", limits=limits) as sink:
                    receipt = publish(sink, publication, (result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]), encode_result(result))
                    self.assertEqual(publish(sink, publication, (result,)), receipt)
                with DuckDBSink(output, "synthetic-reference", limits=limits) as sink:
                    self.assertEqual(sink.lookup(receipt.idempotency_key).receipt, receipt)
                    restored = sink.read(receipt)[0]
                    self.assertEqual(normalized(restored), packet["expected_result"])
                    self.assertEqual(encode_result(restored), encode_result(result))

    def test_every_omitted_role_keeps_actual_original_binding_subset(self):
        for original in (synthetic_reference_classification_fixture(), synthetic_reference_action_fixture()):
            config_packet = next(p for p in document() if p["id"] == ("R03-CANONICAL" if len(original.slots) == 6 else "R01-CANONICAL"))
            config = ConfigSpec.from_json(config_packet["canonical_config_json"])
            for index, role in enumerate(original.roles):
                modes = tuple("unavailable" if n == index else "synthetic" for n in range(len(original.slots)))
                missing = replace(original, **{role: None, "provenance": modes})
                result = compute_ef1(missing.slots, config, entity=EntityKey("X", "S"))
                self.assertEqual({b.role for b in result.metadata.inputs}, set(original.roles) - {role})
                self.assertTrue(all(b.metadata == getattr(original, b.role).metadata for b in result.metadata.inputs))

    def test_action_gate_never_changes_market_prices_sizes_or_original_factors(self):
        packet = next(p for p in document() if p["id"] == "R03-CANONICAL")
        inputs = packet_inputs(packet)
        before = tuple(normalized(b) for b in inputs.batches)
        result = compute_ef1(inputs.slots, ConfigSpec.from_json(packet["canonical_config_json"]), entity=EntityKey("X", "S"))
        self.assertEqual(tuple(normalized(b) for b in inputs.batches), before)
        self.assertEqual(inputs.market.column("price").values, (100,))
        self.assertEqual(inputs.market.column("size").values, (10,))
        self.assertEqual({v.feature_id for v in result.values},
                         {"reference.gate.action_reason", "reference.gate.action_state"})
        for kind in (DataKind.BAR, DataKind.DAILY):
            interval = CanonicalBatch(kind, tuple(Column(name, (value,)) for name, value in (
                ("instrument_id", "X"), ("session_id", "S"), ("start_ns", 10), ("end_ns", 20),
                ("open", 100), ("high", 100), ("low", 100), ("close", 100), ("volume", 10),
                ("actual_notional", 1000), ("known_at_ns", 20))), inputs.market.metadata)
            alternative = replace(inputs, market=interval)
            gate = compute_ef1(alternative.slots, ConfigSpec.from_json(packet["canonical_config_json"]),
                               entity=EntityKey("X", "S"))
            self.assertEqual({v.feature_id: v.values[0] for v in gate.values},
                             {"reference.gate.action_reason": "none", "reference.gate.action_state": "passed"})
            self.assertEqual(next(i.kind for i in gate.metadata.inputs if i.role == "market"), kind)
            # Gate admission is field-agnostic; absent numeric columns stay absent.
            sparse = replace(interval, columns=tuple(c for c in interval.columns if c.name in
                ("instrument_id", "session_id", "start_ns", "end_ns", "known_at_ns")))
            gate = compute_ef1(replace(alternative, market=sparse).slots,
                ConfigSpec.from_json(packet["canonical_config_json"]), entity=EntityKey("X", "S"))
            self.assertEqual({v.values[0] for v in gate.values}, {"none", "passed"})


if __name__ == "__main__":
    unittest.main()
