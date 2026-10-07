"""Independent publication vectors/fault expectations, also run from installed forms."""
import dataclasses
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import traceback
import unittest

from equity_feature_contracts import inputs as i, results as r, specs as s
from equity_feature_factory_fixture.publication import MemorySink
from equity_feature_factory_fixture.publication_facts import synthetic_results
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_contracts.publication import *
from equity_feature_io_sdk.codec import (
    RECORDS, ENUMS, canonical_json, to_wire, encode_result, decode_result,
    encode_envelope, decode_envelope, encode_receipt, decode_receipt,
    descriptor, content_digest, identity_wire, idempotency_key,
)
from equity_feature_io_sdk.conformance import qualify_sink
from equity_feature_io_sdk.publication import prepare_publication, publish, verify_content, verify_receipt

LIMITS = SinkRequirements(max_results=100, max_chunk_bytes=1048576, max_total_bytes=10485760,
                          max_result_cells=100000, max_evidence_rows=100000)
GOLDENS = json.loads(Path(__file__).with_name('publication_goldens.json').read_text(encoding='utf-8'))
SENSITIVE = 'synthetic_sensitive_fixture_marker'


def envelope(results, **changes):
    return prepare_publication(results, destination_scope='dest', generation_id='gen', job_id='job',
                               partition_id='partition', limits=LIMITS, **changes)


def golden_result(name):
    entity = r.EntityKey('I', 'S')
    metadata = r.ResultMetadata('synthetic', 'S', s.AvailabilitySpec(10, 10, 10), '0'*64, (), 'synthetic', '1')
    dtype, value, status, expected, observed, reasons = {
        'count': (r.ValueType.INT64, 0, r.Status.AVAILABLE, 0, 0, ()),
        'missing': (r.ValueType.INT64, None, r.Status.MISSING_INPUT, None, 0, (r.Reason.ABSENT_INPUT,)),
        'partial': (r.ValueType.BREADTH_COUNTS, r.BreadthCounts(1, 0, 0, 2), r.Status.INCOMPLETE_COVERAGE, 2, 1, (r.Reason.PARTIAL_UNIVERSE,)),
    }[name]
    fid = 'synthetic.'+name
    return r.FeatureResult((r.FeatureColumn(fid, '1', dtype, 'count', (entity,), (value,)),),
                           (r.QualityRow(entity, fid, status, expected, observed, reasons),), metadata)


