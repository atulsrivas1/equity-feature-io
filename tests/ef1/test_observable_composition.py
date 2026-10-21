"""Frozen full observable packets through adapter, pure call and new output DB."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, ConfigSpec, ContractError, Coverage, DataKind,
    EntityKey, ErrorCode, InputScope, IntervalCoverage, PriceUnit, SourceBinding,
)
from equity_feature_duckdb.ef1 import (
    OpeningTradeInputs, StatusHistoryInputs, make_observable_batch,
    synthetic_opening_trade_fixture, synthetic_opening_trade_config,
    synthetic_opening_trade_seconds_fixture, synthetic_opening_trade_seconds_config,
    synthetic_status_history_fixture, synthetic_status_history_config,
    synthetic_status_history_missing_capability_fixture, synthetic_status_history_missing_capability_config,
)
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import compute_ef1

PACKETS=Path(__file__).with_name('observable_publication_packets.json')
PACKET_SHA='646e402e321eb97a171a2f8f64ce3c1ee399f7bcb81906fd929be4e6477170a6'
WORKER_ONLY={'X13-task-byte-bound','X15-evidence-bound'}

def packets():
    raw=PACKETS.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==PACKET_SHA
    return json.loads(raw)['packets']

def normalized(value): return json.loads(json.dumps(asdict(value)))

def original_batch(raw):
    if raw is None: return None
    meta=dict(raw['metadata'])
    for key,cls in (('source',SourceBinding),('coverage',Coverage),('adjustment',AdjustmentSpec),
                    ('price_unit',PriceUnit),('scope',InputScope)):
        meta[key]=None if meta[key] is None else cls(**meta[key])
    meta['interval_coverage']=tuple(IntervalCoverage(**{**row,'coverage':Coverage(**row['coverage'])}) for row in meta['interval_coverage'])
    columns=raw['columns']
    return make_observable_batch(DataKind(raw['kind']),tuple(c['name'] for c in columns),
        tuple(zip(*(c['values'] for c in columns))),metadata=BatchMetadata(**meta))

def packet_inputs(packet):
    cls=StatusHistoryInputs if packet['producer']=='status_history' else OpeningTradeInputs
    roles=cls().roles
    slots=[None]*len(roles); seen=set()
    for entry in packet['batches']:
        role=entry['role']
        if role not in roles or role in seen:
            raise ContractError(ErrorCode.INVALID_SCHEMA,'Exact unique fixture roles required')
        seen.add(role)
        slots[roles.index(role)]=original_batch(entry['batch'])
    return cls(*slots,tuple('unavailable' if b is None else 'synthetic' for b in slots))

def calculate(packet):
    inputs=packet_inputs(packet)
    config=ConfigSpec.from_json(packet['config_canonical_json'])
    return compute_ef1(inputs.slots,config,entity=EntityKey('X',config.session.session_id))

class ObservableCompositionTests(unittest.TestCase):
    def test_89_packets_58_exact_results_and_29_canonical_or_pure_errors(self):
        original_raw=PACKETS.with_name('observable_contract_packets.json').read_bytes()
        self.assertEqual(hashlib.sha256(original_raw).hexdigest(),'d0fb7b4fafc2b824e8998dbf10c7f27d8443fdb1218be7588c674002a2dcfc3c')
        original=json.loads(original_raw)
        amended=json.loads(PACKETS.read_bytes())
        changed=0
        for old,new in zip(original['packets'],amended['packets'],strict=True):
            if old['expected_result'] is not None:
                self.assertEqual(new['expected_result']['metadata']['math_policy_version'],'v1')
                new['expected_result']['metadata']['math_policy_version']='observable-v2'
                changed+=1
            self.assertEqual(old,new)
        self.assertEqual(changed,58)
        self.assertEqual(original,amended)
        cases=packets()
        self.assertEqual((len(cases),len({p['id'] for p in cases})),(89,89))
        self.assertEqual(sum(p['expected_result'] is not None for p in cases),58)
        self.assertEqual({p['id'] for p in cases if p['id'] in WORKER_ONLY},WORKER_ONLY)
        for packet in cases:
            if packet['id'] in WORKER_ONLY: continue
            with self.subTest(case=packet['id']):
                if packet['expected_result'] is None:
                    with self.assertRaises(ContractError) as caught: calculate(packet)
                    self.assertEqual(caught.exception.code.value,packet['expected_error']['code'])
                else: self.assertEqual(normalized(calculate(packet)),packet['expected_result'])

    def test_outer_wire_controls_are_explicitly_not_pure_error_credit(self):
        indexed={p['id']:p for p in packets()}
        self.assertEqual(indexed['X13-task-byte-bound']['admission_stage'],'encoded-task preflight before context/grammar')
        self.assertEqual(indexed['X15-evidence-bound']['admission_stage'],'FeatureResult evidence-count bound before duplicate check')
        self.assertEqual(len(indexed['X15-evidence-bound']['candidate_result']['evidence']),33)
        # Worker suites must actually execute these refusal stages. A pure callback
        # never receives candidate_result and cannot establish this wire behavior.

    def test_58_full_duckdb_readbacks_idempotence_and_reopen(self):
        limits=SinkRequirements(max_results=1,max_chunk_bytes=1048576,max_total_bytes=1048576,max_result_cells=6,max_evidence_rows=32)
        for packet in packets():
            if packet['expected_result'] is None: continue
            with self.subTest(case=packet['id']),TemporaryDirectory() as temp:
                result=calculate(packet)
                self.assertEqual(normalized(result),packet['expected_result'])
                publication=prepare_publication((result,),destination_scope='synthetic-observable',generation_id=packet['id'],
                    job_id='observable-fixture',partition_id='X-S',limits=limits)
                output=Path(temp)/'new-observable-results.duckdb'
                with DuckDBSink(output,'synthetic-observable',limits=limits) as sink:
                    receipt=publish(sink,publication,(result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]),encode_result(result))
                    self.assertEqual(publish(sink,publication,(result,)),receipt)
                with DuckDBSink(output,'synthetic-observable',limits=limits) as sink:
                    self.assertEqual(sink.lookup(receipt.idempotency_key).receipt,receipt)
                    self.assertEqual(normalized(sink.read(receipt)[0]),packet['expected_result'])

    def test_literal_public_examples_match_original_full_sources_and_results(self):
        cases={p['id']:p for p in packets()}
        for case,fixture,config in (
            ('O01-first',synthetic_opening_trade_fixture(),synthetic_opening_trade_config()),
            ('O02-seconds',synthetic_opening_trade_seconds_fixture(),synthetic_opening_trade_seconds_config()),
            ('H01-one-record-three-dimensions',synthetic_status_history_fixture(),synthetic_status_history_config()),
            ('H11-missing-source-identity',synthetic_status_history_missing_capability_fixture(),synthetic_status_history_missing_capability_config())):
            with self.subTest(case=case):
                packet=cases[case]
                self.assertEqual(fixture,packet_inputs(packet))
                self.assertEqual(normalized(config),packet['config'])
                self.assertEqual(normalized(compute_ef1(fixture.slots,config,entity=EntityKey('X','S'))),packet['expected_result'])

    def test_all_original_metadata_cells_and_provenance_unchanged(self):
        for packet in packets():
            if packet['expected_result'] is None: continue
            with self.subTest(case=packet['id']):
                inputs=packet_inputs(packet)
                before=tuple(normalized(b) for b in inputs.batches)
                result=calculate(packet)
                self.assertEqual(tuple(normalized(b) for b in inputs.batches),before)
                self.assertEqual({b.role:normalized(b.metadata) for b in result.metadata.inputs},
                    {r['role']:r['batch']['metadata'] for r in packet['batches'] if r['batch'] is not None})
                self.assertTrue(all(e.known_at_ns<=result.metadata.availability.knowledge_cutoff_ns for e in result.evidence))

    def test_paired_identical_empty_batch_is_not_role_inferred(self):
        cases={p['id']:p for p in packets()}
        bad=packet_inputs(cases['T01-zero-prefix-empty-market-prefix-refusal'])
        good=packet_inputs(cases['T02-zero-prefix-empty-source-capability-retained'])
        self.assertEqual(bad.market_prefix,good.source_capability)
        self.assertIsNone(bad.source_capability)
        self.assertIsNone(good.market_prefix)
        self.assertEqual(normalized(calculate(cases['T02-zero-prefix-empty-source-capability-retained'])),
            cases['T02-zero-prefix-empty-source-capability-retained']['expected_result'])
        with self.assertRaises(ContractError) as caught: calculate(cases['T01-zero-prefix-empty-market-prefix-refusal'])
        self.assertEqual(caught.exception.code,ErrorCode.BOUNDS)

    def test_duplicate_and_unknown_role_wrappers_refused(self):
        packet=packets()[0]
        for entries in (packet['batches']+[packet['batches'][0]],packet['batches']+[{'role':'invented','batch':None}]):
            with self.assertRaises(ContractError) as caught: packet_inputs({**packet,'batches':entries})
            self.assertEqual(caught.exception.code,ErrorCode.INVALID_SCHEMA)

if __name__=='__main__': unittest.main()
