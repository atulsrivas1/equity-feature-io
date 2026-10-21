"""Actual endpoint calculations, immutable full results and unchanged sink."""
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from equity_feature_contracts import ConfigSpec, ContractError, EntityKey
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import decode_result, encode_result, prepare_publication, publish
from equity_features.ef1 import compute_ef1
from gap_endpoint_support import causal_packets, packets, packet_inputs, original_batch


def normalized(value):
    return json.loads(json.dumps(asdict(value)))


def config_of(packet):
    return ConfigSpec.from_json(json.dumps(packet["config"], ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def calculate(packet):
    config = config_of(packet)
    return compute_ef1(packet_inputs(packet).slots, config,
                       entity=EntityKey(**packet["entity"]))


class GapEndpointCompositionTests(unittest.TestCase):
    def test_reviewed_successor_changes_exactly_two_quality_leaves(self):
        old, new = packets(), causal_packets()
        self.assertEqual(len(old), 114)
        self.assertEqual(len(new), 114)
        changed = []
        for before, after in zip(old, new):
            if before != after:
                changed.append(before["id"])
                self.assertEqual(before["id"], "E28_prior_late_even_zero_gap")
                owned = json.loads(json.dumps(before))
                owned["expected_result"]["quality"][0]["status"] = "missing_input"
                owned["expected_result"]["quality"][0]["reasons"] = ["future_knowledge"]
                self.assertEqual(owned, after)
        self.assertEqual(changed, ["E28_prior_late_even_zero_gap"])

    def test_all_114_targets_with_71_full_result_sdk_roundtrips(self):
        full = pure_calls = constructor_refusals = 0
        for packet in causal_packets():
            with self.subTest(case=packet["id"]):
                if packet["expected_result"] is None:
                    # Direct original slots intentionally bypass bundle validation:
                    # callback's canonical validation remains the actual earliest
                    # pure-entry stage for those controls; no semantic credit.
                    if packet["id"] == "E30_unknown_expected":
                        with self.assertRaises(ContractError) as caught:
                            tuple(original_batch(s["batch"], convert=False) for s in packet["role_slots"])
                        constructor_refusals += 1
                    else:
                        slots = tuple(original_batch(s["batch"], convert=False) for s in packet["role_slots"])
                        config = config_of(packet)
                        with self.assertRaises(ContractError) as caught:
                            compute_ef1(slots, config, entity=EntityKey(**packet["entity"]))
                        pure_calls += 1
                    self.assertEqual(caught.exception.code.value, packet["expected_error"]["code"])
                else:
                    result = calculate(packet)
                    self.assertEqual(normalized(result), packet["expected_result"])
                    self.assertEqual(normalized(decode_result(encode_result(result))), packet["expected_result"])
                    full += 1
        self.assertEqual((full, pure_calls, constructor_refusals), (71, 42, 1))

    def test_all_71_new_output_sink_readbacks_retry_close_and_reopen(self):
        limits = SinkRequirements(max_results=1, max_chunk_bytes=1048576, max_total_bytes=1048576,
                                  max_result_cells=2, max_evidence_rows=5)
        count = 0
        for packet in causal_packets():
            if packet["expected_result"] is None:
                continue
            with self.subTest(case=packet["id"]), TemporaryDirectory() as temp:
                result = calculate(packet)
                self.assertEqual(normalized(result), packet["expected_result"])
                publication = prepare_publication((result,), destination_scope="synthetic-gap-endpoint",
                    generation_id=packet["id"], job_id="gap-endpoint-fixture", partition_id="X-S", limits=limits)
                output = Path(temp) / "new-gap-endpoint-output.duckdb"
                self.assertFalse(output.exists())
                with DuckDBSink(output, "synthetic-gap-endpoint", limits=limits) as sink:
                    receipt = publish(sink, publication, (result,))
                    self.assertEqual(normalized(sink.read(receipt)[0]), packet["expected_result"])
                    self.assertEqual(publish(sink, publication, (result,)), receipt)
                with DuckDBSink(output, "synthetic-gap-endpoint", limits=limits) as sink:
                    self.assertEqual(sink.lookup(receipt.idempotency_key).receipt, receipt)
                    self.assertEqual(normalized(sink.read(receipt)[0]), packet["expected_result"])
                    self.assertEqual(encode_result(sink.read(receipt)[0]), encode_result(result))
                count += 1
        self.assertEqual(count, 71)


if __name__ == "__main__":
    unittest.main()
