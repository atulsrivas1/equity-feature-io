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

import duckdb

from equity_feature_contracts import inputs as i, results as r, specs as s
from equity_feature_factory_fixture.publication_facts import synthetic_results
from equity_feature_io_contracts import FactoryError, SinkRequirements
from equity_feature_io_contracts.publication import CompletionReceipt, PublicationState, SinkError, SinkErrorCode
from equity_feature_io_sdk.codec import content_digest, descriptor, encode_receipt, encode_result, idempotency_key
from equity_feature_io_sdk.conformance import qualify_sink
from equity_feature_io_sdk.factories import SinkRegistry
from equity_feature_io_sdk.publication import prepare_publication, publish
from equity_feature_duckdb_sink import DuckDBSink, DuckDBSinkFactory

LIMITS = SinkRequirements(max_results=100, max_chunk_bytes=1048576, max_total_bytes=10485760,
                          max_result_cells=100000, max_evidence_rows=100000)
FACTS = synthetic_results()


def envelope(results, **changes):
    e = prepare_publication(results, destination_scope="synthetic-conformance", generation_id="generation",
                            job_id="job", partition_id="partition", limits=LIMITS)
    return dataclasses.replace(e, **changes)


class DuckDBTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name) / 'destination.db'
        self.owners = ExitStack()

    def tearDown(self):
        self.owners.close()
        self.temp.cleanup()

    def sink(self, **kwargs):
        return self.owners.enter_context(DuckDBSink(self.root, 'synthetic-conformance', **kwargs))

    def reject(self, code, action):
        with self.assertRaises(SinkError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_original_replay_new_instance_and_operational_fields(self):
        result = (FACTS[1],);sink = self.sink(caller_committed_at_ns=222)
        e = envelope(result);session = sink.begin(e);sink.write(session,0,result[0]);receipt = sink.commit(session)
        fresh = self.sink(caller_committed_at_ns=999)
        replay = fresh.begin(dataclasses.replace(e, caller_created_at_ns=17, max_results=99))
        self.assertEqual(encode_receipt(replay), encode_receipt(receipt))
        self.assertEqual(fresh.lookup(receipt.idempotency_key).receipt, receipt)
        self.assertEqual(sink.abort(session).receipt, receipt)

    def test_all18_exact_canonical_and_literal_sql_primitives(self):
        sink = self.sink(caller_committed_at_ns=123456789)
        receipt = publish(sink, envelope(FACTS), FACTS)
        self.assertEqual(len(receipt.artifacts),54)
        self.assertEqual(tuple(map(encode_result,sink.read(receipt))),tuple(map(encode_result,FACTS)))
        con=duckdb.connect(str(self.root),read_only=True)
        try:
            expected={1:('value_int64',-(2**63)),2:('value_int64',2**63-1),
                      3:('value_decimal128',Decimal('99999999999999999999999999999999999999')),
                      5:('value_utf8','e\u0301/\u00e9\n'),6:('value_bool',False),7:('value_int64',0)}
            for ordinal,(field,value) in expected.items():
                self.assertEqual(con.execute(f'SELECT {field},is_null FROM efio_cells WHERE result_ordinal=?',[ordinal]).fetchall(),[(value,False)])
            value=con.execute('SELECT value_float64 FROM efio_cells WHERE result_ordinal=4').fetchone()[0]
            self.assertEqual(value.hex(),'-0x0.0p+0')
            self.assertEqual(con.execute('SELECT is_null,value_int64,quality_status FROM efio_cells WHERE result_ordinal=8').fetchall(),[(True,None,'missing_input')])
            self.assertEqual(con.execute('SELECT event_ns,known_at_ns,row_id FROM efio_evidence WHERE result_ordinal=11').fetchall(),[(9,9,'event1')])
            self.assertIsNone(con.execute('SELECT known_at_ns FROM efio_evidence WHERE result_ordinal=17').fetchone()[0])
        finally:con.close()

    def test_fresh_control_snapshot_before_after_commit_and_foreign_busy(self):
        sink=self.sink();e=envelope((FACTS[1],));key=idempotency_key(e.identity)
        session=sink.begin(e);sink.write(session,0,FACTS[1])
        self.assertEqual(sink.lookup(key).state,PublicationState.STAGING)
        self.assertEqual(session.control.execute('SELECT count(*) FROM efio_results').fetchall(),[(0,)])
        foreign=self.sink()
        for action in (lambda:foreign.lookup(key),lambda:foreign.begin(e),lambda:foreign.begin(dataclasses.replace(e,generation_id='other'))):
            self.reject(SinkErrorCode.BUSY,action)
        self.reject(SinkErrorCode.INVALID_SESSION,lambda:foreign.write(session,0,FACTS[1]))
        receipt=sink.commit(session)
        self.assertEqual(foreign.lookup(key).receipt,receipt)
        self.assertEqual(foreign.read(receipt),(FACTS[1],))

    def test_zero_empty_and_new_generation_preserve_original_blobs(self):
        sink=self.sink();zero=publish(sink,envelope(()),())
        empty=publish(sink,envelope((FACTS[0],),generation_id='empty'),(FACTS[0],))
        self.assertEqual(zero.artifacts,());self.assertEqual(sink.read(zero),())
        self.assertEqual(len(empty.artifacts),3);self.assertEqual(sink.read(empty),(FACTS[0],))
        first=publish(sink,envelope((FACTS[1],),generation_id='first'),(FACTS[1],))
        before=self.root.read_bytes()
        second=publish(sink,envelope((FACTS[2],),generation_id='second'),(FACTS[2],))
        self.assertNotEqual(before,self.root.read_bytes())
        self.assertEqual(sink.lookup(first.idempotency_key).receipt,first)
        self.assertEqual(sink.read(first),(FACTS[1],));self.assertEqual(sink.read(second),(FACTS[2],))

    def test_source_store_rejected_read_only_without_database_or_wal_changes(self):
        con=duckdb.connect(str(self.root));con.execute('CREATE TABLE source_data(id BIGINT)');con.execute('INSERT INTO source_data VALUES (1)');con.close()
        before=self.root.read_bytes()
        self.reject(SinkErrorCode.INVALID_CONFIG,lambda:self.sink().begin(envelope((FACTS[1],))))
        self.assertEqual(before,self.root.read_bytes())
        self.assertFalse(Path(str(self.root)+'.wal').exists())

    def test_each_blob_corruption_withholds_replay_lookup_read_abort(self):
        sink=self.sink();e=envelope((FACTS[1],));session=sink.begin(e);sink.write(session,0,FACTS[1]);receipt=sink.commit(session)
        for field in ('record','cells_bundle','evidence_bundle'):
            con=duckdb.connect(str(self.root));original=con.execute(f'SELECT {field} FROM efio_results').fetchone()[0]
            con.execute(f'UPDATE efio_results SET {field}=?',[original+b'x']);con.close()
            try:
                for action in (lambda:sink.lookup(receipt.idempotency_key),lambda:sink.read(receipt),lambda:sink.begin(e),lambda:sink.abort(session)):
                    self.reject(SinkErrorCode.CORRUPTION,action)
            finally:
                con=duckdb.connect(str(self.root));con.execute(f'UPDATE efio_results SET {field}=?',[original]);con.close()

    def test_typed_projection_corruption_even_with_unchanged_valid_blobs(self):
        sink=self.sink();receipt=publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        for field,value,original in (('value_int64',123,-(2**63)),('unit','wrong','integer'),('quality_status','complete','ok')):
            con=duckdb.connect(str(self.root));original=con.execute(f'SELECT {field} FROM efio_cells').fetchone()[0]
            con.execute(f'UPDATE efio_cells SET {field}=?',[value]);con.close()
            try:self.reject(SinkErrorCode.CORRUPTION,lambda:sink.lookup(receipt.idempotency_key))
            finally:
                con=duckdb.connect(str(self.root));con.execute(f'UPDATE efio_cells SET {field}=?',[original]);con.close()

    def test_repeated_payload_rejected_before_projection_allocation(self):
        import equity_feature_duckdb_sink.sink as backend
        base=FACTS[1];entities=tuple(r.EntityKey('I'+str(n),'S') for n in range(100))
        result=dataclasses.replace(base,values=(dataclasses.replace(base.values[0],entities=entities,values=(1,)*100),),
            quality=tuple(dataclasses.replace(base.quality[0],entity=entity) for entity in entities),
            metadata=dataclasses.replace(base.metadata,namespace='n'*50000))
        sink=self.sink(max_projection_bytes=262144);session=sink.begin(envelope((result,)))
        with mock.patch.object(backend,'rows',side_effect=AssertionError('allocation before admission')) as constructor:
            self.reject(SinkErrorCode.RESOURCE_LIMIT,lambda:sink.write(session,0,result))
        constructor.assert_not_called();sink.abort(session)

    def test_abort_retry_old_handle_closed_and_context_releases_connections(self):
        sink=self.sink();e=envelope((FACTS[1],));session=sink.begin(e);sink.write(session,0,FACTS[1])
        self.assertEqual(sink.abort(session).state,PublicationState.ABORTED)
        self.assertEqual(sink.abort(session).state,PublicationState.ABORTED)
        other=self.sink();retry=other.begin(e);self.assertNotEqual(session.attempt_id,retry.attempt_id)
        self.reject(SinkErrorCode.BUSY,lambda:sink.abort(session))
        other.close();self.reject(SinkErrorCode.INVALID_SESSION,lambda:sink.abort(session))
        newer=sink.begin(e);sink.close();self.reject(SinkErrorCode.INVALID_SESSION,lambda:sink.write(newer,0,FACTS[1]))
        fresh=self.sink();receipt=publish(fresh,e,(FACTS[1],));self.assertEqual(fresh.read(receipt),(FACTS[1],))

    def test_wrong_storage_version_extra_schema_and_missing_result_rejected(self):
        sink=self.sink();receipt=publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        con=duckdb.connect(str(self.root));con.execute("UPDATE efio_metadata SET storage_version='future'");con.close()
        self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:sink.lookup(receipt.idempotency_key))
        con=duckdb.connect(str(self.root));con.execute("UPDATE efio_metadata SET storage_version='efio-duckdb1'");con.execute('CREATE TABLE extra(id INT)');con.close()
        self.reject(SinkErrorCode.CORRUPTION,lambda:sink.lookup(receipt.idempotency_key))
        con=duckdb.connect(str(self.root));con.execute('DROP TABLE extra');con.execute('DELETE FROM efio_results');con.close()
        self.reject(SinkErrorCode.CORRUPTION,lambda:sink.lookup(receipt.idempotency_key))

    def test_commit_response_loss_factually_verified_and_partial_insert_rollback(self):
        class Proxy:
            def __init__(self,connection,fail):self.connection=connection;self.fail=fail
            def execute(self,query,*params):
                value=self.connection.execute(query,*params)
                if query==self.fail:raise RuntimeError('synthetic-private-marker')
                return value
            def executemany(self,*params):return self.connection.executemany(*params)
            def close(self):self.connection.close()
        sink=self.sink();e=envelope((FACTS[1],));session=sink.begin(e)
        session.data=Proxy(session.data,'INSERT INTO efio_results VALUES (?,?,?,?,?,?)')
        self.reject(SinkErrorCode.UNAVAILABLE,lambda:sink.write(session,0,FACTS[1]))
        self.reject(SinkErrorCode.INVALID_SESSION,lambda:sink.commit(session))
        self.assertEqual(sink.lookup(session.key).state,PublicationState.STAGING)
        self.assertEqual(sink.abort(session).state,PublicationState.ABORTED)
        session=sink.begin(e);sink.write(session,0,FACTS[1]);session.data=Proxy(session.data,'COMMIT')
        self.reject(SinkErrorCode.COMMIT_UNKNOWN,lambda:sink.commit(session))
        receipt=sink.lookup(session.key).receipt
        self.assertEqual(sink.read(receipt),(FACTS[1],));self.assertEqual(sink.abort(session).receipt,receipt)

    def test_oversize_sql_payload_rejected_before_blob_fetch(self):
        import equity_feature_duckdb_sink.sink as backend
        sink=self.sink(max_projection_bytes=65536);receipt=publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        con=duckdb.connect(str(self.root));con.execute('UPDATE efio_cells SET namespace=?',['n'*200000]);con.close()
        actual=backend.connect;executed=[]
        class Reader:
            def __init__(self,con):self.con=con
            def execute(self,query,*params):
                executed.append(query)
                if query.startswith('SELECT record,'):raise AssertionError('BLOB fetched before admission')
                self.con.execute(query,*params);return self
            def fetchall(self):return self.con.fetchall()
            def close(self):self.con.close()
        with mock.patch.object(backend,'connect',side_effect=lambda *a,**k:Reader(actual(*a,**k))):
            self.reject(SinkErrorCode.CORRUPTION,lambda:sink.lookup(receipt.idempotency_key))
        self.assertFalse(any(query.startswith('SELECT record,') for query in executed))

    def test_reusable21_cases_real_duckdb_sink_and_owned_cleanup(self):
        counter = 0
        def factory():
            nonlocal counter
            counter += 1
            return self.owners.enter_context(DuckDBSink(self.root / str(counter), 'synthetic-conformance'))
        report = qualify_sink(factory, FACTS, LIMITS)
        self.assertEqual(len(report.cases), 21)
        self.assertTrue(all(case.passed for case in report.cases), report)
        self.assertFalse(report.backend_durability_certification)

    def test_admission_before_namespace_creation(self):
        sink = self.sink();e = envelope((FACTS[1],))
        self.reject(SinkErrorCode.INCOMPATIBLE_VERSION, lambda: sink.begin(dataclasses.replace(e, codec_version='future')))
        self.reject(SinkErrorCode.INVALID_CONFIG, lambda: sink.begin(dataclasses.replace(e, destination_scope='foreign')))
        self.reject(SinkErrorCode.RESOURCE_LIMIT, lambda: sink.begin(dataclasses.replace(e, max_results=101)))
        self.assertFalse(self.root.exists())
        self.reject(SinkErrorCode.RESOURCE_LIMIT, lambda: self.sink(max_projection_bytes=67108865))
        self.reject(SinkErrorCode.UNSUPPORTED_CAPABILITY, lambda: self.sink(limits=dataclasses.replace(LIMITS, writer_mode='single_writer')))
        self.assertFalse(self.root.exists())

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
        registry = SinkRegistry[DuckDBSink]();registry.register('duckdb_sink',DuckDBSinkFactory())
        sink = registry.resolve('duckdb_sink',{'output_path':str(self.root),'destination_scope':'synthetic-conformance'},Credentials(),LIMITS)
        self.owners.enter_context(sink);self.assertFalse(self.root.exists())
        receipt = publish(sink,envelope((FACTS[1],)),(FACTS[1],))
        self.assertEqual(self.sink().begin(envelope((FACTS[1],))),receipt)
        for config in ({'output_path':str(self.root),'destination_scope':'synthetic-conformance','max_results':True},
                       {'output_path':'synthetic-sensitive-marker','destination_scope':'synthetic-conformance','unknown':'value'}):
            with self.assertRaises(FactoryError) as caught:
                DuckDBSinkFactory().validate_config(config)
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
        con=duckdb.connect(str(self.root),read_only=True)
        try:
            self.assertEqual(con.execute("SELECT value_int64 FROM efio_cells WHERE feature_id='session.bar.volume'").fetchall(),[(500,)])
            self.assertEqual(con.execute("SELECT value_decimal128 FROM efio_cells WHERE feature_id='session.bar.notional'").fetchall(),[(Decimal(51200),)])
            self.assertEqual(con.execute("SELECT value_float64 FROM efio_cells WHERE feature_id='session.bar.close_weighted_price'").fetchall(),[(102.6,)])
            self.assertEqual(con.execute("SELECT is_null FROM efio_cells WHERE feature_id='session.price.overnight_gap'").fetchall(),[(True,)])
        finally:con.close()


if __name__=='__main__':
    installed='--installed' in sys.argv
    if installed:
        sys.argv.remove('--installed')
        import equity_feature_duckdb_sink,equity_feature_io_contracts,equity_feature_io_sdk,equity_feature_factory_fixture
        for module in (equity_feature_duckdb_sink,equity_feature_io_contracts,equity_feature_io_sdk,equity_feature_factory_fixture):
            assert 'site-packages' in Path(module.__file__).resolve().parts
    report=None
    if '--report-json' in sys.argv:
        index=sys.argv.index('--report-json');report=Path(sys.argv[index+1]);del sys.argv[index:index+2]
    result=unittest.main(exit=False).result
    if report is not None:
        report.write_text(json.dumps(dict(schema='duckdb-sink-installed1',tests=result.testsRun,passed=result.wasSuccessful(),
            installed_public_execution=installed,duckdb_sink=version('equity-feature-duckdb-sink'),duckdb=version('duckdb'),
            io_contracts=version('equity-feature-io-contracts'),io_sdk=version('equity-feature-io-sdk'),
            test_suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            process_qualification=False,private_execution=False),sort_keys=True,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