class PublicationTests(unittest.TestCase):
    def reject(self, code, operation):
        with self.assertRaises(SinkError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assertNotIn(SENSITIVE, rendered)
        self.assertNotIn(SENSITIVE, str(caught.exception))
        self.assertNotIn(SENSITIVE, repr(caught.exception))

    def test_three_nonempty_hand_written_wire_content_and_key_goldens(self):
        for name in ('count', 'missing', 'partial'):
            with self.subTest(name=name):
                result = golden_result(name); golden = GOLDENS[name]
                self.assertEqual(encode_result(result), golden['ascii'].encode('ascii'))
                self.assertEqual(len(encode_result(result)), golden['bytes'])
                self.assertEqual(decode_result(golden['ascii'].encode('ascii')), result)
                self.assertEqual(content_digest((result,)), golden['content_sha256'])
                e = envelope((result,))
                self.assertEqual(canonical_json(identity_wire(e.identity)), golden['key_ascii'].encode('ascii'))
                self.assertEqual(idempotency_key(e.identity), golden['idempotency_key'])

    def test_empty_and_zero_distinctions_frozen_sha(self):
        empty = synthetic_results()[0]
        self.assertEqual(len(encode_result(empty)), 607)
        self.assertEqual(content_digest((empty,)), 'c44d3b04e6f721a11dcce6d0232b2125d61a48a55d73f8cc168deb43e27b1a2c')
        self.assertEqual(content_digest(()), 'fbe925a7019c2ebb4df50356cc17f1666e1e0f6d39b01dcd4bdc6a2b24fe9a43')
        for results in ((), (empty,)):
            receipt = publish(MemorySink(), envelope(results), results)
            self.assertEqual(receipt.result_count, len(results))

    def test_hand_written_source_evidence_wire_content_key_and_causal_rejection(self):
        entity=r.EntityKey('A','S')
        batch=i.BatchMetadata('demo',i.SourceBinding('synthetic','snapshot','map1','input1'),i.Coverage(1,1,True),i.PriceUnit(4,'USD'))
        metadata=r.ResultMetadata('demo','S',s.AvailabilitySpec(200,210,210),'0'*64,(r.InputBinding('market',i.DataKind.TRADE,batch),),'caller:fixture','v1',2)
        result=r.FeatureResult((r.FeatureColumn('demo:count','v1',r.ValueType.INT64,'shares',(entity,),(1,)),),
                               (r.QualityRow(entity,'demo:count',r.Status.AVAILABLE,1,1),),metadata,
                               (r.EvidenceRow(entity,'demo:count','input1','row1',199,210),))
        golden=GOLDENS['evidence'];e=envelope((result,))
        self.assertEqual(encode_result(result),golden['ascii'].encode('ascii'))
        self.assertEqual(content_digest((result,)),golden['content_sha256'])
        self.assertEqual(canonical_json(identity_wire(e.identity)),golden['key_ascii'].encode('ascii'))
        self.assertEqual(idempotency_key(e.identity),golden['idempotency_key'])
        self.reject(SinkErrorCode.INVALID_CONTENT,lambda:decode_result(golden['ascii'].encode('ascii').replace(b'"known_at_ns":{"int":"210"}',b'"known_at_ns":null')))
        excluded=dataclasses.replace(result,evidence=(dataclasses.replace(result.evidence[0],known_at_ns=None,use='excluded',exclusion_reason=r.Reason.UNKNOWN_AVAILABILITY),))
        self.assertEqual(idempotency_key(envelope((excluded,)).identity),idempotency_key(e.identity))
        self.assertNotEqual(content_digest((excluded,)),golden['content_sha256'])

    def test_exact_scalars_and_unicode_no_normalization(self):
        cases = [(0, b'{"int":"0"}'), (-(2**63), b'{"int":"-9223372036854775808"}'),
                 (10**38-1, b'{"int":"99999999999999999999999999999999999999"}'),
                 (0.0, b'{"float64":"0x0.0p+0"}'), (-0.0, b'{"float64":"-0x0.0p+0"}'),
                 (1.25, b'{"float64":"0x1.4000000000000p+0"}'), (False, b'false'), ('0', b'"0"'),
                 (None, b'null'), ('e\u0301', b'"e\\u0301"'), ('\u00e9', b'"\\u00e9"')]
        for value, expected in cases:
            self.assertEqual(canonical_json(to_wire(value)), expected)

    def test_all_closed_records_and_enums_preserve_full_structured_content(self):
        results = synthetic_results()
        names = set(); enums = set()
        def visit(wire):
            if isinstance(wire, dict):
                if 'record' in wire: names.add(wire['record'])
                if 'enum' in wire: enums.add(wire['enum'])
                for item in wire.values(): visit(item)
            elif isinstance(wire, list):
                for item in wire: visit(item)
        for result in results:
            data = encode_result(result); visit(json.loads(data))
            self.assertEqual(encode_result(decode_result(data)), data)
        self.assertEqual(names, set(RECORDS)); self.assertEqual(enums, set(ENUMS))
        sink = MemorySink(); receipt = publish(sink, envelope(results), results)
        observed = sink.read(receipt)
        self.assertEqual(tuple(map(encode_result, observed)), tuple(map(encode_result, results)))
        self.assertEqual(observed[4].values[0].values[0].hex(), '-0x0.0p+0')
        self.assertIsNone(observed[8].values[0].values[0])
        self.assertEqual(observed[9].values[0].values[0].coverage.numerator, 1)
        self.assertEqual(observed[9].values[0].values[0].coverage.denominator, 2)
        self.assertIsNone(observed[-1].evidence[0].known_at_ns)
        verify_receipt(receipt, envelope(results), observed)

    def test_decoder_rejects_duplicate_unknown_missing_extra_and_noncanonical_payloads(self):
        original = GOLDENS['count']['ascii'].encode('ascii')
        bad = [original+b'\n', original.replace(b'{', b'{ ', 1), b'{"record":"os.system","fields":{}}',
               b'{"record":"results.FeatureResult","record":"results.FeatureResult","fields":{}}',
               original.replace(b'"int":"0"', b'"int":"-0"'), original.replace(b'"int":"0"', b'"int":"01"'),
               original.replace(b'"int":"0"', b'"int":"+0"'), original.replace(b'"int":"0"', b'0'),
               original.replace(b'"unit":"count"', b'"unit":"count","extra":null'),
               original.replace(b'"unit":"count",', b''), original.replace(b'"unit":"count"', b'"unit":"\\ud800"')]
        for data in bad:
            self.reject(SinkErrorCode.INVALID_CONTENT, lambda: decode_result(data))

    def test_nonfinite_noncanonical_float_and_forged_records_rejected(self):
        result = synthetic_results()[4]; data = encode_result(result)
        for text in ('nan', 'inf', '0X0.0P+0', '-0x0p+0'):
            self.reject(SinkErrorCode.INVALID_CONTENT, lambda: decode_result(data.replace(b'-0x0.0p+0', text.encode())))
        for value in (float('nan'), float('inf'), lambda: None, object()):
            self.reject(SinkErrorCode.INVALID_CONTENT, lambda: to_wire(value))
        forged = dataclasses.replace(golden_result('count'))
        object.__setattr__(forged, 'quality', ())
        self.reject(SinkErrorCode.INVALID_CONTENT, lambda: encode_result(forged))

    def test_wire_envelope_receipt_exact_fields_and_key_rejection(self):
        results = (golden_result('count'),); e = envelope(results); receipt = publish(MemorySink(), e, results)
        self.assertEqual(decode_envelope(encode_envelope(e)), e)
        self.assertEqual(decode_receipt(encode_receipt(receipt)), receipt)
        self.reject(SinkErrorCode.INVALID_CONTENT, lambda: decode_envelope(encode_envelope(e)+b'\n'))
        self.reject(SinkErrorCode.INVALID_CONTENT, lambda: decode_receipt(encode_receipt(dataclasses.replace(receipt, idempotency_key='0'*64))))

    def test_wire_versions_rejected_before_current_schema_decoding_even_valid_key(self):
        results=(golden_result('count'),);e=envelope(results);receipt=publish(MemorySink(),e,results)
        for field in ('protocol_version','codec_version','identity_version','digest_version','canonical_package_version','canonical_schema_version','math_policy_version'):
            wire=json.loads(encode_envelope(e));wire[field]='future2'
            data=json.dumps(wire,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
            self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:decode_envelope(data))
            wire=json.loads(encode_receipt(receipt));wire['identity'][field]='future2'
            keybytes=json.dumps(wire['identity'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
            wire['idempotency_key']=hashlib.sha256(b'efio-key1\0'+keybytes).hexdigest()
            data=json.dumps(wire,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
            self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:decode_receipt(data))
            self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:encode_envelope(dataclasses.replace(e,**{field:'future2'})))
        wire=json.loads(encode_envelope(e));wire['result_descriptors'][0]['metadata']['fields']['schema_version']='2'
        self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:decode_envelope(json.dumps(wire,sort_keys=True,separators=(',',':')).encode('ascii')))

    def test_non_limit_guarantees_are_never_dropped_before_begin(self):
        results=(golden_result('count'),);e=envelope(results);sink=MemorySink()
        for changes in (dict(visibility='manifest_last'),dict(writer_mode='serialized_writer'),dict(reservation_retention_ns=1000),dict(visibility='manifest_last',writer_mode='serialized_writer',reservation_retention_ns=1000)):
            requested=dataclasses.replace(LIMITS,**changes)
            self.reject(SinkErrorCode.UNSUPPORTED_CAPABILITY,lambda:prepare_publication(results,destination_scope='dest',generation_id='gen',job_id='job',partition_id='partition',limits=requested))
            self.reject(SinkErrorCode.UNSUPPORTED_CAPABILITY,lambda:publish(sink,e,results,requirements=requested))
            self.assertEqual(sink.lookup(idempotency_key(e.identity)).state,PublicationState.ABSENT)
        requested=dataclasses.replace(LIMITS,visibility='transactional',writer_mode='single_writer')
        self.assertEqual(publish(sink,e,results,requirements=requested),sink.lookup(idempotency_key(e.identity)).receipt)
        fresh=MemorySink()
        self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:publish(fresh,e,results,requirements=dataclasses.replace(LIMITS,codec_version='future2')))
        self.reject(SinkErrorCode.RESOURCE_LIMIT,lambda:publish(fresh,e,results,requirements=dataclasses.replace(LIMITS,max_chunk_bytes=1)))
        self.assertEqual(fresh.lookup(idempotency_key(e.identity)).state,PublicationState.ABSENT)

    def test_declared_staging_restart_policy_requires_exclusive_new_handle(self):
        class Restarting(MemorySink):
            def begin(self,envelope):
                try:
                    return super().begin(envelope)
                except SinkError as error:
                    if error.code is not SinkErrorCode.BUSY: raise
                    self.simulate_restart()
                    return super().begin(envelope)
        results=synthetic_results()
        self.assertTrue(qualify_sink(Restarting,results,LIMITS,staging_recovery='restart').passed)
        self.assertFalse(qualify_sink(Restarting,results,LIMITS,staging_recovery='busy').passed)
        self.assertFalse(qualify_sink(MemorySink,results,LIMITS,staging_recovery='restart').passed)
        class DeadHandle(Restarting):
            def begin(self,envelope):
                before=self.lookup(idempotency_key(envelope.identity)).state
                started=super().begin(envelope)
                return object() if before is PublicationState.STAGING else started
        self.assertFalse(qualify_sink(DeadHandle,results,LIMITS,staging_recovery='restart').passed)

    def test_factual_corruption_cannot_become_success_through_abort_or_lookup(self):
        class CorruptCommit(MemorySink):
            def commit(self,session):
                receipt=super().commit(session)
                self.captured=receipt
                self.corrupt(receipt.idempotency_key,0,b'corrupt')
                self.read(receipt)  # factual physical-hash corruption, not an invented transient
                return receipt
        results=(golden_result('count'),);e=envelope(results);sink=CorruptCommit()
        self.reject(SinkErrorCode.CORRUPTION,lambda:publish(sink,e,results))
        self.reject(SinkErrorCode.CORRUPTION,lambda:sink.begin(e))
        self.reject(SinkErrorCode.CORRUPTION,lambda:sink.lookup(idempotency_key(e.identity)))
        self.reject(SinkErrorCode.CORRUPTION,lambda:sink.read(sink.captured))
        class CorruptLookup(MemorySink):
            def lookup(self,key):
                raise SinkError(SinkErrorCode.CORRUPTION)
        self.reject(SinkErrorCode.CORRUPTION,lambda:publish(CorruptLookup('after_commit'),e,results))

    def test_key_operational_fields_excluded_content_change_conflicts(self):
        original = golden_result('count'); changed = dataclasses.replace(original, values=(dataclasses.replace(original.values[0], values=(1,)),))
        e, new = envelope((original,)), envelope((changed,))
        self.assertEqual(idempotency_key(e.identity), idempotency_key(new.identity))
        self.assertNotEqual(e.expected_content_sha256, new.expected_content_sha256)
        sink = MemorySink(); receipt = publish(sink, e, (original,))
        self.assertEqual(sink.begin(dataclasses.replace(e, caller_created_at_ns=999, max_results=1)), receipt)
        self.reject(SinkErrorCode.CONFLICT, lambda: sink.begin(new))
        for field in ('destination_scope', 'generation_id', 'job_id', 'partition_id'):
            self.assertNotEqual(idempotency_key(e.identity), idempotency_key(dataclasses.replace(e, **{field: 'other'}).identity))

    def test_content_evidence_mutation_and_receipt_mismatch_detected(self):
        result = synthetic_results()[-1]; e = envelope((result,)); sink = MemorySink(); receipt = publish(sink, e, (result,))
        no_evidence = dataclasses.replace(result, evidence=())
        self.assertEqual(idempotency_key(envelope((no_evidence,)).identity), receipt.idempotency_key)
        self.reject(SinkErrorCode.CONFLICT, lambda: sink.begin(envelope((no_evidence,))))
        self.reject(SinkErrorCode.CORRUPTION, lambda: verify_receipt(receipt, e, (no_evidence,)))
        for field, value in (('cell_count', 2), ('evidence_count', 0), ('content_bytes', 1), ('content_sha256', '0'*64), ('idempotency_key', '1'*64)):
            self.reject(SinkErrorCode.CORRUPTION, lambda: verify_receipt(dataclasses.replace(receipt, **{field: value}), e, (result,)))

    def test_precommit_write_fault_aborts_and_redacts(self):
        results = (golden_result('count'),); e = envelope(results)
        for fault in ('before_write', 'after_write', 'before_commit'):
            sink = MemorySink(fault)
            self.reject(SinkErrorCode.RETRYABLE_FAILURE, lambda: publish(sink, e, results))
            self.assertEqual(sink.lookup(idempotency_key(e.identity)).state, PublicationState.ABORTED)
            sink.fault = None
            verify_receipt(publish(sink, e, results), e, results)

    def test_postvisibility_response_loss_lookup_returns_original(self):
        results = (golden_result('count'),); e = envelope(results); sink = MemorySink('after_commit')
        receipt = publish(sink, e, results)
        self.assertEqual(sink.lookup(receipt.idempotency_key).receipt, receipt)
        self.assertEqual(sink.begin(e), receipt)
        self.assertEqual(receipt.caller_committed_at_ns, 10)

    def test_unknown_commit_and_lookup_never_claim_absence(self):
        results = (golden_result('count'),); e = envelope(results); sink = MemorySink('unknown_lookup')
        self.reject(SinkErrorCode.COMMIT_UNKNOWN, lambda: publish(sink, e, results))
        self.assertEqual(sink.lookup(idempotency_key(e.identity)).state, PublicationState.UNKNOWN)
        sink.fault = None
        receipt = sink.lookup(idempotency_key(e.identity)).receipt
        self.assertEqual(sink.begin(e), receipt)

    def test_partial_cancel_aborted_tombstone_retry_new_session(self):
        results = (golden_result('count'),); e = envelope(results); sink = MemorySink()
        class Cancel:
            def is_cancelled(self): return True
        self.reject(SinkErrorCode.CANCELLED, lambda: publish(sink, e, results, cancellation=Cancel()))
        self.assertEqual(sink.lookup(idempotency_key(e.identity)).state, PublicationState.ABORTED)
        self.reject(SinkErrorCode.CONFLICT, lambda: sink.begin(dataclasses.replace(e, expected_content_sha256='0'*64)))
        old = sink.begin(e); sink.write(old, 0, results[0]); sink.simulate_restart()
        self.assertEqual(sink.lookup(idempotency_key(e.identity)).state, PublicationState.ABORTED)
        new = sink.begin(e); self.assertIsNot(new, old)
        self.reject(SinkErrorCode.INVALID_SESSION, lambda: sink.write(old, 0, results[0]))

    def test_after_commit_abort_preserves_and_cannot_retract(self):
        result = golden_result('count'); e = envelope((result,)); sink = MemorySink()
        session = sink.begin(e); sink.write(session, 0, result); receipt = sink.commit(session)
        self.assertEqual(sink.abort(session), AbortOutcome(PublicationState.COMMITTED, receipt))
        self.assertEqual(sink.read(receipt), (result,))

    def test_invalid_order_foreign_session_descriptor_missing_commit(self):
        result = golden_result('count'); e = envelope((result,)); sink = MemorySink(); session = sink.begin(e)
        self.reject(SinkErrorCode.INVALID_CONTENT, lambda: sink.write(session, 1, result))
        wrong = dataclasses.replace(result, metadata=dataclasses.replace(result.metadata, backend_version='2'))
        self.reject(SinkErrorCode.INVALID_CONTENT, lambda: sink.write(session, 0, wrong))
        self.reject(SinkErrorCode.CONFLICT, lambda: sink.commit(session))
        other = MemorySink(); other.begin(e)
        self.reject(SinkErrorCode.INVALID_SESSION, lambda: other.write(session, 0, result))
        sink.write(session, 0, result)
        self.reject(SinkErrorCode.INVALID_CONTENT, lambda: sink.write(session, 0, result))

    def test_limits_exact_types_and_duplicate_results(self):
        result = golden_result('count')
        self.reject(SinkErrorCode.RESOURCE_LIMIT, lambda: prepare_publication((result,), destination_scope='d', generation_id='g', job_id='j', partition_id='p', limits=dataclasses.replace(LIMITS, max_chunk_bytes=1)))
        self.reject(SinkErrorCode.INVALID_CONTENT, lambda: envelope((result, result)))
        self.reject(SinkErrorCode.INVALID_CONFIG, lambda: dataclasses.replace(envelope((result,)), cell_count=True))
        self.reject(SinkErrorCode.RESOURCE_LIMIT, lambda: dataclasses.replace(envelope((result,)), max_result_cells=0))
        self.reject(SinkErrorCode.INVALID_CONFIG, lambda: PublicationStatus(PublicationState.COMMITTED, None))
        self.reject(SinkErrorCode.INVALID_CONFIG, lambda: AbortOutcome(PublicationState.ABSENT, None))

    def test_physical_tamper_required_artifact_hash_and_length(self):
        result = golden_result('count'); e = envelope((result,)); sink = MemorySink(); receipt = publish(sink, e, (result,))
        sink.corrupt(receipt.idempotency_key, 0, encode_result(result)+b' ')
        self.reject(SinkErrorCode.CORRUPTION, lambda: sink.read(receipt))

    def test_versions_rejected_before_reservation(self):
        result = golden_result('count'); e = envelope((result,)); sink = MemorySink()
        for field in ('protocol_version', 'codec_version', 'identity_version', 'digest_version', 'canonical_package_version', 'canonical_schema_version', 'math_policy_version'):
            wrong = dataclasses.replace(e, **{field:'future2'})
            self.reject(SinkErrorCode.INCOMPATIBLE_VERSION, lambda: sink.begin(wrong))
            self.assertEqual(sink.lookup(idempotency_key(wrong.identity)).state, PublicationState.ABSENT)
        metadata=dataclasses.replace(result.metadata,math_policy_version='future2')
        wrong=dataclasses.replace(e,result_descriptors=(ResultDescriptor(metadata,e.result_descriptors[0].features),))
        changed=dataclasses.replace(result,metadata=metadata)
        self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:verify_content(wrong,(changed,)))
        self.reject(SinkErrorCode.INCOMPATIBLE_VERSION,lambda:sink.begin(wrong))

    def test_reusable_conformance_detects_broken_reader_and_replay(self):
        results = synthetic_results()
        report = qualify_sink(MemorySink, results, LIMITS)
        self.assertEqual(len(report.cases), 21); self.assertTrue(report.passed)
        self.assertFalse(report.backend_durability_certification)
        class BrokenReader(MemorySink):
            def read(self, receipt): return ()
        self.assertFalse(qualify_sink(BrokenReader, results, LIMITS).passed)
        class BrokenReplay(MemorySink):
            def begin(self, envelope):
                started = super().begin(envelope)
                return dataclasses.replace(started, caller_committed_at_ns=99) if isinstance(started, CompletionReceipt) else started
        self.assertFalse(qualify_sink(BrokenReplay, results, LIMITS).passed)

    def test_independent_public_calculation500_51200_1026_and_null_survive(self):
        from equity_feature_contracts import ConfigSpec, Parameter, SessionSpec, WindowSpec
        from equity_features.session import compute_bars
        unit=i.PriceUnit(0,'USD')
        config=ConfigSpec('synthetic-bars','v1',(Parameter('eligibility_policy','example-v1'),),SessionSpec('demo','S',100,200,'caller-supplied'),WindowSpec(1,'S',('P','S')),s.AvailabilitySpec(200,210,210),price_unit=unit)
        facts=(('instrument_id',('A','A')),('session_id',('S','S')),('start_ns',(100,150)),('end_ns',(150,200)),('known_at_ns',(150,210)),('open',(100,102)),('high',(103,104)),('low',(99,101)),('close',(102,103)),('volume',(200,300)),('actual_notional',(20300,30900)))
        batch=i.CanonicalBatch(i.DataKind.BAR,tuple(i.Column(n,v) for n,v in facts),i.BatchMetadata('demo',i.SourceBinding('synthetic','snapshot1','map1','bars1'),i.Coverage(2,2,True),unit,scope=i.InputScope(100,200,'example-v1')))
        result=compute_bars(batch,config,entity=r.EntityKey('A','S'));sink=MemorySink();receipt=publish(sink,envelope((result,)),(result,))
        observed=sink.read(receipt)[0]; values={column.feature_id:column.values[0] for column in observed.values}
        self.assertEqual(values['session.bar.volume'],500);self.assertEqual(values['session.bar.notional'],51200)
        self.assertEqual(values['session.bar.close_weighted_price'],102.6);self.assertIsNone(values['session.price.overnight_gap'])
        self.assertEqual(observed.metadata,result.metadata);self.assertEqual(observed.quality,result.quality);self.assertEqual(observed.evidence,result.evidence)


if __name__ == '__main__':
    installed = '--installed' in sys.argv
    if installed:
        sys.argv.remove('--installed')
        import equity_feature_io_contracts, equity_feature_io_sdk, equity_feature_factory_fixture
        for module in (equity_feature_io_contracts, equity_feature_io_sdk, equity_feature_factory_fixture):
            assert 'site-packages' in Path(module.__file__).resolve().parts
    report = None
    if '--report-json' in sys.argv:
        index=sys.argv.index('--report-json'); report=Path(sys.argv[index+1]);del sys.argv[index:index+2]
    outcome=unittest.main(exit=False).result
    if report is not None:
        report.write_text(json.dumps(dict(schema='publication-installed1',publication_tests=outcome.testsRun,
             installed_public_execution=installed,io_contracts=version('equity-feature-io-contracts'),
             io_sdk=version('equity-feature-io-sdk'),consumer=version('equity-feature-factory-fixture'),
             test_suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             hand_golden_sha256=hashlib.sha256(Path(__file__).with_name('publication_goldens.json').read_bytes()).hexdigest(),
             backend_durability_certification=False,private_execution=False),sort_keys=True,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if outcome.wasSuccessful() else 1)
