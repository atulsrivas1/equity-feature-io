"""Real isolated local child termination/restart and cooperative writer tests."""
import dataclasses
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from equity_feature_factory_fixture.publication_facts import synthetic_results
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_contracts.publication import CompletionReceipt, PublicationState, SinkError, SinkErrorCode
from equity_feature_io_sdk.codec import decode_receipt, encode_receipt, encode_result, idempotency_key
from equity_feature_io_sdk.publication import prepare_publication,publish
from equity_feature_duckdb_sink import DuckDBSink

FACTS=synthetic_results()
LIMITS=SinkRequirements(max_results=100,max_chunk_bytes=1048576,max_total_bytes=10485760,max_result_cells=100000,max_evidence_rows=100000)
CHILD=Path(__file__).with_name('process_child.py').resolve()


def envelope(facts=FACTS,**changes):
    e=prepare_publication(facts,destination_scope='synthetic-process',generation_id='generation',job_id='job',partition_id='partition',limits=LIMITS)
    return dataclasses.replace(e,**changes)


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)/'destination';self.children=[]

    def stop(self,child):
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill();child.wait(timeout=10)
        for stream in (child.stdin,child.stdout,child.stderr):
            if stream is not None:stream.close()

    def tearDown(self):
        for child in self.children:self.stop(child)
        self.temp.cleanup()

    def child(self,phase,*,different=False):
        marker=Path(self.temp.name)/('checkpoint'+str(len(self.children))+'.json')
        args=[sys.executable,'-I',str(CHILD),phase,str(self.root),str(marker)]
        if different:args.append('--different')
        child=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        self.children.append(child)
        return child,marker

    def checkpoint(self,child,marker):
        deadline=time.monotonic()+30
        while not marker.exists():
            if child.poll() is not None:
                stdout,stderr=child.communicate();self.fail('child exited before controlled boundary: '+stdout+stderr)
            if time.monotonic()>deadline:self.fail('controlled boundary timeout')
            time.sleep(.02)
        # The observer flushes its complete JSON before pausing.
        for _ in range(100):
            try:return json.loads(marker.read_text(encoding='utf-8'))
            except json.JSONDecodeError:time.sleep(.01)
        self.fail('incomplete checkpoint')

    def outcome(self,child):
        stdout,stderr=child.communicate(timeout=30)
        self.assertEqual(child.returncode,0,stderr)
        return json.loads(stdout)

    def interrupted(self,phase,committed):
        child,marker=self.child(phase);record=self.checkpoint(child,marker)
        e=envelope();key=idempotency_key(e.identity)
        self.assertEqual(record['key'],key)
        with DuckDBSink(self.root,'synthetic-process',caller_committed_at_ns=999) as observer:
            with self.assertRaises(SinkError) as caught:observer.lookup(key)
            self.assertEqual(caught.exception.code,SinkErrorCode.BUSY)
            self.stop(child)
            status=observer.lookup(key)
            self.assertEqual(status.state,PublicationState.COMMITTED if committed else PublicationState.STAGING)
            original=status.receipt
            if not committed:self.assertIsNone(original)
            else:
                self.assertEqual(original.caller_committed_at_ns,17)
                self.assertEqual(tuple(map(encode_result,observer.read(original))),tuple(map(encode_result,FACTS)))
            restarted=observer.begin(e)
            if committed:
                self.assertIsInstance(restarted,CompletionReceipt)
                self.assertEqual(encode_receipt(restarted),encode_receipt(original))
            else:
                self.assertNotEqual(restarted.attempt_id,record['attempt_id'])
                for ordinal,result in enumerate(FACTS):observer.write(restarted,ordinal,result)
                restarted=observer.commit(restarted)
                self.assertEqual(restarted.caller_committed_at_ns,999)
            self.assertEqual(tuple(map(encode_result,observer.read(restarted))),tuple(map(encode_result,FACTS)))
            self.assertEqual(observer.lookup(key).receipt,restarted)

    def test_terminated_after_durable_reservation(self):self.interrupted('reservation',False)
    def test_terminated_after_first_sql_insert(self):self.interrupted('partial',False)
    def test_terminated_after_all_components(self):self.interrupted('components',False)
    def test_terminated_before_transaction_commit(self):self.interrupted('before_manifest',False)
    def test_terminated_after_visible_commit_lost_response(self):self.interrupted('after_manifest',True)

    def test_rejected_arbitrary_source_database_and_wal_byte_invariance_after_writer_exit(self):
        child,marker=self.child('source_wal');self.checkpoint(child,marker);self.stop(child)
        wal=Path(str(self.root)+'.wal')
        self.assertTrue(wal.is_file())
        def read_all():
            for attempt in range(40):
                try:return (self.root.read_bytes(),wal.read_bytes())
                except PermissionError:
                    if attempt==39:raise
                    time.sleep(.05)
        before=read_all()
        with DuckDBSink(self.root,'synthetic-process') as sink:
            with self.assertRaises(SinkError) as caught:sink.begin(envelope())
            self.assertEqual(caught.exception.code,SinkErrorCode.INVALID_CONFIG)
        self.assertTrue(wal.is_file());self.assertEqual(before,read_all())

    def test_live_process_ownership_same_other_key_and_changed_content(self):
        child,marker=self.child('reservation');self.checkpoint(child,marker)
        changed=list(FACTS);changed[1]=dataclasses.replace(changed[1],values=(dataclasses.replace(changed[1].values[0],values=(-(2**63)+1,)),))
        with DuckDBSink(self.root,'synthetic-process') as contender:
            for e,code in ((envelope(),SinkErrorCode.BUSY),(envelope(generation_id='other'),SinkErrorCode.BUSY),(envelope(tuple(changed)),SinkErrorCode.BUSY)):
                with self.assertRaises(SinkError) as caught:contender.begin(e)
                self.assertEqual(caught.exception.code,code)
            self.stop(child)
            receipt=publish(contender,envelope(),FACTS)
            self.assertEqual(tuple(map(encode_result,contender.read(receipt))),tuple(map(encode_result,FACTS)))

    def test_two_actual_same_content_writers_original_replay(self):
        first,_=self.child('publish');second,_=self.child('publish')
        outcomes=[self.outcome(first),self.outcome(second)]
        self.assertTrue(all(o['outcome'] in ('committed','BUSY') for o in outcomes),[o['outcome'] for o in outcomes])
        committed=[decode_receipt(o['receipt'].encode('ascii')) for o in outcomes if o['outcome']=='committed']
        self.assertTrue(committed)
        with DuckDBSink(self.root,'synthetic-process',caller_committed_at_ns=999) as retry:
            replay=retry.begin(envelope())
            self.assertTrue(all(encode_receipt(r)==encode_receipt(replay) for r in committed))
            self.assertEqual(replay.caller_committed_at_ns,17)
            self.assertEqual(retry.read(replay),FACTS)

    def test_two_actual_different_content_writers_conflict(self):
        first,_=self.child('publish');second,_=self.child('publish',different=True)
        outcomes=[self.outcome(first),self.outcome(second)]
        codes=[o['outcome'] for o in outcomes]
        self.assertEqual(codes.count('committed'),1,codes)
        self.assertTrue(all(code in ('committed','BUSY','CONFLICT') for code in codes),codes)
        # Contention can precede the durable first reservation. After the winner
        # is committed, the loser's distinct logical content must conflict.
        loser=codes.index('BUSY') if 'BUSY' in codes else codes.index('CONFLICT')
        changed=list(FACTS)
        changed[1]=dataclasses.replace(changed[1],values=(dataclasses.replace(changed[1].values[0],values=(-(2**63)+1,)),))
        with DuckDBSink(self.root,'synthetic-process') as retry:
            with self.assertRaises(SinkError) as caught:retry.begin(envelope(FACTS if loser==0 else tuple(changed)))
            self.assertEqual(caught.exception.code,SinkErrorCode.CONFLICT)


if __name__=='__main__':
    installed='--installed' in sys.argv
    if installed:
        sys.argv.remove('--installed')
        import equity_feature_duckdb_sink,equity_feature_io_sdk,equity_feature_factory_fixture
        for module in (equity_feature_duckdb_sink,equity_feature_io_sdk,equity_feature_factory_fixture):
            assert 'site-packages' in Path(module.__file__).resolve().parts
    report=None
    if '--report-json' in sys.argv:
        index=sys.argv.index('--report-json');report=Path(sys.argv[index+1]);del sys.argv[index:index+2]
    result=unittest.main(exit=False).result
    if report is not None:
        report.write_text(json.dumps(dict(schema='duckdb-sink-process1',tests=result.testsRun,passed=result.wasSuccessful(),
            installed_public_execution=installed,actual_owned_child_processes=True,python=platform.python_version(),
            system=platform.system(),machine=platform.machine(),duckdb_sink=version('equity-feature-duckdb-sink'),duckdb=version('duckdb'),
            io_sdk=version('equity-feature-io-sdk'),child_sha256=hashlib.sha256(CHILD.read_bytes()).hexdigest(),
            test_suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            power_loss_qualification=False,network_filesystem_qualification=False,private_execution=False),sort_keys=True,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
