"""Independent public installed extension expectations, no private/provider data."""
import argparse
from dataclasses import replace
import hashlib
import importlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import traceback
import unittest

from equity_feature_contracts.adapters import SourceError, SourceErrorCode, validate_delivery
from equity_feature_contracts.inputs import Coverage, PriceUnit, SourceBinding
from equity_feature_contracts.results import Reason, Status
from equity_feature_example_extensions import ExampleSink, ExampleSource, SinkFactory, SourceFactory, example_request
from equity_feature_example_extensions.demo import Continue, calculate, run_example
from equity_feature_example_extensions.sink import LIMITS
from equity_feature_factory_fixture.publication_facts import synthetic_results
from equity_feature_io_contracts import FactoryError, SinkError, SinkErrorCode, PublicationState, CompletionReceipt
from equity_feature_io_sdk import (
    SinkRegistry, SourceRegistry, admit_sink, admit_source, encode_result, idempotency_key,
    prepare_publication, publish, qualify_sink,
)

MARKER = 'synthetic-sensitive-fixture-marker'
FACTS = synthetic_results()


def envelope(results=FACTS, **kw):
    return prepare_publication(results, destination_scope='synthetic-conformance', generation_id='g1',
                               job_id='j1', partition_id='p1', limits=LIMITS, **kw)


class Credentials:
    def __init__(self):self.calls=0
    def get(self,name):self.calls+=1;raise AssertionError(MARKER)
    def __repr__(self):raise AssertionError('must not format credential provider')


