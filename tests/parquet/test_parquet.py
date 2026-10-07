"""Independent physical/lifecycle/numerical cases, runnable against fresh artifacts."""
from contextlib import ExitStack
import dataclasses
from decimal import Decimal
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import pyarrow as pa
import pyarrow.parquet as pq

from equity_feature_contracts import inputs as i, results as r, specs as s
from equity_feature_factory_fixture.publication_facts import synthetic_results
from equity_feature_io_contracts import FactoryError, SinkRequirements
from equity_feature_io_contracts.publication import CompletionReceipt, PublicationState, SinkError, SinkErrorCode
from equity_feature_io_sdk.codec import content_digest, descriptor, encode_receipt, encode_result, idempotency_key
from equity_feature_io_sdk.conformance import qualify_sink
from equity_feature_io_sdk.factories import SinkRegistry
from equity_feature_io_sdk.publication import prepare_publication, publish
from equity_feature_parquet import ParquetSink, ParquetSinkFactory

LIMITS = SinkRequirements(max_results=100, max_chunk_bytes=1048576, max_total_bytes=10485760,
                          max_result_cells=100000, max_evidence_rows=100000)
FACTS = synthetic_results()


def envelope(results, **changes):
    e = prepare_publication(results, destination_scope="synthetic-conformance", generation_id="generation",
                            job_id="job", partition_id="partition", limits=LIMITS)
    return dataclasses.replace(e, **changes)


def component(root, receipt, index):
    return root / '.efio-parquet1' / receipt.artifacts[index].artifact_id


class ParquetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name) / 'destination'
        self.owners = ExitStack()

    def tearDown(self):
        self.owners.close()
        self.temp.cleanup()

    def sink(self, **kwargs):
        return self.owners.enter_context(ParquetSink(self.root, 'synthetic-conformance', **kwargs))

    def reject(self, code, action):
        with self.assertRaises(SinkError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_full18_complete_canonical_and_independent_primitive_rows(self):
        sink = self.sink(caller_committed_at_ns=123456789)
        receipt = publish(sink, envelope(FACTS), FACTS)
        self.assertEqual(len(receipt.artifacts), 54)
        self.assertEqual(tuple(map(encode_result, sink.read(receipt))), tuple(map(encode_result, FACTS)))
        self.assertEqual(receipt.caller_committed_at_ns, 123456789)
        # Literal expectations are independent of backend projection construction.
        expected = {1: ('value_int64', -(2**63)), 2: ('value_int64', 2**63-1),
                    3: ('value_decimal128', Decimal('99999999999999999999999999999999999999')),
                    5: ('value_utf8', 'e\u0301/\u00e9\n'), 6: ('value_bool', False), 7: ('value_int64', 0)}
        for ordinal, (column, value) in expected.items():
            with pq.ParquetFile(component(self.root, receipt, ordinal*3+1)) as file:
                observed = file.read().to_pylist()
                self.assertEqual(len(observed), 1)
                self.assertEqual(observed[0][column], value)
                self.assertEqual(observed[0]['result_ordinal'], ordinal)
                self.assertFalse(observed[0]['is_null'])
        with pq.ParquetFile(component(self.root, receipt, 4*3+1)) as file:
            self.assertEqual(file.read().to_pylist()[0]['value_float64'].hex(), '-0x0.0p+0')
        with pq.ParquetFile(component(self.root, receipt, 8*3+1)) as file:
            row = file.read().to_pylist()[0]
            self.assertTrue(row['is_null']);self.assertIsNone(row['value_int64'])
            self.assertEqual(row['quality_status'], 'missing_input')
        with pq.ParquetFile(component(self.root, receipt, 11*3+2)) as file:
            self.assertEqual(file.schema_arrow.field('event_ns').type, pa.int64())
            row = file.read().to_pylist()[0]
            self.assertEqual((row['event_ns'], row['known_at_ns'], row['row_id']), (9, 9, 'event1'))
        with pq.ParquetFile(component(self.root, receipt, 17*3+2)) as file:
            self.assertIsNone(file.read().to_pylist()[0]['known_at_ns'])

    def test_original_replay_new_instance_and_operational_fields(self):
        result = (FACTS[1],);sink = self.sink(caller_committed_at_ns=222)
        e = envelope(result);session = sink.begin(e);sink.write(session,0,result[0]);receipt = sink.commit(session)
        fresh = self.sink(caller_committed_at_ns=999)
        replay = fresh.begin(dataclasses.replace(e, caller_created_at_ns=17, max_results=99))
        self.assertEqual(encode_receipt(replay), encode_receipt(receipt))
        self.assertEqual(fresh.lookup(receipt.idempotency_key).receipt, receipt)
        self.assertEqual(sink.abort(session).receipt, receipt)

    def test_zero_publication_and_observed_empty_result_remain_distinct(self):
        sink = self.sink();zero = publish(sink, envelope(()), ())
        empty_e = envelope((FACTS[0],), generation_id='empty-result')
        empty = publish(sink, empty_e, (FACTS[0],))
        self.assertEqual(zero.artifacts, ());self.assertEqual(sink.read(zero), ())
        self.assertEqual(len(empty.artifacts), 3)
        self.assertNotEqual(zero.content_sha256, empty.content_sha256)
        self.assertEqual(sink.read(empty), (FACTS[0],))
        for index in (1,2):
            with pq.ParquetFile(component(self.root, empty, index)) as file:
                self.assertEqual(file.metadata.num_rows, 0)
                self.assertEqual(file.schema_arrow.metadata[b'efio_storage'], b'efio-parquet1')

    def test_reusable21_cases_real_parquet_and_owned_cleanup(self):
        counter = 0
        def factory():
            nonlocal counter
            counter += 1
            return self.owners.enter_context(ParquetSink(self.root / str(counter), 'synthetic-conformance'))
        report = qualify_sink(factory, FACTS, LIMITS)
        self.assertEqual(len(report.cases), 21)
        self.assertTrue(all(case.passed for case in report.cases), report)
        self.assertFalse(report.backend_durability_certification)

    def test_real_multiple_instances_live_serialization_conflict_and_abort(self):
        first = self.sink();second = self.sink();e = envelope((FACTS[1],))
        session = first.begin(e)
        self.assertEqual(second.lookup(idempotency_key(e.identity)).state, PublicationState.STAGING)
        self.reject(SinkErrorCode.BUSY, lambda: second.begin(e))
        self.reject(SinkErrorCode.BUSY, lambda: second.begin(dataclasses.replace(e, generation_id='other')))
        self.reject(SinkErrorCode.CONFLICT, lambda: second.begin(dataclasses.replace(e, expected_content_sha256='f'*64)))
        self.reject(SinkErrorCode.INVALID_SESSION, lambda: second.write(session, 0, FACTS[1]))
        self.assertEqual(first.abort(session).state, PublicationState.ABORTED)
        self.assertEqual(first.abort(session).state, PublicationState.ABORTED)
        self.reject(SinkErrorCode.CONFLICT, lambda: second.begin(dataclasses.replace(e, expected_content_sha256='f'*64)))
        restarted = second.begin(e)
        self.assertNotEqual(session.attempt_id, restarted.attempt_id)
        self.reject(SinkErrorCode.INVALID_SESSION, lambda: first.abort(session))
        second.write(restarted, 0, FACTS[1]);receipt = second.commit(restarted)
        self.assertEqual(second.abort(restarted).receipt, receipt)
        self.reject(SinkErrorCode.INVALID_SESSION, lambda: second.write(restarted, 0, FACTS[1]))

    def test_admission_before_namespace_creation(self):
        sink = self.sink();e = envelope((FACTS[1],))
        self.reject(SinkErrorCode.INCOMPATIBLE_VERSION, lambda: sink.begin(dataclasses.replace(e, codec_version='future')))
        self.reject(SinkErrorCode.INVALID_CONFIG, lambda: sink.begin(dataclasses.replace(e, destination_scope='foreign')))
        self.reject(SinkErrorCode.RESOURCE_LIMIT, lambda: sink.begin(dataclasses.replace(e, max_results=101)))
        self.assertFalse(self.root.exists())
        self.reject(SinkErrorCode.RESOURCE_LIMIT, lambda: self.sink(max_physical_bytes=67108865))
        self.reject(SinkErrorCode.UNSUPPORTED_CAPABILITY, lambda: self.sink(limits=dataclasses.replace(LIMITS, writer_mode='single_writer')))
        self.assertFalse(self.root.exists())

    def test_all_three_corrupt_components_withhold_all_receipts(self):
        sink = self.sink();e = envelope((FACTS[1],));session = sink.begin(e)
        sink.write(session,0,FACTS[1]);receipt = sink.commit(session)
        for index in range(3):
            path = component(self.root,receipt,index);original = path.read_bytes()
            try:
                path.write_bytes(original+b'x')
                for action in (lambda: sink.read(receipt), lambda: sink.lookup(receipt.idempotency_key),
                               lambda: sink.begin(e),lambda: sink.abort(session)):
                    self.reject(SinkErrorCode.CORRUPTION,action)
            finally:
                path.write_bytes(original)
        self.assertEqual(sink.read(receipt),(FACTS[1],))

    def test_column_corruption_with_recomputed_physical_hash_is_detected(self):
        sink = self.sink();receipt = publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        path = component(self.root,receipt,1)
        with pq.ParquetFile(path) as file:
            schema = file.schema_arrow;values = file.read().to_pylist()
        values[0]['value_int64'] = 123
        pq.write_table(pa.Table.from_pylist(values,schema=schema),path,version='2.6',compression='NONE',use_dictionary=False)
        data = path.read_bytes();artifacts = list(receipt.artifacts)
        artifacts[1] = dataclasses.replace(artifacts[1],byte_length=len(data),byte_sha256=hashlib.sha256(data).hexdigest())
        changed = dataclasses.replace(receipt,artifacts=tuple(artifacts))
        control = self.root/'.efio-parquet1'/receipt.idempotency_key/'complete.json'
        record = json.loads(control.read_text(encoding='ascii'));record['receipt'] = encode_receipt(changed).decode('ascii')
        control.write_text(json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=True),encoding='ascii')
        self.reject(SinkErrorCode.CORRUPTION,lambda: sink.lookup(receipt.idempotency_key))

    def _reject_expanding_projection_before_read(self, compression, dictionary, payload):
        import equity_feature_parquet.projections as projection
        sink = self.sink(max_physical_bytes=131072)
        receipt = publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        path = component(self.root,receipt,1)
        with pq.ParquetFile(path) as file:
            schema = file.schema_arrow;values = file.read().to_pylist()
        values[0]['namespace'] = payload
        pq.write_table(pa.Table.from_pylist(values,schema=schema),path,version='2.6',
                       compression=compression,use_dictionary=dictionary,write_statistics=False)
        data = path.read_bytes();self.assertLess(len(data),131072)
        artifacts = list(receipt.artifacts)
        artifacts[1] = dataclasses.replace(artifacts[1],byte_length=len(data),byte_sha256=hashlib.sha256(data).hexdigest())
        changed = dataclasses.replace(receipt,artifacts=tuple(artifacts))
        control = self.root/'.efio-parquet1'/receipt.idempotency_key/'complete.json'
        record = json.loads(control.read_text(encoding='ascii'));record['receipt'] = encode_receipt(changed).decode('ascii')
        control.write_text(json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=True),encoding='ascii')
        actual = pq.ParquetFile
        readers = []
        def guarded(*args, **kwargs):
            reader = actual(*args, **kwargs)
            proxy = mock.Mock(wraps=reader)
            proxy.schema_arrow = reader.schema_arrow;proxy.metadata = reader.metadata
            proxy.read = mock.Mock(side_effect=AssertionError('unqualified allocation'))
            readers.append(proxy)
            return proxy
        with mock.patch.object(projection.pq,'ParquetFile',side_effect=guarded):
            self.reject(SinkErrorCode.CORRUPTION,lambda: sink.lookup(receipt.idempotency_key))
        self.assertEqual(len(readers),1)
        readers[0].read.assert_not_called();readers[0].close.assert_called_once()

    def test_compressed_expansion_rejected_before_arrow_read(self):
        self._reject_expanding_projection_before_read('ZSTD',False,'n'*2097152)

    def test_dictionary_encoding_rejected_before_arrow_read(self):
        self._reject_expanding_projection_before_read('NONE',True,'n'*10000)

    def test_control_corruption_missing_component_and_mismatched_receipt(self):
        sink = self.sink();receipt = publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        self.reject(SinkErrorCode.CORRUPTION,lambda: sink.read(dataclasses.replace(receipt,caller_committed_at_ns=1)))
        path = component(self.root,receipt,2);data = path.read_bytes();path.unlink()
        self.reject(SinkErrorCode.CORRUPTION,lambda: sink.lookup(receipt.idempotency_key));path.write_bytes(data)
        control = self.root/'.efio-parquet1'/receipt.idempotency_key/'complete.json'
        record = json.loads(control.read_text(encoding='ascii'));record['unexpected']='field'
        control.write_text(json.dumps(record,sort_keys=True,separators=(',',':')),encoding='ascii')
        self.reject(SinkErrorCode.CORRUPTION,lambda: sink.lookup(receipt.idempotency_key))

    def test_physical_stream_cannot_write_beyond_attempt_budget(self):
        sink = self.sink(max_physical_bytes=4096);e = envelope((FACTS[1],));session = sink.begin(e)
        self.reject(SinkErrorCode.RESOURCE_LIMIT,lambda: sink.write(session,0,FACTS[1]))
        attempt = self.root/'.efio-parquet1'/session.key/session.attempt_id
        self.assertLessEqual(sum(p.stat().st_size for p in attempt.iterdir()),4096)
        self.assertFalse((attempt.parent/'complete.json').exists())
        self.assertEqual(sink.abort(session).state,PublicationState.ABORTED)

    def test_expanded_repeated_metadata_is_admitted_before_arrow_allocation(self):
        import equity_feature_parquet.projections as projection
        base = FACTS[1];entities = tuple(r.EntityKey('I'+str(n),'S') for n in range(100))
        column = dataclasses.replace(base.values[0],entities=entities,values=(1,)*100)
        qualities = tuple(dataclasses.replace(base.quality[0],entity=entity) for entity in entities)
        result = dataclasses.replace(base,values=(column,),quality=qualities,metadata=dataclasses.replace(base.metadata,namespace='n'*50000))
        rows,_ = projection.rows(result,0);schema,_ = projection.schemas()
        arrow = mock.Mock()
        with mock.patch.object(projection,'pa',arrow):
            self.reject(SinkErrorCode.RESOURCE_LIMIT,lambda: projection.write_projection(self.root/'not-created.parquet',rows,schema,262144))
        arrow.Table.from_pylist.assert_not_called();self.assertFalse(self.root.exists())

    def test_control_bound_and_logical_partial_digest_rejection(self):
        small = self.sink(max_control_bytes=16)
        self.reject(SinkErrorCode.RESOURCE_LIMIT,lambda: small.begin(envelope((FACTS[1],))))
        self.assertFalse(self.root.exists())
        sink = self.sink();e = envelope((FACTS[1],));session = sink.begin(e)
        self.reject(SinkErrorCode.CONFLICT,lambda: sink.commit(session));sink.abort(session)
        changed = dataclasses.replace(e,generation_id='changed-digest',expected_content_sha256='f'*64)
        session = sink.begin(changed);sink.write(session,0,FACTS[1])
        self.reject(SinkErrorCode.CONFLICT,lambda: sink.commit(session));sink.abort(session)

    def test_cross_result_duplicate_cell_keys_rejected(self):
        data = (FACTS[1],FACTS[1]);e = envelope((FACTS[1],FACTS[2]))
        e = dataclasses.replace(e,result_descriptors=tuple(descriptor(result) for result in data),
                                content_bytes=sum(len(encode_result(result)) for result in data),
                                expected_content_sha256=content_digest(data))
        sink = self.sink();session = sink.begin(e);sink.write(session,0,data[0])
        self.reject(SinkErrorCode.INVALID_CONTENT,lambda: sink.write(session,1,data[1]));sink.abort(session)

    def test_direct_factory_equivalence_and_redacted_no_credential_access(self):
        class Credentials:
            def get(self,name):raise AssertionError('credentials must not be consumed')
        registry = SinkRegistry[ParquetSink]();registry.register('parquet',ParquetSinkFactory())
        sink = registry.resolve('parquet',{'root':str(self.root),'destination_scope':'synthetic-conformance'},Credentials(),LIMITS)
        self.owners.enter_context(sink);self.assertFalse(self.root.exists())
        receipt = publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        self.assertEqual(self.sink().begin(envelope((FACTS[1],))),receipt)
        for config in ({'root':str(self.root),'destination_scope':'synthetic-conformance','max_results':True},
                       {'root':'synthetic-sensitive-marker','destination_scope':'synthetic-conformance','unknown':'value'}):
            with self.assertRaises(FactoryError) as caught:
                ParquetSinkFactory().validate_config(config)
            self.assertNotIn('synthetic-sensitive-marker',str(caught.exception))

    def test_public_source_to_calculation_independent500_51200_102point6(self):
        from equity_feature_contracts.specs import ConfigSpec,Parameter,SessionSpec,WindowSpec
        from equity_features.session import compute_bars
        unit=i.PriceUnit(0,'USD')
        config=ConfigSpec('synthetic-bars','v1',(Parameter('eligibility_policy','example-v1'),),SessionSpec('demo','S',100,200,'caller-supplied'),WindowSpec(1,'S',('P','S')),s.AvailabilitySpec(200,210,210),price_unit=unit)
        facts=(('instrument_id',('A','A')),('session_id',('S','S')),('start_ns',(100,150)),('end_ns',(150,200)),('known_at_ns',(150,210)),('open',(100,102)),('high',(103,104)),('low',(99,101)),('close',(102,103)),('volume',(200,300)),('actual_notional',(20300,30900)))
        batch=i.CanonicalBatch(i.DataKind.BAR,tuple(i.Column(n,v) for n,v in facts),i.BatchMetadata('demo',i.SourceBinding('synthetic','snapshot1','map1','bars1'),i.Coverage(2,2,True),unit,scope=i.InputScope(100,200,'example-v1')))
        result=compute_bars(batch,config,entity=r.EntityKey('A','S'));sink=self.sink();receipt=publish(sink,envelope((result,)),(result,))
        observed=sink.read(receipt)[0];values={column.feature_id:column.values[0] for column in observed.values}
        self.assertEqual(values['session.bar.volume'],500);self.assertEqual(values['session.bar.notional'],51200)
        self.assertEqual(values['session.bar.close_weighted_price'],102.6);self.assertIsNone(values['session.price.overnight_gap'])
        self.assertEqual(encode_result(observed),encode_result(result))
        with pq.ParquetFile(component(self.root,receipt,1)) as file:
            rows={row['feature_id']:row for row in file.read().to_pylist()}
        self.assertEqual(rows['session.bar.volume']['value_int64'],500)
        self.assertEqual(rows['session.bar.notional']['value_decimal128'],Decimal(51200))
        self.assertEqual(rows['session.bar.close_weighted_price']['value_float64'],102.6)
        self.assertTrue(rows['session.price.overnight_gap']['is_null'])


if __name__=='__main__':
    installed='--installed' in sys.argv
    if installed:
        sys.argv.remove('--installed')
        import equity_feature_parquet,equity_feature_io_contracts,equity_feature_io_sdk,equity_feature_factory_fixture
        for module in (equity_feature_parquet,equity_feature_io_contracts,equity_feature_io_sdk,equity_feature_factory_fixture):
            assert 'site-packages' in Path(module.__file__).resolve().parts
    report=None
    if '--report-json' in sys.argv:
        index=sys.argv.index('--report-json');report=Path(sys.argv[index+1]);del sys.argv[index:index+2]
    result=unittest.main(exit=False).result
    if report is not None:
        report.write_text(json.dumps(dict(schema='parquet-installed1',tests=result.testsRun,passed=result.wasSuccessful(),
            installed_public_execution=installed,parquet=version('equity-feature-parquet'),pyarrow=version('pyarrow'),
            io_contracts=version('equity-feature-io-contracts'),io_sdk=version('equity-feature-io-sdk'),
            test_suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            process_qualification=False,private_execution=False),sort_keys=True,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
