"""Frozen full period/phase packets; source checks are not installed evidence."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, ConfigSpec, ContractError, Coverage, DataKind,
    EntityKey, InputScope, IntervalCoverage, PriceUnit, SourceBinding,
)
from equity_feature_duckdb.ef1 import (
    PeriodInputs, ExtendedInputs, make_period_batch, synthetic_period_fixture,
    synthetic_extended_fixture, synthetic_period_config, synthetic_extended_config,
)
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import compute_ef1

PACKETS = Path(__file__).with_name('period_phase_contract_packets.json')
PACKET_SHA = '81ac55769bdd21074aacf83c8df8955a501979d22e813ccfeba55b9e5e9f9204'


def packets():
    raw = PACKETS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKET_SHA
    doc = json.loads(raw)
    return doc['canonical_fixture_packets'] + doc['canonical_case_packets']


def normalized(value):
    return json.loads(json.dumps(asdict(value)))


def original_batch(raw):
    if raw is None:
        return None
    meta = dict(raw['metadata'])
    meta['source'] = SourceBinding(**meta['source'])
    meta['coverage'] = Coverage(**meta['coverage'])
    meta['price_unit'] = None if meta['price_unit'] is None else PriceUnit(**meta['price_unit'])
    meta['adjustment'] = AdjustmentSpec(**meta['adjustment'])
    meta['scope'] = None if meta['scope'] is None else InputScope(**meta['scope'])
    meta['interval_coverage'] = tuple(IntervalCoverage(**{**r, 'coverage': Coverage(**r['coverage'])})
                                      for r in meta['interval_coverage'])
    return make_period_batch(DataKind(raw['kind']), tuple(raw['column_order']),
                             tuple(tuple(r) for r in raw['rows']), metadata=BatchMetadata(**meta))


def packet_inputs(packet):
    slots = tuple(original_batch(row['batch']) for row in packet['input_slots'])
    origins = tuple('unavailable' if b is None else 'synthetic' for b in slots)
    cls = PeriodInputs if packet['context']['producer'] == 'period' else ExtendedInputs
    return cls(*slots, origins)


def calculate(packet):
    config = ConfigSpec.from_json(json.dumps(packet['config'], sort_keys=True, separators=(',', ':')))
    inputs = packet_inputs(packet)
    return compute_ef1(inputs.batches, config, entity=EntityKey(**packet['entity']))


class PeriodPhaseCompositionTests(unittest.TestCase):
    def test_exact_62_packets_42_full_successes_and_20_typed_errors(self):
        cases = packets()
        self.assertEqual((len(cases), len({p['id'] for p in cases})), (62, 62))
        self.assertEqual(sum(p['expected_result'] is not None for p in cases), 42)
        for packet in cases:
            with self.subTest(case=packet['id']):
                if packet['expected_result'] is None:
                    with self.assertRaises(ContractError) as caught:
                        calculate(packet)
                    self.assertEqual(caught.exception.code.value, packet['expected_error']['code'])
                else:
                    self.assertEqual(normalized(calculate(packet)), packet['expected_result'])

    def test_42_full_sink_readbacks_idempotence_and_reopen(self):
        limits = SinkRequirements(max_results=1, max_chunk_bytes=1048576, max_total_bytes=1048576,
                                  max_result_cells=9, max_evidence_rows=128)
        for packet in packets():
            if packet['expected_result'] is None:
                continue
            with self.subTest(case=packet['id']), TemporaryDirectory() as temp:
                actual = calculate(packet)
                self.assertEqual(normalized(actual), packet['expected_result'])
                publication = prepare_publication((actual,), destination_scope='synthetic-period-phase',
                    generation_id=packet['id'], job_id='period-phase-fixture', partition_id='X-S', limits=limits)
                output = Path(temp) / 'new-period-phase-results.duckdb'
                with DuckDBSink(output, 'synthetic-period-phase', limits=limits) as sink:
                    receipt = publish(sink, publication, (actual,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]), encode_result(actual))
                    self.assertEqual(publish(sink, publication, (actual,)), receipt)
                with DuckDBSink(output, 'synthetic-period-phase', limits=limits) as sink:
                    self.assertEqual(sink.lookup(receipt.idempotency_key).receipt, receipt)
                    restored = sink.read(receipt)[0]
                    self.assertEqual(normalized(restored), packet['expected_result'])
                    self.assertEqual(encode_result(restored), encode_result(actual))

    def test_public_examples_exact_base_sources_configs_and_results(self):
        for packet, fixture, config in zip(packets()[:2],
                (synthetic_period_fixture(), synthetic_extended_fixture()),
                (synthetic_period_config(), synthetic_extended_config()), strict=True):
            self.assertEqual(fixture, packet_inputs(packet))
            self.assertEqual(normalized(config), packet['config'])
            self.assertEqual(normalized(compute_ef1(fixture.batches, config, entity=EntityKey('X', 'S'))),
                             packet['expected_result'])

    def test_all_success_packets_original_fields_metadata_and_witness_clocks_unchanged(self):
        for packet in packets():
            if packet['expected_result'] is None:
                continue
            with self.subTest(case=packet['id']):
                inputs = packet_inputs(packet)
                before = tuple(normalized(b) for b in inputs.batches)
                result = calculate(packet)
                self.assertEqual(tuple(normalized(b) for b in inputs.batches), before)
                self.assertEqual({b.role: normalized(b.metadata) for b in result.metadata.inputs},
                    {r['role']: r['batch']['metadata'] for r in packet['input_slots'] if r['batch'] is not None})
                self.assertTrue(all(e.known_at_ns <= result.metadata.availability.knowledge_cutoff_ns
                                    for e in result.evidence))


if __name__ == '__main__':
    unittest.main()
