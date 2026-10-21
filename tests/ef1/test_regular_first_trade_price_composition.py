"""Actual producer and unchanged SDK/sink; execute only with coordinator stable pin."""
from collections import Counter
from contextlib import nullcontext
from dataclasses import asdict
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
import unittest
from equity_feature_contracts import ConfigSpec, ContractError, EntityKey, validate_batch
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import decode_result, encode_result, prepare_publication, publish
from equity_features.ef1 import compute_ef1, decode_ef1_context
from regular_first_trade_price_support import packets, packet_inputs, original_batch


def normalized(value):
    return json.loads(json.dumps(asdict(value), allow_nan=False))


def config_for(packet):
    return ConfigSpec.from_json(json.dumps(packet['request']['config'], ensure_ascii=True,
        sort_keys=True, separators=(',', ':'), allow_nan=False))


def calculate(packet):
    inputs = packet_inputs(packet)
    return compute_ef1(inputs.slots, config_for(packet), entity=EntityKey(**packet['request']['entity']))


def output_directory(case):
    parent = os.environ.get('EF1_FIRST_TRADE_IO_OUTPUT_ROOT')
    if parent is None:
        return TemporaryDirectory()
    # The private qualification controller owns this new directory. Never reuse
    # existing databases; keep the case prefix bounded on Windows.
    return nullcontext(mkdtemp(prefix=case+'-', dir=parent))


class RegularFirstTradePriceCompositionTests(unittest.TestCase):
    def assert_full_result(self, result, packet):
        self.assertEqual(normalized(result), packet['expected_result'])
        scalar = result.values[0].values[0]
        self.assertEqual(None if scalar is None else scalar.hex(), packet['expected_float_hex'])
        encoded = encode_result(result)
        self.assertEqual(normalized(decode_result(encoded)), packet['expected_result'])
        self.assertEqual(encode_result(decode_result(encoded)), encoded)

    def test_001_all_281_requests_full_results_and_actual_159_refusal_stages(self):
        counts = Counter()
        constructor_stages = {'CanonicalBatch_constructor','Coverage_constructor','PriceUnit_constructor',
            'BatchMetadata_constructor','transport_schema_admission'}
        for packet in packets():
            with self.subTest(case=packet['id']):
                error = packet.get('expected_error')
                if error is None:
                    self.assert_full_result(calculate(packet), packet)
                    counts['whole_result'] += 1
                    continue
                expected_stage = error['earliest_stage']
                stage = None
                trace = []
                with self.assertRaises(ContractError) as caught:
                    stage = 'ConfigSpec_constructor'
                    config = config_for(packet)
                    if expected_stage == stage: self.fail('Expected ConfigSpec constructor refusal')
                    try:
                        slots = tuple(original_batch(s['batch'], convert=False, trace=trace)
                            for s in packet['request']['role_slots'])
                    except ContractError:
                        stage = trace[-1]
                        raise
                    if expected_stage in constructor_stages: self.fail('Expected original constructor refusal')
                    stage = 'canonical_validate_batch'
                    for batch in slots:
                        if batch is not None: validate_batch(batch, required_fields=())
                    if expected_stage == stage: self.fail('Expected required-fields-only canonical refusal')
                    stage = 'future_new_config_decode'
                    decode_ef1_context(config)
                    if expected_stage == stage: self.fail('Expected producer config refusal')
                    # Direct original DTOs retain true pure invocation for cases
                    # that the adapter also refuses at its earlier container.
                    stage = 'future_new_pure_semantic'
                    compute_ef1(slots,config,entity=EntityKey(**packet['request']['entity']))
                    self.fail('Expected actual pure refusal')
                self.assertEqual(stage, expected_stage)
                self.assertEqual(caught.exception.code.value, error['code'])
                counts[stage] += 1
                print('FIRST_TRADE_ACTUAL_STAGE',packet['id'],stage,caught.exception.code.value,flush=True)
        self.assertEqual(dict(counts), {'whole_result':122,'CanonicalBatch_constructor':23,
            'Coverage_constructor':4,'PriceUnit_constructor':3,'BatchMetadata_constructor':1,
            'ConfigSpec_constructor':1,'transport_schema_admission':1,'canonical_validate_batch':20,
            'future_new_config_decode':11,'future_new_pure_semantic':95})

    def test_002_all_122_new_duckdb_full_readbacks_retry_close_reopen(self):
        limits = SinkRequirements(max_results=1,max_chunk_bytes=1048576,max_total_bytes=1048576,
            max_result_cells=1,max_evidence_rows=1)
        count = 0
        for packet in packets():
            if packet.get('expected_result') is None: continue
            with self.subTest(case=packet['id']), output_directory(packet['id']) as temp:
                result = calculate(packet)
                self.assert_full_result(result,packet)
                publication = prepare_publication((result,),destination_scope='synthetic-first-trade',
                    generation_id=packet['id'],job_id='first-trade-fixture',partition_id='X-S',limits=limits)
                output = Path(temp)/'results.duckdb'
                sidecar = output.with_name(output.name+'.efio-duckdb1.lock')
                self.assertLess(len(str(sidecar.resolve())),260)
                self.assertFalse(output.exists())
                with DuckDBSink(output,'synthetic-first-trade',limits=limits) as sink:
                    receipt = publish(sink,publication,(result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]),encode_result(result))
                    self.assertEqual(publish(sink,publication,(result,)),receipt)
                self.assertEqual(sidecar.read_bytes(),b'\0')
                lock_stat = sidecar.stat()
                with DuckDBSink(output,'synthetic-first-trade',limits=limits) as sink:
                    self.assertEqual(sink.lookup(receipt.idempotency_key).receipt,receipt)
                    self.assert_full_result(sink.read(receipt)[0],packet)
                self.assertEqual(sidecar.read_bytes(),b'\0')
                self.assertEqual(sidecar.stat().st_ino,lock_stat.st_ino)
                count += 1
                print('FIRST_TRADE_FULL_DB',packet['id'],str(output),flush=True)
        self.assertEqual(count,122)


if __name__ == '__main__': unittest.main()
