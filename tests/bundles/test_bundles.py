"""Independent pre-code ZIP plus hostile-container/content/replay controls."""
import base64
from dataclasses import replace
import hashlib
import io
import importlib.util
import json
import math
from pathlib import Path
import struct
import unittest
from unittest.mock import patch, Mock
import zipfile
from equity_feature_contracts import inputs as i, results as r, specs as s
from equity_feature_contracts import ContractError, ErrorCode
from equity_feature_evidence import canonical_content, make_content_receipt, fingerprint_result
from equity_feature_bundles import (
    BundleError, BundleInput, BundleVersions, BundleManifest, PublicationDeclaration,
    ReplayReport, ReproductionBundle, read_bundle, write_bundle,
)
from equity_feature_bundles import _archive as archive, _json as lexer, _typed as typed
from equity_feature_bundles import replay


FIXTURE = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/bundle_oracle.json').read_text(encoding='utf-8'))
RAW = base64.b64decode(FIXTURE['archive_base64'])
HAS_FEATURES = importlib.util.find_spec('equity_features') is not None


def members(raw=RAW):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return {x: z.read(x) for x in z.namelist()}


def standard_zip(entries, names=None, **metadata):
    """Independent stdlib packer; never uses the new writer for expected bytes."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        for name in (sorted(entries) if names is None else names):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3; info.create_version = info.extract_version = 20
            info.external_attr = 0o100600 << 16
            for key, value in metadata.items(): setattr(info, key, value)
            z.writestr(info, entries[name])
    return output.getvalue()


def exported(bundle, embedded=True):
    return write_bundle(bundle.receipt, bundle.configuration, bundle.result,
        tuple((x.role, x.batch) for x in bundle.inputs if embedded and x.batch is not None), bundle.manifest.publication)


def changed_bundle(original, *, config=None, batch=None, result=None):
    cfg = original.configuration if config is None else config
    output = original.result if result is None else result
    data = original.inputs[0].batch if batch is None else batch
    meta = replace(output.metadata, namespace=cfg.session.namespace, availability=cfg.availability,
        config_digest=cfg.digest, inputs=(r.InputBinding('trades', data.kind, data.metadata),))
    output = replace(output, metadata=meta)
    receipt = make_content_receipt(output, cfg, (('trades', data),), original.receipt.environment,
        original.receipt.execution, original.receipt.evidence)
    return read_bundle(write_bundle(receipt, cfg, output, (('trades', data),), original.manifest.publication))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.bundle = read_bundle(RAW)

    def test_independent_known_bytes_and_headers(self):
        self.assertEqual(len(RAW), 11517)
        self.assertEqual(hashlib.sha256(RAW).hexdigest(), 'a9134cadf800d5288725a9976c32866b464a27bcf25c569751e6188646d7b4ff')
        self.assertEqual(standard_zip(members()), RAW)
        self.assertEqual(exported(self.bundle), RAW)
        manifest = members()['manifest.json']
        self.assertEqual((len(manifest), hashlib.sha256(manifest).hexdigest()),
            (1336, 'a52597d5226d838a985e19f168c7ecb6484dedb6598a04fb791f7ba2f03fd119'))
        self.assertEqual(tuple(x.values[0] for x in self.bundle.result.values), (3,10,1011,101.1,10/3))

    @unittest.skipUnless(HAS_FEATURES, 'explicit replay extra required')
    def test_actual_core_export_and_replay(self):
        from equity_features.session import compute_trades
        b = self.bundle
        actual = compute_trades(b.inputs[0].batch, b.configuration, entity=b.manifest.entity)
        self.assertEqual(canonical_content(actual), canonical_content(b.result))
        receipt = make_content_receipt(actual, b.configuration, (('trades', b.inputs[0].batch),),
            b.receipt.environment, b.receipt.execution, b.receipt.evidence)
        fresh = read_bundle(write_bundle(receipt, b.configuration, actual,
            (('trades', b.inputs[0].batch),), b.manifest.publication))
        # Source development uses fixed local module; fresh installed qualification
        # separately exercises actual metadata/version checks without this patch.
        with patch.object(replay, '_installed_calculator', return_value=compute_trades):
            report = replay.replay_bundle(fresh)
        self.assertEqual(report.status, 'matched')
        self.assertEqual(report.calculation_count, 1)
        self.assertEqual(report.replayed_output, fingerprint_result(actual))
        self.assertFalse(report.declared_environment_verified)

    def test_references_unavailable_and_explicit_resolution(self):
        reference = read_bundle(exported(self.bundle, False))
        self.assertIsNone(reference.inputs[0].batch)
        with patch.object(replay, '_installed_calculator', side_effect=AssertionError('must not load')):
            self.assertEqual(replay.replay_bundle(reference).status, 'unavailable')
        if HAS_FEATURES:
            from equity_features.session import compute_trades
            with patch.object(replay, '_installed_calculator', return_value=compute_trades):
                self.assertEqual(replay.replay_bundle(reference, (('trades', self.bundle.inputs[0].batch),)).status, 'matched')
        changed = replace(self.bundle.inputs[0].batch, metadata=replace(self.bundle.inputs[0].batch.metadata,
            source=replace(self.bundle.inputs[0].batch.metadata.source, snapshot_id='different')))
        with patch.object(replay, '_installed_calculator', side_effect=AssertionError('must not load')):
            with self.assertRaises(BundleError): replay.replay_bundle(reference, (('trades', changed),))
            with self.assertRaises(BundleError): replay.replay_bundle(reference, (('other', changed),))
            with self.assertRaises(BundleError): replay.replay_bundle(self.bundle, (('trades', changed),))

    @unittest.skipUnless(HAS_FEATURES, 'explicit replay extra required')
    def test_zero_input_missing_case(self):
        from equity_features.session import compute_trades
        b = self.bundle
        output = compute_trades(None, b.configuration, entity=b.manifest.entity)
        receipt = make_content_receipt(output, b.configuration, (), b.receipt.environment, b.receipt.execution, b.receipt.evidence)
        missing = read_bundle(write_bundle(receipt, b.configuration, output, (), b.manifest.publication))
        self.assertEqual(missing.inputs, ())
        with patch.object(replay, '_installed_calculator', return_value=compute_trades):
            self.assertEqual(replay.replay_bundle(missing).status, 'matched')

    def test_no_lazy_or_mutable_arguments(self):
        class Trap:
            def __iter__(self): raise AssertionError('must not iterate')
            def __str__(self): raise AssertionError('must not format')
        for bad in ([], {}, Trap(), iter(())):
            with self.subTest(type=type(bad)):
                with self.assertRaises(BundleError): write_bundle(self.bundle.receipt, self.bundle.configuration, self.bundle.result, bad, self.bundle.manifest.publication)
                with self.assertRaises(BundleError): replay.replay_bundle(self.bundle, bad)
        for raw in (bytearray(RAW), memoryview(RAW), Trap()):
            with self.assertRaises(BundleError): read_bundle(raw)
        with self.assertRaises(BundleError): replay.replay_bundle(self.bundle, cancel_before_start=1)
        with self.assertRaises(BundleError): replace(self.bundle, inputs=list(self.bundle.inputs))

    def test_publication_versions_and_exact_types(self):
        for args in (('private','x','caller_owned'), ('synthetic','','caller_owned'), ('synthetic','x','forever'), ('synthetic','x\n','caller_owned')):
            with self.assertRaises(BundleError): PublicationDeclaration(*args)
        for name in ('bundle','contracts','features','evidence'):
            with self.assertRaises(BundleError): replace(self.bundle.manifest.versions, **{name:'unknown'})
        with self.assertRaises(BundleError): replace(self.bundle.manifest, versions={})
        class Derived(BundleManifest): pass
        derived = Derived(self.bundle.manifest.registry, self.bundle.manifest.entity, self.bundle.manifest.versions, self.bundle.manifest.publication)
        with self.assertRaises(BundleError): replace(self.bundle, manifest=derived)

    def test_all_byte_truncations(self):
        for n in range(len(RAW)):
            with self.assertRaises(BundleError): read_bundle(RAW[:n])

    def test_header_language_mutations(self):
        mutations = [(0,b'XX'), (4,struct.pack('<H',21)), (6,struct.pack('<H',1)),
            (8,struct.pack('<H',8)), (10,struct.pack('<H',1)), (12,struct.pack('<H',34)),
            (28,struct.pack('<H',1)), (len(RAW)-2,b'\x01\x00')]
        central = RAW.index(b'PK\x01\x02')
        mutations += [(central+4,struct.pack('<H',20)), (central+8,struct.pack('<H',8)),
            (central+30,struct.pack('<H',1)), (central+32,struct.pack('<H',1)),
            (central+34,struct.pack('<H',1)), (central+36,struct.pack('<H',1)),
            (central+38,struct.pack('<I',0o120777<<16)), (central+42,struct.pack('<I',1))]
        for offset, value in mutations:
            changed = RAW[:offset]+value+RAW[offset+len(value):]
            with self.subTest(offset=offset), self.assertRaises(BundleError): read_bundle(changed)
        for changed in (b'x'+RAW, RAW+b'x', RAW[:-22]+b'x'+RAW[-22:], RAW[:-22]+b'PK\x06\x06'+RAW[-22:]):
            with self.assertRaises(BundleError): read_bundle(changed)

    def test_path_aliases_missing_extra_unsorted_and_duplicate(self):
        original = members()
        for name in ('../result.json','/result.json','C:result.json','\\result.json','RESULT.json','inputs/../000.json','inputs/０００.json','x\n.json','inputs/000.json/'):
            data = dict(original); data[name] = data.pop('result.json')
            with self.subTest(name=name), self.assertRaises(BundleError): read_bundle(standard_zip(data))
        data=dict(original); data.pop('result.json')
        with self.assertRaises(BundleError): read_bundle(standard_zip(data))
        data=dict(original); data['inputs/001.json']=data['inputs/000.json']
        with self.assertRaises(BundleError): read_bundle(standard_zip(data))
        with self.assertRaises(BundleError): read_bundle(standard_zip(original, list(reversed(sorted(original)))))
        with self.assertWarns(UserWarning): duplicate=standard_zip(original, sorted(original)+['result.json'])
        with self.assertRaises(BundleError): read_bundle(duplicate)

    def test_bad_crc_hash_and_canonical_json(self):
        changed=bytearray(RAW); changed[80]^=1
        with self.assertRaises(BundleError): read_bundle(bytes(changed))
        for key in members():
            data=members(); data[key]=data[key]+b' '
            with self.subTest(entry=key), self.assertRaises(BundleError): read_bundle(standard_zip(data))
        data=members(); data['manifest.json']=data['manifest.json'].replace(b'"registry":',b'"registry":"x","registry":')
        with self.assertRaises(BundleError): read_bundle(standard_zip(data))

    def test_manifest_closed_fields_and_bindings(self):
        original=json.loads(members()['manifest.json'])
        changes=[lambda d:d.update(extra=True), lambda d:d.pop('publication'), lambda d:d.update(registry='os.system'),
            lambda d:d['versions'].update(features='9'), lambda d:d['configuration']['content'].update(digest='0'*64),
            lambda d:d['inputs'][0].update(role='other'), lambda d:d['inputs'][0].update(input_id='other'),
            lambda d:d['inputs'][0].update(storage='reference',entry=None), lambda d:d['inputs'][0].update(entry='inputs/001.json'),
            lambda d:d['receipt'].update(byte_length=True), lambda d:d['entity'].update(instrument_id='B')]
        for change in changes:
            manifest=json.loads(json.dumps(original)); change(manifest)
            data=members(); data['manifest.json']=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode('ascii')
            with self.subTest(change=change), self.assertRaises(BundleError): read_bundle(standard_zip(data))

    def test_direct_content_binding_mutations(self):
        b=self.bundle
        variants=(replace(b.configuration,identity='changed'), replace(b.configuration,price_unit=i.PriceUnit(1,'USD')))
        for config in variants:
            with self.assertRaises(BundleError): replace(b,configuration=config)
        for batch in (replace(b.inputs[0].batch,metadata=replace(b.inputs[0].batch.metadata,ordering='unsorted')),
            replace(b.inputs[0].batch,columns=tuple(replace(c,values=(2,3,6)) if c.name=='size' else c for c in b.inputs[0].batch.columns))):
            with self.assertRaises(BundleError): replace(b.inputs[0],batch=batch)
        with self.assertRaises(BundleError): replace(b,result=replace(b.result,quality=tuple(reversed(b.result.quality))))
        with self.assertRaises(BundleError): replace(b,inputs=())

    def test_semantic_request_conflicts_before_calculator(self):
        b=self.bundle
        mutations=(replace(b.configuration,price_unit=i.PriceUnit(1,'USD')),
            replace(b.configuration,adjustment=i.AdjustmentSpec('split','v1','actions','anchor')),
            replace(b.configuration,parameters=(s.Parameter('eligibility_policy','other'),)))
        for config in mutations:
            changed=changed_bundle(b,config=config)
            with patch.object(replay,'_installed_calculator',side_effect=AssertionError('must not load')):
                with self.assertRaises(BundleError): replay.replay_bundle(changed)

    def test_cancel_incompatible_and_no_hidden_calls(self):
        with patch.object(replay,'_installed_calculator',side_effect=AssertionError('must not load')):
            self.assertEqual(replay.replay_bundle(self.bundle,cancel_before_start=True).status,'cancelled_before_start')
        with patch.object(replay,'_installed_calculator',return_value=None):
            report=replay.replay_bundle(self.bundle)
            self.assertEqual((report.status,report.calculation_count),('incompatible',0))

    def test_consistent_unknown_math_policy_refuses_before_calculator(self):
        b=self.bundle
        result=replace(b.result,metadata=replace(b.result.metadata,math_policy_version='v2'))
        receipt=make_content_receipt(result,b.configuration,(('trades',b.inputs[0].batch),),
            b.receipt.environment,b.receipt.execution,b.receipt.evidence)
        with self.assertRaises(BundleError) as caught:
            write_bundle(receipt,b.configuration,result,(('trades',b.inputs[0].batch),),b.manifest.publication)
        self.assertEqual(caught.exception.code,'unsupported_version')
        # Independently rebind every changed byte/hash through standard JSON/ZIP,
        # so integrity failure cannot accidentally stand in for policy admission.
        entries=members()
        wire=json.loads(entries['result.json'])
        wire['value']['fields']['metadata']['fields']['math_policy_version']='v2'
        encode=lambda x:json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('ascii')
        entries['result.json']=encode(wire)
        claim=json.loads(entries['receipt.json'])
        claim['metadata']['math_policy_version']='v2'
        claim['output'].update(digest=hashlib.sha256(entries['result.json']).hexdigest(),byte_length=len(entries['result.json']))
        entries['receipt.json']=encode(claim)
        manifest=json.loads(entries['manifest.json'])
        manifest['result']['content']=claim['output']
        manifest['receipt'].update(digest=hashlib.sha256(entries['receipt.json']).hexdigest(),byte_length=len(entries['receipt.json']))
        entries['manifest.json']=encode(manifest)
        with self.assertRaises(BundleError) as caught: read_bundle(standard_zip(entries))
        self.assertEqual(caught.exception.code,'unsupported_version')
        # Revalidate a caller-forged exact wrapper too; no admission flag is trusted.
        forged=object.__new__(ReproductionBundle)
        for name,value in (('manifest',b.manifest),('receipt',receipt),('configuration',b.configuration),('result',result),('inputs',b.inputs)):
            object.__setattr__(forged,name,value)
        loader=Mock(side_effect=AssertionError('must not reach calculator loader'))
        with patch.object(replay,'_installed_calculator',loader):
            with self.assertRaises(BundleError) as caught: replay.replay_bundle(forged)
        self.assertEqual(caught.exception.code,'unsupported_version')
        self.assertEqual(loader.call_count,0)

    def test_empty_zero_input_policy_refuses_before_calculator(self):
        b=self.bundle
        # A known missing-result shape is independent of a calculator call here.
        missing=replace(b.result,
            values=tuple(replace(c,values=(None,)) for c in b.result.values),
            quality=tuple(replace(q,status=r.Status.MISSING_INPUT,expected=None,observed=0,reasons=(r.Reason.ABSENT_INPUT,)) for q in b.result.quality),
            metadata=replace(b.result.metadata,inputs=()))
        baseline=make_content_receipt(missing,b.configuration,(),b.receipt.environment,b.receipt.execution,b.receipt.evidence)
        good=read_bundle(write_bundle(baseline,b.configuration,missing,(),b.manifest.publication))
        from equity_feature_evidence import encode_receipt
        for policy in ('','   ','\t\n'):
            config=replace(b.configuration,parameters=(s.Parameter('eligibility_policy',policy),))
            output=replace(missing,metadata=replace(missing.metadata,config_digest=config.digest))
            receipt=make_content_receipt(output,config,(),b.receipt.environment,b.receipt.execution,b.receipt.evidence)
            with self.assertRaises(BundleError) as caught:
                write_bundle(receipt,config,output,(),b.manifest.publication)
            self.assertEqual(caught.exception.code,'unsupported_version')
            # Accepted foundation encoders + independent standard JSON/ZIP rebind
            # every changed descriptor; no new writer creates its own negative.
            entries=members(exported(good)); entries['configuration.json']=canonical_content(config)
            entries['result.json']=canonical_content(output); entries['receipt.json']=encode_receipt(receipt)
            claim=json.loads(entries['receipt.json']); manifest=json.loads(entries['manifest.json'])
            manifest['configuration']['content']=claim['configuration']; manifest['result']['content']=claim['output']
            manifest['receipt'].update(digest=hashlib.sha256(entries['receipt.json']).hexdigest(),byte_length=len(entries['receipt.json']))
            entries['manifest.json']=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode('ascii')
            with self.assertRaises(BundleError) as caught: read_bundle(standard_zip(entries))
            self.assertEqual(caught.exception.code,'unsupported_version')
            forged=object.__new__(ReproductionBundle)
            for name,value in (('manifest',b.manifest),('receipt',receipt),('configuration',config),('result',output),('inputs',())):
                object.__setattr__(forged,name,value)
            loader=Mock(side_effect=AssertionError('invalid request must not load calculator'))
            with patch.object(replay,'_installed_calculator',loader):
                with self.assertRaises(BundleError) as caught: replay.replay_bundle(forged)
            self.assertEqual(caught.exception.code,'unsupported_version'); self.assertEqual(loader.call_count,0)

    def test_controlled_one_call_outcomes_and_gate(self):
        b=self.bundle
        changed=replace(b.result,values=(replace(b.result.values[0],values=(4,)),)+b.result.values[1:])
        cases=[([0,5000000000],b.result,'matched',1),([0,5000000001],b.result,'budget_exceeded_after_return',1),
            ([True],b.result,'control_failed_before_start',0),([0,False],b.result,'control_failed_after_return',1),
            ([2,1],b.result,'control_failed_after_return',1),([0,1],changed,'mismatch',1),([0,1],None,'result_rejected',1)]
        for times,output,status,count in cases:
            function=Mock(return_value=output)
            with patch.object(replay,'_installed_calculator',return_value=function),patch.object(replay,'_now',side_effect=times):
                report=replay.replay_bundle(b)
            self.assertEqual((report.status,report.calculation_count,function.call_count),(status,count,count))
        function=Mock(side_effect=ContractError(ErrorCode.INVALID_CONFIG,'private sentinel'))
        with patch.object(replay,'_installed_calculator',return_value=function),patch.object(replay,'_now',return_value=0):
            report=replay.replay_bundle(b)
        self.assertEqual((report.status,function.call_count),('calculation_rejected',1))
        for error in (RuntimeError('private'),KeyboardInterrupt()):
            with patch.object(replay,'_installed_calculator',return_value=Mock(side_effect=error)),patch.object(replay,'_now',return_value=0):
                with self.assertRaises(type(error)): replay.replay_bundle(b)

    def test_work_bounds_before_calculator(self):
        b=self.bundle
        # Registry admits one trades input, while generic parser member/ref caps
        # are defense in depth; these are semantic replay-stage boundary probes.
        config=replace(b.configuration,window=replace(b.configuration.window,governed_sessions=tuple(str(n) for n in range(257))+('S',)))
        changed=changed_bundle(b,config=config)
        with patch.object(replay,'_installed_calculator',side_effect=AssertionError('must not load')):
            with self.assertRaises(BundleError) as caught: replay.replay_bundle(changed)
        self.assertEqual(caught.exception.code,'limit_exceeded')

    def test_row_and_interval_replay_boundaries(self):
        b=self.bundle
        for count in (10000,10001):
            columns=[]
            for column in b.inputs[0].batch.columns:
                values=tuple(range(count)) if column.name=='order_key' else tuple('t'+str(n) for n in range(count)) if column.name=='event_id' else (column.values[0],)*count
                columns.append(replace(column,values=values))
            batch=replace(b.inputs[0].batch,columns=tuple(columns),metadata=replace(b.inputs[0].batch.metadata,coverage=i.Coverage(count,count,True)))
            changed=changed_bundle(b,batch=batch)
            function=Mock(return_value=changed.result)
            with patch.object(replay,'_installed_calculator',return_value=function),patch.object(replay,'_now',side_effect=[0,1]):
                if count==10000:
                    self.assertEqual(replay.replay_bundle(changed).calculation_count,1)
                    self.assertEqual(function.call_count,1)
                else:
                    with self.assertRaises(BundleError): replay.replay_bundle(changed)
                    self.assertEqual(function.call_count,0)
        for count in (64,65):
            config=replace(b.configuration,session=replace(b.configuration.session,
                intervals=tuple(s.IntervalSpec(str(n),100+n,101+n) for n in range(count))))
            changed=changed_bundle(b,config=config)
            function=Mock(return_value=changed.result)
            with patch.object(replay,'_installed_calculator',return_value=function),patch.object(replay,'_now',side_effect=[0,1]):
                if count==64:
                    self.assertEqual(replay.replay_bundle(changed).calculation_count,1)
                else:
                    with self.assertRaises(BundleError): replay.replay_bundle(changed)
                    self.assertEqual(function.call_count,0)

    def test_error_messages_do_not_echo_payload(self):
        secret='SYNTHETIC-PRIVATE-SENTINEL'
        data=members(); wire=json.loads(data['manifest.json']); wire['entity']['instrument_id']=secret
        data['manifest.json']=json.dumps(wire,sort_keys=True,separators=(',',':')).encode()
        with self.assertRaises(BundleError) as caught: read_bundle(standard_zip(data))
        self.assertNotIn(secret,str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)


class LexicalTests(unittest.TestCase):
    def test_integer_widths_and_conversion_order(self):
        for raw in (b'0',str(10**38-1).encode(),str(-(10**38-1)).encode()): lexer.preflight(raw,'typed')
        for raw in (b'-0',b'+1',b'01',b'1.0',b'1e1',b'NaN',b'Infinity',b'--1'):
            with self.assertRaises(BundleError): lexer.preflight(raw,'typed')
        with patch.object(lexer,'load',side_effect=AssertionError('must not parse')):
            for raw in (b'1'*39,b'-'+b'9'*39):
                with self.assertRaises(BundleError) as caught: lexer.preflight(raw,'typed')
                self.assertEqual(caught.exception.code,'limit_exceeded')
        for raw in (b'9223372036854775807',b'-9223372036854775808'): lexer.preflight(raw,'receipt')
        for raw in (b'9223372036854775808',b'-9223372036854775809'):
            with self.assertRaises(BundleError): lexer.preflight(raw,'receipt')
        lexer.preflight(b'33554432','manifest')
        for raw in (b'33554433',b'100000000',b'-1',b'1e2'):
            with self.assertRaises(BundleError): lexer.preflight(raw,'manifest')

    def test_decoded_and_raw_string_boundaries(self):
        for kind,limit in (('typed',4096),('manifest',256),('receipt',256)):
            for text in ('x'*limit,'𐀀'*limit,'é'*limit):
                raw=json.dumps(text,ensure_ascii=True).encode('ascii')
                lexer.preflight(raw,kind)
                with self.assertRaises(BundleError): lexer.preflight(json.dumps(text+'x',ensure_ascii=True).encode(),kind)
        raw=b'"'+b'\\ud800\\udc00'*4096+b'"'
        self.assertEqual(len(raw),49154); lexer.preflight(raw,'typed')
        for raw in (b'"\\ud800"',b'"\\udc00"',b'"\\udc00\\ud800"',b'"\\uZZZZ"',b'"\\x00"',b'"\n"',b'"\xff"'):
            with self.assertRaises(BundleError): lexer.preflight(raw,'typed')
        lexer.preflight(b'"\\u0000"','typed')
        with self.assertRaises(BundleError): lexer.preflight(b'"\\u0000"','manifest')

    def test_float_conversion_limits_and_exact_hex(self):
        for value in (0.0,-0.0,math.ulp(0.0),-float.fromhex('0x1.fffffffffffffp+1023'),1.0):
            text=value.hex(); self.assertEqual(typed._float(text).hex(),text)
        for text in ('nan','inf','1.0','0x1.0p+0','0x1.0000000000000p+00','0x1.0000000000000p+1024','0x0.0000000000000p-1022'):
            with self.assertRaises(BundleError): typed._float(text)
        with self.assertRaises(BundleError) as caught: typed._float('x'*25)
        self.assertEqual(caught.exception.code,'limit_exceeded')

    def test_depth_nodes_array_and_shared_preparse_budget(self):
        lexer.preflight(b'['*24+b'0'+b']'*24,'typed')
        with self.assertRaises(BundleError): lexer.preflight(b'['*25+b'0'+b']'*25,'typed')
        lexer.preflight(b'['+b'0,'*99999+b'0]','typed')
        with self.assertRaises(BundleError): lexer.preflight(b'['+b'0,'*100000+b'0]','typed')
        budget=lexer.Budget(7,4)
        lexer.preflight(b'[0]','typed',budget)
        lexer.preflight(b'[1]','typed',budget)
        self.assertEqual((budget.size,budget.nodes),(6,4))
        with self.assertRaises(BundleError): lexer.preflight(b'0','typed',budget)
        for kind,depth,count in (('manifest',8,64),('receipt',16,256)):
            lexer.preflight(b'['*depth+b'0'+b']'*depth,kind)
            with self.assertRaises(BundleError): lexer.preflight(b'['*(depth+1)+b'0'+b']'*(depth+1),kind)
            lexer.preflight(b'['+b'0,'*(count-1)+b'0]',kind)
            with self.assertRaises(BundleError): lexer.preflight(b'['+b'0,'*count+b'0]',kind)

    def test_duplicates_and_closed_typed_tags(self):
        with self.assertRaises(BundleError): lexer.load(b'{"x":1,"x":2}')
        for value in ({'type':'os.system','fields':{}},{'float64':'nan'},{'type':'results.EntityKey','fields':{'instrument_id':'A'}}):
            with self.assertRaises(BundleError): typed.decode(value)

    def test_literal_byte_and_node_caps_preflight_stage(self):
        # These intentionally probe generic lexical ceilings, not an accepted
        # fixed-registry request. The registry separately limits input shape.
        for kind,maximum in (('manifest',65536),('receipt',1048576),('typed',33554432)):
            lexer.preflight(b'0'+b' '*(maximum-1),kind)
            with self.assertRaises(BundleError): lexer.preflight(b'0'+b' '*maximum,kind)
        for kind,maximum in (('manifest',8192),('receipt',32768)):
            # root+2nodes/pair, with one array wrapper adding the final node.
            obj={str(n):0 for n in range((maximum-4)//2)}
            obj['array']=[0]
            raw=json.dumps(obj,separators=(',',':')).encode()
            lexer.preflight(raw,kind)
            obj['array']=[0,0]
            with self.assertRaises(BundleError): lexer.preflight(json.dumps(obj,separators=(',',':')).encode(),kind)
        row=b'['+b'0,'*99998+b'0]'
        shorter=b'['+b'0,'*99997+b'0]'
        lexer.preflight(b'['+b','.join([row]*9+[shorter])+b']','typed')
        with self.assertRaises(BundleError): lexer.preflight(b'['+b','.join([row]*10)+b']','typed')

    def test_all_data_kinds_and_structured_result_types_decode(self):
        b=read_bundle(RAW)
        for kind in i.DataKind:
            columns=[]
            for field in i.schema_for(kind).fields:
                if field.required:
                    value='A' if field.dtype is i.DType.STRING else True if field.dtype is i.DType.BOOL else 1
                    columns.append(i.Column(field.name,(value,)))
            batch=i.CanonicalBatch(kind,tuple(columns),replace(b.inputs[0].batch.metadata,
                coverage=i.Coverage(1,1,True),scope=None,sampling='continuous' if kind is i.DataKind.QUOTE else 'none'))
            raw=canonical_content(batch); lexer.preflight(raw,'typed')
            self.assertEqual(canonical_content(typed.typed_content(raw,'canonical_batch')),raw)
        entity=r.EntityKey('A','S'); quality=r.QualityRow(entity,'fixture.scalar',r.Status.AVAILABLE,1,1)
        interval=s.IntervalSpec('regular',0,10)
        samples=(1,10**38-1,1.0,'a\n',True,r.BreadthCounts(1,0,0,1),r.BreadthFraction(1,1,1),
            r.TimeWeightedSpread(r.QuoteDurations(1,0,0,0,0,0),1.0,1.0,1,'seed'),r.QuoteStateCounts(1,0,0,0),
            r.SampledSpread('continuous',1,1,1.0,1.0,1,(r.QuoteObservation('input','event',0,0,0,1,2,'normal',1.0,1.0),)),
            r.TopKTrades(1,(r.TopKTradeRow('input','event',0,0,0,1,1),)),
            r.IntervalOHLCV((r.IntervalOHLCVRow(interval,1.0,1.0,1.0,1.0,1,quality),)),
            r.IntervalVolumeShares((r.IntervalVolumeShareRow(interval,1.0,quality),)))
        for dtype,sample in zip(r.ValueType,samples,strict=True):
            meta=r.ResultMetadata('fixture','S',s.AvailabilitySpec(0,0,0),'0'*64,(),'fixture','v1')
            evidence=()
            if dtype in (r.ValueType.TIME_WEIGHTED_SPREAD,r.ValueType.QUOTE_STATE_COUNTS,r.ValueType.SAMPLED_SPREAD,r.ValueType.TOP_K_TRADES):
                quote=dtype is not r.ValueType.TOP_K_TRADES
                bm=replace(b.inputs[0].batch.metadata,namespace='fixture',source=i.SourceBinding('synthetic','snapshot','v1','input'),
                    coverage=i.Coverage(1,1,True),sampling='continuous' if quote else 'none',scope=i.InputScope(0,1,'fixture'))
                meta=replace(meta,availability=s.AvailabilitySpec(1,1,1),
                    inputs=(r.InputBinding('quotes' if quote else 'trades',i.DataKind.QUOTE if quote else i.DataKind.TRADE,bm),),evidence_limit=1)
                if dtype in (r.ValueType.SAMPLED_SPREAD,r.ValueType.TOP_K_TRADES):
                    evidence=(r.EvidenceRow(entity,'fixture.scalar','input','event',0,0),)
            value=r.FeatureResult((r.FeatureColumn('fixture.scalar','v1',dtype,'ratio',(entity,),(sample,)),),(quality,),meta,evidence)
            raw=canonical_content(value); lexer.preflight(raw,'typed')
            self.assertEqual(canonical_content(typed.typed_content(raw,'feature_result')),raw)

    def test_typed_roundtrip_distinctions(self):
        cfg=read_bundle(RAW).configuration
        for value in (None,True,1,1.0,0.0,-0.0,10**38-1,-10**38+1,'','é','e\u0301','a\n',math.ulp(0.0)):
            obj=replace(cfg,parameters=(s.Parameter('payload',value),))
            raw=canonical_content(obj); lexer.preflight(raw,'typed')
            self.assertEqual(canonical_content(typed.typed_content(raw,'configuration')),raw)


class ReportTests(unittest.TestCase):
    def test_complete_matrix_and_independent_direct_constructor_negatives(self):
        b=read_bundle(RAW); output=fingerprint_result(b.result)
        rows=[('cancelled_before_start','not_started','not_checked','not_checked',None,None,0,None,False),
            ('unavailable','not_started','unavailable','not_checked',None,None,0,None,False),
            ('incompatible','not_started','verified','incompatible',None,None,0,None,False),
            ('control_failed_before_start','not_started','verified','verified',None,None,0,None,False),
            ('control_failed_after_return','returned','verified','verified',None,None,1,None,False),
            ('calculation_rejected','raised','verified','verified',None,None,1,None,False),
            ('budget_exceeded_after_return','returned','verified','verified',None,5000000001,1,None,False),
            ('result_rejected','returned','verified','verified',None,0,1,None,False),
            ('mismatch','returned','verified','verified',False,5000000000,1,output,False),
            ('matched','returned','verified','verified',True,0,1,output,False)]
        for row in rows:
            valid=ReplayReport(*row)
            for field,value in (('execution_state','bad'),('content_state','bad'),('compatibility_state','bad'),
                ('calculation_count',True),('elapsed_ns',True),('declared_environment_verified',True)):
                with self.subTest(status=row[0],field=field),self.assertRaises(BundleError): replace(valid,**{field:value})
            with self.assertRaises(BundleError): replace(valid,calculation_count=1-valid.calculation_count)
            with self.assertRaises(BundleError): replace(valid,result_match=None if valid.result_match is not None else True)
            with self.assertRaises(BundleError): replace(valid,replayed_output=None if valid.replayed_output is not None else output)


if __name__ == '__main__': unittest.main()