class Extensions(unittest.TestCase):
    def test_direct_factory_independent_values_quality_metadata_and_complete_bytes(self):
        direct=run_example();factory=run_example(factory=True)
        self.assertEqual(tuple(map(encode_result,direct[2])),tuple(map(encode_result,factory[2])))
        self.assertEqual(direct[1],factory[1])
        for result,receipt,readback in (direct,factory):
            values={c.feature_id:c.values[0] for c in result.values}
            expected={'session.bar.open':100.0,'session.bar.high':104.0,'session.bar.low':99.0,
                      'session.bar.close':103.0,'session.bar.volume':500,'session.bar.notional':51200,
                      'session.bar.close_weighted_price':102.6,'session.price.open_close_return':3/100,
                      'session.price.range_fraction':5/103,'session.price.close_location':4/5,
                      'session.price.overnight_gap':None,'session.price.close_close_return':None}
            self.assertEqual(values,expected)
            qualities={q.feature_id:q for q in result.quality}
            for name in values:
                q=qualities[name];self.assertEqual((q.expected,q.observed),(2,2))
                if expected[name] is None:self.assertEqual((q.status,q.reasons),(Status.MISSING_INPUT,(Reason.ABSENT_INPUT,)))
                else:self.assertEqual((q.status,q.reasons),(Status.AVAILABLE,()))
            m=result.metadata;self.assertEqual((m.namespace,m.session_id,m.backend_id,m.backend_version,m.schema_version,m.math_policy_version),('demo','S','python-exact','0.0.4a4','1','v1'))
            self.assertEqual((m.availability.market_cutoff_ns,m.availability.knowledge_cutoff_ns,m.availability.evaluation_ns),(200,210,210))
            self.assertEqual(m.config_digest,'ddc1b3b90e8d3333f31c268228e472aa440029f3f6ba7d72745d2f0096c3c931')
            self.assertEqual(len(m.inputs),1);binding=m.inputs[0]
            self.assertEqual((binding.role,binding.metadata.source,binding.metadata.coverage),('bars',SourceBinding('synthetic','snapshot1','map1','bars1'),Coverage(2,2,True)))
            self.assertEqual((binding.metadata.price_unit,binding.metadata.scope.start_ns,binding.metadata.scope.end_ns),(PriceUnit(0,'USD'),100,200))
            self.assertEqual(result.evidence,());self.assertEqual(m.evidence_limit,0)
            self.assertEqual({c.algorithm_version for c in result.values},{'v1'})
            units={c.feature_id:c.unit for c in result.values}
            self.assertEqual(units['session.bar.volume'],'shares');self.assertEqual(units['session.bar.notional'],'currency coefficient / 10^price_scale')
            self.assertEqual(units['session.bar.close_weighted_price'],'currency/share; proxy')
            self.assertEqual(tuple(map(encode_result,readback)),(encode_result(result),))
            self.assertEqual((receipt.result_count,receipt.cell_count,receipt.evidence_count),(1,12,0))

    def test_source_literal_delivery_and_no_acquisition_during_admission(self):
        request=example_request();creds=Credentials();sources=SourceRegistry();sources.register('custom.bars',SourceFactory())
        source=sources.resolve('custom.bars',{'namespace':'demo'},creds,request);self.assertEqual(creds.calls,0)
        deliveries=tuple(source.iter_batches(request,Continue()));validate_delivery(request,source.capabilities(),deliveries)
        self.assertEqual(len(deliveries),1);d=deliveries[0]
        self.assertEqual((d.request_id,d.ordinal,d.final,d.source_coverage,d.delivery_coverage),('req1',0,True,Coverage(2,2,True),Coverage(2,2,True)))
        cols={c.name:c.values for c in d.batch.columns}
        self.assertEqual(cols,{'instrument_id':('A','A'),'session_id':('S','S'),'start_ns':(100,150),'end_ns':(150,200),'known_at_ns':(150,210),'open':(100,102),'high':(103,104),'low':(99,101),'close':(102,103),'volume':(200,300),'actual_notional':(20300,30900)})

    def test_source_cancellation_and_unsupported_requests(self):
        class Cancel:
            def is_cancelled(self):return True
        source=ExampleSource();request=example_request()
        self.assertEqual(tuple(source.iter_batches(request,Cancel())),())
        for wrong in (replace(request,sessions=('P',)),replace(request,snapshot_id='other'),replace(request,availability=replace(request.availability,knowledge_cutoff_ns=211,evaluation_ns=211))):
            with self.assertRaises(SourceError) as caught:tuple(source.iter_batches(wrong,Continue()))
            self.assertEqual(caught.exception.code,SourceErrorCode.UNSUPPORTED)
        for wrong in (replace(request,price_unit=PriceUnit(0,'EUR')),replace(request,max_batch_rows=3,max_rows=3)):
            with self.assertRaises(FactoryError):admit_source(source,wrong)
        with self.assertRaises(FactoryError):admit_source(source,request,live=True)

    def test_wrong_schema_capability_and_requirement_rejected(self):
        class WrongSchema:
            def capabilities(self):
                from types import SimpleNamespace
                return SimpleNamespace(schema_version='2')
            def iter_batches(self,request,cancellation):raise AssertionError('must not acquire')
        with self.assertRaises(FactoryError):admit_source(WrongSchema(),example_request())
        for limits in (replace(LIMITS,writer_mode='conflict_safe_multi_writer'),replace(LIMITS,codec_version='codec2'),replace(LIMITS,max_results=101)):
            with self.assertRaises(FactoryError):admit_sink(ExampleSink(),limits)
        with self.assertRaises(SinkError) as caught:ExampleSink().begin(replace(envelope(),codec_version='codec2'))
        self.assertEqual(caught.exception.code,SinkErrorCode.INCOMPATIBLE_VERSION)

    def test_explicit_registry_isolation_config_secrets_and_no_credentials(self):
        creds=Credentials();a=SinkRegistry();b=SinkRegistry();a.register('custom.memory',SinkFactory())
        with self.assertRaises(FactoryError):b.resolve('custom.memory',{},creds,LIMITS)
        with self.assertRaises(FactoryError):a.register('custom.memory',SinkFactory())
        sink=a.resolve('custom.memory',{'destination_scope':'synthetic-conformance'},creds,LIMITS)
        self.assertIsInstance(sink,ExampleSink);self.assertEqual(creds.calls,0)
        for config in ({'destination_scope':'other'},{'destination_scope':'synthetic-conformance','api_key':MARKER},{'destination_scope':'synthetic-conformance','module':MARKER},{'destination_scope':[MARKER]}):
            with self.assertRaises(FactoryError) as caught:a.resolve('custom.memory',config,creds,LIMITS)
            self.assertNotIn(MARKER,''.join(traceback.format_exception(caught.exception)))
        sources=SourceRegistry();sources.register('custom.bars',SourceFactory())
        with self.assertRaises(FactoryError):sources.resolve('custom.bars',{'namespace':'other'},creds,example_request())

    def test_constructor_failure_is_redacted_and_source_failure_propagates(self):
        class BrokenFactory(SinkFactory):
            def create(self,config,credentials):raise RuntimeError(MARKER)
        registry=SinkRegistry();registry.register('broken',BrokenFactory())
        with self.assertRaises(FactoryError) as caught:registry.resolve('broken',{'destination_scope':'synthetic-conformance'},Credentials(),LIMITS)
        self.assertNotIn(MARKER,''.join(traceback.format_exception(caught.exception)))
        class BrokenSource(ExampleSource):
            def iter_batches(self,request,cancellation):raise SourceError(SourceErrorCode.UNAVAILABLE,'synthetic unavailable')
        with self.assertRaises(SourceError) as caught:calculate(BrokenSource())
        self.assertEqual(caught.exception.code,SourceErrorCode.UNAVAILABLE)

    def test_public_sink_conformance_all_complete_synthetic_records(self):
        report=qualify_sink(ExampleSink,FACTS,LIMITS)
        self.assertEqual(len(report.cases),21);self.assertTrue(report.passed);self.assertFalse(report.backend_durability_certification)
        sink=ExampleSink();receipt=publish(sink,envelope(),FACTS)
        self.assertEqual(tuple(map(encode_result,sink.read(receipt))),tuple(map(encode_result,FACTS)))

    def test_publication_failure_aborts_without_fabricating_receipt(self):
        class BrokenSink(ExampleSink):
            def write(self,session,ordinal,result):raise RuntimeError(MARKER)
        sink=BrokenSink();e=envelope()
        with self.assertRaises(SinkError) as caught:publish(sink,e,FACTS)
        self.assertNotIn(MARKER,''.join(traceback.format_exception(caught.exception)))
        status=sink.lookup(idempotency_key(e.identity));self.assertEqual(status.state,PublicationState.ABORTED);self.assertIsNone(status.receipt)

    def test_publication_preexisting_cancellation_and_after_commit(self):
        class Cancel:
            def is_cancelled(self):return True
        sink=ExampleSink();e=envelope()
        with self.assertRaises(SinkError) as caught:publish(sink,e,FACTS,cancellation=Cancel())
        self.assertEqual(caught.exception.code,SinkErrorCode.CANCELLED)
        status=sink.lookup(idempotency_key(e.identity))
        self.assertEqual(status.state,PublicationState.ABORTED);self.assertIsNone(status.receipt)
        class CommitThenCancel(ExampleSink):
            def commit(self,session):
                receipt=super().commit(session);self.cancelled=True;return receipt
        sink=CommitThenCancel();sink.cancelled=False
        class Observe:
            def is_cancelled(self):return sink.cancelled
        receipt=publish(sink,e,FACTS,cancellation=Observe())
        self.assertEqual(sink.lookup(receipt.idempotency_key).receipt,receipt)

    def test_cancellation_during_staging_invalidates_original_handle(self):
        class State:
            cancelled=False
            def is_cancelled(self):return self.cancelled
        token=State()
        class CancelAfterWrite(ExampleSink):
            def write(self,session,ordinal,result):super().write(session,ordinal,result);token.cancelled=True
        sink=CancelAfterWrite();e=envelope()
        with self.assertRaises(SinkError) as caught:publish(sink,e,FACTS,cancellation=token)
        self.assertEqual(caught.exception.code,SinkErrorCode.CANCELLED)
        status=sink.lookup(idempotency_key(e.identity));self.assertEqual(status.state,PublicationState.ABORTED);self.assertIsNone(status.receipt)

    def test_zero_empty_foreign_stale_and_retained_corruption(self):
        sink=ExampleSink();zero=publish(sink,envelope(()),());self.assertEqual(sink.read(zero),());self.assertEqual(zero.artifacts,())
        empty=publish(sink,replace(envelope((FACTS[0],)),generation_id='empty'),(FACTS[0],));self.assertEqual(empty.result_count,1);self.assertEqual(len(empty.artifacts),1)
        e=replace(envelope(),generation_id='retry');old=sink.begin(e);self.assertNotIsInstance(old,CompletionReceipt)
        sink.abort(old);new=sink.begin(e)
        with self.assertRaises(SinkError) as caught:sink.write(old,0,FACTS[0])
        self.assertEqual(caught.exception.code,SinkErrorCode.INVALID_SESSION)
        with self.assertRaises(SinkError):ExampleSink().write(new,0,FACTS[0])
        # Explicit test-only mutation demonstrates retained data cannot fabricate a success.
        sink._records[empty.idempotency_key].data[0]=b'bad'
        for operation in (lambda:sink.read(empty),lambda:sink.lookup(empty.idempotency_key),lambda:sink.begin(replace(envelope((FACTS[0],)),generation_id='empty'))):
            with self.assertRaises(SinkError) as caught:operation()
            self.assertEqual(caught.exception.code,SinkErrorCode.CORRUPTION)

    def test_import_public_package_is_side_effect_free_and_dependency_light(self):
        module=importlib.import_module('equity_feature_example_extensions')
        self.assertEqual(module.__version__,'0.1.0a0')
        self.assertEqual(module.__all__,['__version__','ExampleSource','ExampleSink','SourceFactory','SinkFactory','example_request'])
        self.assertFalse(any(isinstance(value,(ExampleSource,ExampleSink,SourceRegistry,SinkRegistry)) for value in vars(module).values()))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');parser.add_argument('--report-json',required=True,type=Path);args=parser.parse_args()
    if args.installed:
        origin=Path(importlib.import_module('equity_feature_example_extensions').__file__).resolve()
        assert 'site-packages' in origin.parts and 'examples' not in origin.parts,origin
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Extensions);count=suite.countTestCases();assert count==12
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(schema='example-extension-installed1',tests=count,passed=result.wasSuccessful(),installed_public_execution=args.installed,
                python=platform.python_version(),system=platform.system(),extensions=version('equity-feature-example-extensions'),
                io_sdk=version('equity-feature-io-sdk'),io_contracts=version('equity-feature-io-contracts'),
                canonical=version('equity-feature-contracts'),features=version('equity-features'),
                actual_conformance_cases=21,complete_synthetic_results=len(FACTS),private_execution=False,backend_durability_certification=False,
                test_suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.report_json.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
