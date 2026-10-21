"""Actual daily producer against immutable full goldens and unchanged DuckDB sink."""
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from equity_feature_contracts import ConfigSpec, ContractError, EntityKey
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import compute_ef1
from daily_observations_support import packets, packet_inputs, original_batch


def normalized(value): return json.loads(json.dumps(asdict(value)))


def calculate(packet):
    inputs = packet_inputs(packet)
    config = ConfigSpec.from_json(json.dumps(packet['config'],ensure_ascii=True,sort_keys=True,separators=(',',':')))
    return compute_ef1(inputs.slots,config,entity=EntityKey('X',config.session.session_id))


class DailyObservationsCompositionTests(unittest.TestCase):
    def test_all_119_packets_with_28_direct_pure_refusals(self):
        cases = packets()
        self.assertEqual((len(cases),sum(p.get('expected_result') is not None for p in cases)),(119,91))
        for packet in cases:
            with self.subTest(case=packet['id']):
                if packet.get('expected_result') is None:
                    # Pure errors must reach the actual pure API. Generic adapter
                    # validation independently rejects duplicate canonical IDs.
                    slots=tuple(original_batch(slot['batch'],convert=False) for slot in packet['role_slots'])
                    config=ConfigSpec.from_json(json.dumps(packet['config'],ensure_ascii=True,sort_keys=True,separators=(',',':')))
                    with self.assertRaises(ContractError) as caught:
                        compute_ef1(slots,config,entity=EntityKey('X',config.session.session_id))
                    self.assertEqual(caught.exception.code.value,packet['expected_error']['code'])
                else:
                    self.assertEqual(normalized(calculate(packet)),packet['expected_result'])

    def test_all_91_full_sink_readbacks_identical_retry_close_and_reopen(self):
        limits=SinkRequirements(max_results=1,max_chunk_bytes=1048576,max_total_bytes=1048576,
            max_result_cells=4,max_evidence_rows=28)
        for packet in packets():
            if packet.get('expected_result') is None: continue
            with self.subTest(case=packet['id']),TemporaryDirectory() as temp:
                result=calculate(packet)
                self.assertEqual(normalized(result),packet['expected_result'])
                publication=prepare_publication((result,),destination_scope='synthetic-daily',generation_id=packet['id'],
                    job_id='daily-fixture',partition_id='X-S',limits=limits)
                output=Path(temp)/'new-daily-results.duckdb'
                with DuckDBSink(output,'synthetic-daily',limits=limits) as sink:
                    receipt=publish(sink,publication,(result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]),encode_result(result))
                    self.assertEqual(publish(sink,publication,(result,)),receipt)
                with DuckDBSink(output,'synthetic-daily',limits=limits) as sink:
                    self.assertEqual(sink.lookup(receipt.idempotency_key).receipt,receipt)
                    self.assertEqual(normalized(sink.read(receipt)[0]),packet['expected_result'])


if __name__ == '__main__': unittest.main()
