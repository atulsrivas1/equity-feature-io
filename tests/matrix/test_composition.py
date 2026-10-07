"""Independent composed installed consumer facts; synthetic data only."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import importlib
from importlib.metadata import distribution,version
import json
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
import unittest

from equity_feature_contracts import AvailabilitySpec,ConfigSpec,EntityKey,Parameter,PriceUnit,SessionSpec,WindowSpec
from equity_feature_contracts.adapters import SourceError,SourceErrorCode,validate_delivery
from equity_feature_contracts.results import Reason,Status
from equity_feature_example_extensions import ExampleSource,ExampleSink,SourceFactory,example_request
from equity_feature_example_extensions.demo import Continue,NoCredentials,calculate
from equity_feature_example_extensions.sink import LIMITS
from equity_feature_io_contracts import FactoryError,PublicationState,SinkError,SinkErrorCode
from equity_feature_io_sdk import SourceRegistry,admit_sink,encode_result,idempotency_key,prepare_publication,publish
from equity_feature_parquet import ParquetSink
from equity_feature_duckdb_sink import DuckDBSink
from equity_features.session import compute_bars

# This committed public fixture uses only synthetic catalog/Parquet facts.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'examples'))
from duckdb_conformance import Fixture

VERSIONS={'equity-feature-contracts':'0.0.4a4','equity-features':'0.0.4a4',
 'equity-feature-io-contracts':'0.1.0a2','equity-feature-io-sdk':'0.1.0a2',
 'equity-feature-duckdb':'0.1.0a8','equity-feature-parquet':'0.1.0a1',
 'equity-feature-duckdb-sink':'0.1.0a0','equity-feature-example-extensions':'0.1.0a0',
 'equity-feature-workers':'0.1.0a1','duckdb':'1.5.6','numpy':'2.2.6','pyarrow':'20.0.0'}
INSTALLED=False

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class Composition(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.owners=ExitStack();self.addCleanup(self.owners.close)
    def sinks(self,label):
        return (ExampleSink(),self.owners.enter_context(ParquetSink(self.root/label/'parquet','synthetic-conformance')),
                self.owners.enter_context(DuckDBSink(self.root/label/'output.duckdb','synthetic-conformance')))
    def expected(self,result,values,namespace,session,unit,cutoff,source,scope):
        self.assertEqual({c.feature_id:c.values[0] for c in result.values},values)
        self.assertEqual({c.algorithm_version for c in result.values},{'v1'})
        self.assertEqual(len(result.values),12);self.assertEqual(result.evidence,())
        for q in result.quality:
            self.assertEqual((q.expected,q.observed),(2,2))
            self.assertEqual((q.status,q.reasons),(Status.MISSING_INPUT,(Reason.ABSENT_INPUT,)) if values[q.feature_id] is None else (Status.AVAILABLE,()))
        m=result.metadata
        self.assertEqual((m.namespace,m.session_id,m.backend_id,m.backend_version,m.schema_version,m.math_policy_version,m.evidence_limit),(namespace,session,'python-exact','0.0.4a4','1','v1',0))
        self.assertEqual((m.availability.market_cutoff_ns,m.availability.knowledge_cutoff_ns,m.availability.evaluation_ns),cutoff)
        self.assertEqual(len(m.inputs),1);binding=m.inputs[0]
        self.assertEqual(binding.role,'bars');self.assertEqual(binding.metadata.source,source)
        self.assertEqual(binding.metadata.price_unit,unit)
        self.assertEqual((binding.metadata.coverage.expected,binding.metadata.coverage.observed,binding.metadata.coverage.complete),(2,2,True))
        self.assertEqual((binding.metadata.scope.start_ns,binding.metadata.scope.end_ns,binding.metadata.scope.eligibility_policy),scope)
        units={c.feature_id:c.unit for c in result.values}
        self.assertEqual(units['session.bar.volume'],'shares')
        self.assertEqual(units['session.bar.notional'],'currency coefficient / 10^price_scale')
        self.assertEqual(units['session.bar.close_weighted_price'],'currency/share; proxy')
    def roundtrip(self,result,label):
        reference=encode_result(result)
        for sink in self.sinks(label):
            e=prepare_publication((result,),destination_scope='synthetic-conformance',generation_id=label,job_id='matrix',partition_id='one',limits=LIMITS)
            receipt=publish(sink,e,(result,));self.assertEqual((receipt.result_count,receipt.cell_count,receipt.evidence_count),(1,12,0))
            self.assertEqual(tuple(map(encode_result,sink.read(receipt))),(reference,))
            self.assertEqual(publish(sink,e,(result,)),receipt)
            self.assertEqual(sink.lookup(receipt.idempotency_key).receipt,receipt)
    def test_custom_direct_and_factory_full_twelve_facts_to_all_sinks(self):
        registry=SourceRegistry();registry.register('custom',SourceFactory())
        direct=ExampleSource();factory=registry.resolve('custom',{'namespace':'demo'},NoCredentials(),example_request())
        outputs=[]
        for label,source in (('direct',direct),('factory',factory)):
            result=calculate(source)
            values={'session.bar.open':100.0,'session.bar.high':104.0,'session.bar.low':99.0,'session.bar.close':103.0,
              'session.bar.volume':500,'session.bar.notional':51200,'session.bar.close_weighted_price':102.6,
              'session.price.open_close_return':3/100,'session.price.range_fraction':5/103,'session.price.close_location':4/5,
              'session.price.overnight_gap':None,'session.price.close_close_return':None}
            from equity_feature_contracts import SourceBinding
            self.expected(result,values,'demo','S',PriceUnit(0,'USD'),(200,210,210),SourceBinding('synthetic','snapshot1','map1','bars1'),(100,200,'example-v1'))
            self.assertEqual(result.metadata.config_digest,'ddc1b3b90e8d3333f31c268228e472aa440029f3f6ba7d72745d2f0096c3c931')
            outputs.append(encode_result(result));self.roundtrip(result,label)
        self.assertEqual(outputs[0],outputs[1])
    def test_standalone_minute_source_null_notional_to_all_sinks_source_unchanged(self):
        fixture=Fixture(self.root/'source','ohlcv-1m');request=fixture.request();source=fixture.adapter(complete=2)
        sourcefiles=[fixture.db,*fixture.root.rglob('*.parquet')]
        before={str(p):digest(p) for p in sourcefiles};wal=Path(str(fixture.db)+'.wal');self.assertFalse(wal.exists())
        deliveries=tuple(source.iter_batches(request,Continue()));validate_delivery(request,source.capabilities(),deliveries)
        self.assertEqual(len(deliveries),1);batch=deliveries[0].batch;self.assertIsNotNone(batch)
        columns={c.name:c.values for c in batch.columns}
        self.assertEqual(columns['start_ns'],(0,60000000000));self.assertEqual(columns['end_ns'],(60000000000,120000000000))
        for name,expected in {'open':(1000,1100),'high':(1200,1400),'low':(900,1000),'close':(1100,1200),'volume':(3,5),'known_at_ns':(1,1)}.items():self.assertEqual(columns[name],expected)
        self.assertNotIn('actual_notional',columns)
        config=ConfigSpec('matrix-minute','v1',(Parameter('eligibility_policy','synthetic1'),),fixture.sessions[0],
                          WindowSpec(1,'S1',('P','S1')),AvailabilitySpec(120000000000,120000000000,120000000000),price_unit=PriceUnit(2,'USD'))
        result=compute_bars(batch,config,entity=EntityKey('A','S1'))
        expected={'session.bar.open':10.0,'session.bar.high':14.0,'session.bar.low':9.0,'session.bar.close':12.0,
          'session.bar.volume':8,'session.bar.notional':None,'session.bar.close_weighted_price':11.625,
          'session.price.open_close_return':.2,'session.price.range_fraction':5/12,'session.price.close_location':.6,
          'session.price.overnight_gap':None,'session.price.close_close_return':None}
        self.expected(result,expected,'sdk','S1',PriceUnit(2,'USD'),(120000000000,)*3,batch.metadata.source,(0,120000000000,'synthetic1'))
        self.roundtrip(result,'minute')
        self.assertEqual({str(p):digest(p) for p in sourcefiles},before);self.assertFalse(wal.exists())
    def test_actual_installed_versions_workers_version_only(self):
        for name,v in VERSIONS.items():
            self.assertEqual(version(name),v)
            if INSTALLED:
                module=importlib.import_module(name.replace('-','_'))
                self.assertIn('site-packages',Path(module.__file__).resolve().parts)
        import equity_feature_workers as workers
        self.assertEqual(workers.__all__,['__version__']);self.assertEqual(distribution('equity-feature-workers').requires,['equity-feature-io-sdk==0.1.0a2']);self.assertFalse(distribution('equity-feature-workers').entry_points)
    def test_unsupported_codec_and_writer_rejected_before_publication(self):
        for sink in self.sinks('reject'):
            for requirements in (replace(LIMITS,codec_version='unknown'),replace(LIMITS,writer_mode='conflict_safe_multi_writer')):
                with self.assertRaises(FactoryError):admit_sink(sink,requirements)
    def test_failed_partial_write_has_no_successful_receipt(self):
        class Fails(ExampleSink):
            def write(self,session,ordinal,result):
                super().write(session,ordinal,result);raise SinkError(SinkErrorCode.UNAVAILABLE)
        result=calculate(ExampleSource());sink=Fails();e=prepare_publication((result,),destination_scope='synthetic-conformance',generation_id='fail',job_id='matrix',partition_id='one',limits=LIMITS)
        with self.assertRaises(SinkError):publish(sink,e,(result,))
        status=sink.lookup(idempotency_key(e.identity));self.assertEqual(status.state,PublicationState.ABORTED);self.assertIsNone(status.receipt)
    def test_source_failure_precedes_output_construction(self):
        class Fails(ExampleSource):
            def iter_batches(self,request,cancellation):raise SourceError(SourceErrorCode.TRANSPORT,'synthetic transport failure')
        with self.assertRaises(SourceError):calculate(Fails())

def main():
    global INSTALLED
    p=argparse.ArgumentParser();p.add_argument('--report-json',required=True,type=Path);p.add_argument('--installed',action='store_true');a=p.parse_args();INSTALLED=a.installed
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Composition);result=unittest.TextTestRunner(verbosity=2).run(suite)
    record={'schema':'composition-matrix1','passed':result.wasSuccessful(),'tests':result.testsRun,
            'full_result_sink_compositions':9,'versions':VERSIONS,'system':platform.system(),'python':platform.python_version(),
            'source_wal_present_qualified':False,'actual_installed_modules':INSTALLED,'test_suite_sha256':digest(Path(__file__))}
    a.report_json.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
if __name__=='__main__':main()
