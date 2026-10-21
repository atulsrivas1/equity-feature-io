"""Actual regular BAR producer against immutable full goldens and unchanged DuckDB sink."""
from contextlib import nullcontext
from dataclasses import asdict
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
import unittest
from equity_feature_contracts import ConfigSpec, ContractError, EntityKey
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import decode_result, encode_result, prepare_publication, publish
from equity_features.ef1 import compute_ef1
from regular_bar_prices_support import packets, packet_inputs, original_batch


def normalized(value): return json.loads(json.dumps(asdict(value)))


def output_directory(case):
    # Qualification may retain private synthetic outputs and stable lock sidecars.
    # Ordinary isolated unit runs still use their usual temporary directory.
    parent = os.environ.get("EF1_REGULAR_BAR_IO_OUTPUT_ROOT")
    return TemporaryDirectory() if parent is None else nullcontext(mkdtemp(prefix=case + "-", dir=parent))


def calculate(packet):
    inputs = packet_inputs(packet)
    config = ConfigSpec.from_json(json.dumps(packet['config'],ensure_ascii=True,sort_keys=True,separators=(',',':')))
    return compute_ef1(inputs.slots,config,entity=EntityKey('X',config.session.session_id))


class RegularBarPriceCompositionTests(unittest.TestCase):
    def test_all_100_packets_with_real_constructor_canonical_config_and_pure_stages(self):
        from equity_feature_contracts import validate_batch
        from equity_features.ef1 import decode_ef1_context
        cases = packets()
        self.assertEqual((len(cases), sum(p.get("expected_result") is not None for p in cases)), (100, 46))
        counts = {}
        for packet in cases:
            with self.subTest(case=packet["id"]):
                error = packet.get("expected_error")
                if error is None:
                    result = calculate(packet)
                    self.assertEqual(normalized(result), packet["expected_result"])
                    self.assertEqual(normalized(decode_result(encode_result(result))), packet["expected_result"])
                    continue
                stage = error["expected_earliest_stage"]
                with self.assertRaises(ContractError) as caught:
                    slots = tuple(original_batch(s["batch"], convert=False) for s in packet["role_slots"])
                    if stage in ("CanonicalBatch_constructor", "Coverage_constructor"):
                        self.fail("Expected original constructor refusal")
                    if stage == "canonical_validate_batch":
                        for batch in slots:
                            if batch is not None: validate_batch(batch, required_fields=())
                        self.fail("Expected original canonical validation refusal")
                    config = ConfigSpec.from_json(json.dumps(packet["config"], ensure_ascii=True, sort_keys=True, separators=(",", ":")))
                    if stage == "endpoint_config_decode":
                        decode_ef1_context(config)
                        self.fail("Expected endpoint config refusal")
                    compute_ef1(slots, config, entity=EntityKey(**packet["entity"]))
                self.assertEqual(caught.exception.code.value, error["code"])
                counts[stage] = counts.get(stage, 0) + 1
        self.assertEqual(counts, {"canonical_validate_batch": 10, "Coverage_constructor": 1,
            "CanonicalBatch_constructor": 3, "endpoint_config_decode": 3,
            "endpoint_pure_semantic_or_geometry": 37})

    def test_all_46_full_sink_readbacks_identical_retry_close_and_reopen(self):
        limits=SinkRequirements(max_results=1,max_chunk_bytes=1048576,max_total_bytes=1048576,
            max_result_cells=2,max_evidence_rows=2)
        for packet in packets():
            if packet.get('expected_result') is None: continue
            with self.subTest(case=packet['id']),output_directory(packet['id']) as temp:
                result=calculate(packet)
                self.assertEqual(normalized(result),packet['expected_result'])
                publication=prepare_publication((result,),destination_scope='synthetic-regular-bar',generation_id=packet['id'],
                    job_id='regular-bar-fixture',partition_id='X-S',limits=limits)
                output=Path(temp)/'new-regular-bar-results.duckdb'
                with DuckDBSink(output,'synthetic-regular-bar',limits=limits) as sink:
                    receipt=publish(sink,publication,(result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]),encode_result(result))
                    self.assertEqual(publish(sink,publication,(result,)),receipt)
                sidecar = output.with_name(output.name + '.efio-duckdb1.lock')
                self.assertEqual(sidecar.read_bytes(), b'\0')
                lock_stat = sidecar.stat()
                with DuckDBSink(output,'synthetic-regular-bar',limits=limits) as sink:
                    self.assertEqual(sink.lookup(receipt.idempotency_key).receipt,receipt)
                    self.assertEqual(normalized(sink.read(receipt)[0]),packet['expected_result'])
                self.assertEqual(sidecar.read_bytes(), b'\0')
                self.assertEqual(sidecar.stat().st_ino, lock_stat.st_ino)


if __name__ == '__main__': unittest.main()
