"""Owned wire fixtures and independent literal timing/price/budget adversaries."""
from dataclasses import replace
import io
import http.client
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

import databento_dbn as d
from equity_feature_acquisition import AcquisitionLimits, AttemptBudget, AttemptFailure, DownloadApproval, Page
from equity_feature_contracts import AvailabilitySpec, Coverage, DataKind, InputScope, PriceUnit, SourceBinding
from equity_feature_contracts.adapters import AcquisitionRequest, SourceError, SourceErrorCode, validate_delivery
from equity_feature_databento import (DatabentoFactory, DatabentoHistoricalAdapter, DatabentoProfile,
                                     DownloadPolicy, HTTPSDatabentoTransport, InstrumentBinding)
from equity_feature_io_contracts import FactoryError
from equity_feature_io_sdk.factories import SourceRegistry

BASE = 1700000000000000000
GOLD = json.loads((Path(__file__).resolve().parents[1]/'databento_oracle.json').read_text(encoding='utf-8'))


def encoded(schema='trades', *, records=None, **meta_changes):
    kwargs = dict(dataset='XNAS.ITCH', start=BASE, end=BASE+10 if schema=='trades' else BASE+60_000_000_000,
                  stype_in=d.SType.INSTRUMENT_ID, stype_out=d.SType.INSTRUMENT_ID,
                  schema=d.Schema.TRADES if schema=='trades' else d.Schema.OHLCV_1M,
                  symbols=['1'], version=3)
    kwargs.update(meta_changes)
    meta = d.Metadata(**kwargs)
    if records is None:
        if schema=='trades':
            records = [d.TradeMsg(1,1,GOLD['event_ns'][i],GOLD['price'][i],GOLD['size'][i],
                d.Action.TRADE,d.Side.BID,0,GOLD['capture_ns'][i],sequence=GOLD['sequence'][i]) for i in range(3)]
        else:
            b=GOLD['bar']
            records=[d.OHLCVMsg(d.RType.OHLCV_1M,1,1,BASE,b['open'],b['high'],b['low'],b['close'],b['volume'])]
    return bytes(meta)+b''.join(bytes(r) for r in records)


class Credentials:
    def __init__(self): self.names=[]
    def get(self,name): self.names.append(name); return 'private-sentinel'


class Cancel:
    value=False
    def is_cancelled(self): return self.value


class Databento(unittest.TestCase):
    def setUp(self):
        self.credentials=Credentials(); self.cancel=Cancel(); self.clock=10; self.calls=[]

    def profile(self,schema='trades',**changes):
        return replace(DatabentoProfile('XNAS.ITCH',schema,'owned-fixture',
            SourceBinding('owned-databento','owned-snapshot','owned-mapping','owned-input'),
            PriceUnit(9,'USD'),InputScope(BASE,BASE+10 if schema=='trades' else BASE+60_000_000_000,'owned-scope'),
            BASE,BASE+10 if schema=='trades' else BASE+60_000_000_000,
            (InstrumentBinding(1,1,'A','S',True),)),**changes)

    def request(self,schema='trades',**changes):
        end=BASE+10 if schema=='trades' else BASE+60_000_000_000
        return replace(AcquisitionRequest('owned-request',DataKind.TRADE if schema=='trades' else DataKind.BAR,
            'owned-fixture',('A',),('S',),BASE,end,'owned-snapshot',PriceUnit(9,'USD'),
            AvailabilitySpec(end,end,end),max_batch_rows=3,
            selection='event_half_open' if schema=='trades' else 'completed_intervals'),**changes)

    def approve(self,scope):
        return DownloadApproval(scope,'owned-synthetic-only',1000000,
            AcquisitionLimits(1,min(10,scope.request.max_rows),524288,1000000,0))

    def adapter(self,schema='trades',*,raw=None,profile=None,**kwargs):
        raw=encoded(schema) if raw is None else raw
        def transport(parameters,credential,budget,check):
            self.calls.append((parameters,credential,budget)); check()
            return Page(raw,max(0,(len(raw)-8-int.from_bytes(raw[4:8],'little'))//(48 if schema=='trades' else 56)))
        return DatabentoHistoricalAdapter(profile or self.profile(schema),
            approve=kwargs.pop('approve',self.approve),credentials=self.credentials,
            clock_ns=lambda:self.clock,cost_upper_micro_usd=kwargs.pop('cost_upper_micro_usd',0),
            transport=kwargs.pop('transport',transport),**kwargs)

    def deliver(self,adapter,request=None):
        request=request or self.request()
        result=tuple(adapter.iter_batches(request,self.cancel))
        validate_delivery(request,adapter.capabilities(),result)
        return result

    def error(self,code,callback):
        with self.assertRaises(SourceError) as caught: callback()
        error=caught.exception
        self.assertEqual(error.code,code)
        self.assertNotIn('private-sentinel',str(error))
        self.assertIsNone(error.__context__); self.assertIsNone(error.__cause__)

    def test_exact_trade_cells_and_unknown_coverage(self):
        result=self.deliver(self.adapter()); b=result[0].batch
        for name,oracle in (('event_ns','event_ns'),('order_key','sequence'),('price','price'),('size','size')):
            self.assertEqual(b.column(name).values,tuple(GOLD[oracle]))
        self.assertEqual(b.column('known_at_ns').values,(None,None,None))
        self.assertEqual(b.column('eligible').values,(True,True,True))
        self.assertEqual(result[0].source_coverage,Coverage(None,3,False))
        self.assertEqual(b.column('event_id').values,tuple(f'databento:1:1:{n}:{s}' for n,s in zip(GOLD['event_ns'],GOLD['sequence'])))
        p=self.calls[0][0]
        self.assertEqual(dict(p),dict(dataset='XNAS.ITCH',schema='trades',symbols='1',stype_in='instrument_id',
            stype_out='instrument_id',encoding='dbn',compression='none',start=str(BASE),end=str(BASE+10),limit='10'))
        self.assertEqual(self.credentials.names,['DATABENTO_API_KEY'])

    def test_exact_bar_cells_and_no_fabricated_notional(self):
        b=self.deliver(self.adapter('ohlcv-1m'),self.request('ohlcv-1m'))[0].batch
        for name,value in GOLD['bar'].items(): self.assertEqual(b.column(name).values,(value,))
        self.assertEqual(b.column('start_ns').values,(BASE,))
        self.assertEqual(b.column('end_ns').values,(BASE+60_000_000_000,))

    def test_capture_and_event_ranges_are_distinct(self):
        p=self.profile(event_scope=InputScope(BASE+2,BASE+5,'owned-scope'))
        result=self.deliver(self.adapter(profile=p),self.request(start_ns=BASE+2,end_ns=BASE+5))
        self.assertEqual(result[0].batch.column('event_ns').values,(BASE+3,))
        self.assertEqual(self.calls[0][0]['start'],str(BASE))
        self.assertEqual(result[0].source_coverage,Coverage(None,1,False))

    def test_original_known_times_and_chunk_identity(self):
        p=self.profile(known_at_ns=(BASE+1,None,BASE+999))
        result=self.deliver(self.adapter(profile=p),self.request(max_batch_rows=2))
        self.assertEqual([r.batch.row_count for r in result],[2,1])
        self.assertEqual([r.final for r in result],[False,True])
        self.assertEqual(result[0].batch.column('known_at_ns').values,(BASE+1,None))
        self.assertEqual(result[1].batch.column('known_at_ns').values,(BASE+999,))
        self.assertNotEqual(result[0].source.input_id,result[1].source.input_id)
        self.assertEqual([r.source_coverage.observed for r in result],[3,3])

    def test_complete_coverage_requires_policy_and_exact_count(self):
        self.error(SourceErrorCode.SCHEMA,lambda:self.profile(coverage=Coverage(3,3,True)))
        p=self.profile(coverage=Coverage(3,3,True),coverage_policy='owned-independent-event-population')
        self.assertEqual(self.deliver(self.adapter(profile=p))[0].source_coverage,Coverage(3,3,True))
        p=replace(p,coverage=Coverage(4,4,True))
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(profile=p)))

    def test_no_approval_or_unknown_or_paid_cost_precedes_credentials(self):
        for kwargs,code in (({'approve':lambda _:None},SourceErrorCode.ENTITLEMENT),
                            ({'cost_upper_micro_usd':None},SourceErrorCode.ENTITLEMENT),
                            ({'cost_upper_micro_usd':1},SourceErrorCode.LIMIT)):
            with self.subTest(kwargs=kwargs):
                self.error(code,lambda:self.deliver(self.adapter(**kwargs)))
        self.assertEqual(self.credentials.names,[]); self.assertEqual(self.calls,[])

    def test_scope_mismatch_and_expiry_precede_credentials(self):
        def mismatch(scope): return replace(self.approve(scope),scope=replace(scope,dataset='OTHER.DATA'))
        self.error(SourceErrorCode.ENTITLEMENT,lambda:self.deliver(self.adapter(approve=mismatch)))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(approve=lambda s:replace(self.approve(s),expires_ns=10))))
        self.assertEqual(self.credentials.names,[])

    def test_policy_expiry_during_approval_precedes_credentials(self):
        def delayed(scope):
            self.clock=31
            return self.approve(scope)
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(
            approve=delayed,policy=DownloadPolicy(max_elapsed_ns=20))))
        self.assertEqual(self.credentials.names,[]); self.assertEqual(self.calls,[])
        self.clock=10
        def slow_get(name):
            self.clock=31
            self.credentials.names.append(name)
            return 'private-sentinel'
        with patch.object(self.credentials,'get',side_effect=slow_get):
            self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=DownloadPolicy(max_elapsed_ns=20))))
        self.assertEqual(self.calls,[])

    def test_cancel_and_invalid_request_precede_credentials(self):
        self.cancel.value=True
        self.error(SourceErrorCode.CANCELLED,lambda:self.deliver(self.adapter()))
        self.cancel.value=False
        for change in ({'instruments':('OTHER',)},{'sessions':('OTHER',)},{'start_ns':BASE+1}):
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter(),self.request(**change)))
        self.assertEqual(self.credentials.names,[])

    def test_sensitive_dependency_failures_are_opaque(self):
        def bad(*args): raise RuntimeError('private-sentinel')
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(approve=bad)))
        self.error(SourceErrorCode.TRANSPORT,lambda:self.deliver(self.adapter(transport=bad)))
        with patch.object(self.credentials,'get',side_effect=RuntimeError('private-sentinel')):
            self.error(SourceErrorCode.AUTHENTICATION,lambda:self.deliver(self.adapter()))

    def test_record_cap_rejects_possible_truncation(self):
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=DownloadPolicy(max_rows=3))))

    def test_bytes_metadata_and_batches_limits(self):
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(
            approve=lambda s:replace(self.approve(s),limits=AcquisitionLimits(1,10,10,1000000)))))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=DownloadPolicy(max_metadata_bytes=8))))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(),self.request(max_batch_rows=1,max_batches=2)))

    def test_bad_metadata_and_compression_rejected(self):
        for changes,code in (({'dataset':'OTHER.DATA'},SourceErrorCode.UNSUPPORTED),
            ({'version':2},SourceErrorCode.UNSUPPORTED),({'ts_out':True},SourceErrorCode.UNSUPPORTED),
            ({'partial':['1']},SourceErrorCode.UNAVAILABLE),({'not_found':['1']},SourceErrorCode.UNAVAILABLE),
            ({'end':BASE+11},SourceErrorCode.UNSUPPORTED)):
            with self.subTest(changes=changes):
                self.error(code,lambda:self.deliver(self.adapter(raw=encoded(**changes))))
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter(raw=b'compressed-private-sentinel')))

    def test_bad_capture_mapping_and_order_reject_before_prefix(self):
        raw_records=[d.TradeMsg(1,1,GOLD['event_ns'][i],GOLD['price'][i],GOLD['size'][i],
            d.Action.TRADE,d.Side.BID,0,GOLD['capture_ns'][i],sequence=GOLD['sequence'][i]) for i in range(3)]
        for records in (raw_records[::-1],raw_records[:1]*2):
            iterator=self.adapter(raw=encoded(records=records)).iter_batches(self.request(max_batch_rows=1),self.cancel)
            self.error(SourceErrorCode.SCHEMA,lambda:next(iterator))
        for record in (d.TradeMsg(1,2,BASE+1,100000000000,2,d.Action.TRADE,d.Side.BID,0,BASE+2,sequence=7),
            d.TradeMsg(1,1,BASE+1,100000000000,2,d.Action.TRADE,d.Side.BID,0,BASE+10,sequence=7),
            d.TradeMsg(1,1,BASE+1,9223372036854775807,2,d.Action.TRADE,d.Side.BID,0,BASE+2,sequence=7)):
            self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(raw=encoded(records=[record]))))

    def test_wrong_bar_duration_is_unsupported(self):
        record=d.OHLCVMsg(d.RType.OHLCV_1S,1,1,BASE,100000000000,102000000000,99000000000,101000000000,10)
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter('ohlcv-1m',raw=encoded('ohlcv-1m',records=[record])),self.request('ohlcv-1m')))

    def test_filtered_out_invalid_received_record_rejected(self):
        records=[d.TradeMsg(1,1,BASE+1,-1,2,d.Action.TRADE,d.Side.BID,0,BASE+2,sequence=7),
                 d.TradeMsg(1,1,BASE+3,102000000000,3,d.Action.TRADE,d.Side.BID,0,BASE+4,sequence=8)]
        p=self.profile(event_scope=InputScope(BASE+2,BASE+5,'owned-scope'))
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(profile=p,raw=encoded(records=records)),
                                                            self.request(start_ns=BASE+2,end_ns=BASE+5)))

    def test_empty_source_stays_unknown(self):
        result=self.deliver(self.adapter(raw=encoded(records=[])))
        self.assertEqual(len(result),1); self.assertEqual(result[0].batch.row_count,0)
        self.assertEqual(result[0].source_coverage,Coverage(None,0,False))

    def test_single_use_denied_successful_and_concurrent(self):
        a=self.adapter(); iterator=a.iter_batches(self.request(max_batch_rows=1),self.cancel)
        next(iterator)
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(a)); iterator.close()
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(a))
        a=self.adapter(approve=lambda _:None)
        self.error(SourceErrorCode.ENTITLEMENT,lambda:self.deliver(a))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(a))

    def test_factory_is_explicit_and_identity_bound(self):
        p=self.profile(); f=DatabentoFactory(p,approve=self.approve,clock_ns=lambda:self.clock)
        self.assertEqual(dict(f.validate_config({'profile_id':p.fingerprint})),{'profile_id':p.fingerprint})
        for config in ({},{'profile_id':'wrong'},{'profile_id':p.fingerprint,'credential':'private-sentinel'}):
            with self.assertRaises(FactoryError): f.validate_config(config)
        registry=SourceRegistry(); registry.register('owned-databento',f)
        a=registry.resolve('owned-databento',{'profile_id':p.fingerprint},self.credentials,self.request())
        self.assertEqual(a.capabilities().kinds,(DataKind.TRADE,))
        self.assertEqual(self.credentials.names,[])


class Response:
    def __init__(self,data,status=200,headers=None):
        self.stream=io.BytesIO(data); self.status=status; self.headers=headers or {}; self.reads=[]
    def getheader(self,name,default=None): return self.headers.get(name,default)
    def read(self,n): self.reads.append(n); return self.stream.read(n)


class Connection:
    sock=None
    def __init__(self,response): self.response=response; self.requests=[]; self.closed=False
    def request(self,*args): self.requests.append(args)
    def connect(self): pass
    def getresponse(self): return self.response
    def close(self): self.closed=True


class HTTPS(unittest.TestCase):
    def call(self,response,*,budget=None,check=lambda:None):
        connection=Connection(response)
        with patch('equity_feature_databento.transport.http.client.HTTPSConnection',return_value=connection) as constructor:
            page=HTTPSDatabentoTransport(DownloadPolicy(),lambda:10)(
                {'schema':'trades','symbols':'1','compression':'none'},'private-sentinel',
                budget or AttemptBudget(1,1000000,10,524288),check)
        return page,connection,constructor

    def test_fixed_host_post_shape_and_bounded_reads(self):
        response=Response(encoded(),headers={'Content-Length':str(len(encoded()))})
        page,connection,constructor=self.call(response)
        self.assertEqual(page.row_count,3); self.assertTrue(connection.closed)
        self.assertEqual(constructor.call_args.args,('hist.databento.com',))
        args=connection.requests[0]
        self.assertEqual(args[:2],('POST','/v0/timeseries.get_range'))
        self.assertEqual(parse_qs(args[2].decode())['symbols'],['1'])
        self.assertEqual(args[3]['Accept-Encoding'],'identity')
        self.assertLessEqual(max(response.reads),16384)

    def test_statuses_never_read_body_or_follow_redirect(self):
        for status,code in ((302,SourceErrorCode.UNSUPPORTED),(401,SourceErrorCode.AUTHENTICATION),
            (403,SourceErrorCode.ENTITLEMENT),(404,SourceErrorCode.UNAVAILABLE),
            (429,SourceErrorCode.RATE_LIMIT),(500,SourceErrorCode.TRANSPORT)):
            r=Response(b'private-sentinel',status)
            with self.assertRaises(AttemptFailure) as caught: self.call(r)
            self.assertEqual(caught.exception.code,code); self.assertEqual(r.reads,[])
            self.assertIsNone(caught.exception.__context__); self.assertIsNone(caught.exception.__cause__)

    def test_oversize_declared_and_streamed_and_compression(self):
        for r,code in ((Response(encoded(),headers={'Content-Length':'524289'}),SourceErrorCode.LIMIT),
            (Response(encoded(),headers={'Content-Encoding':'gzip'}),SourceErrorCode.UNSUPPORTED),
            (Response(encoded(),headers={'Content-Length':'1'}),SourceErrorCode.SCHEMA)):
            with self.assertRaises(AttemptFailure) as caught: self.call(r)
            self.assertEqual(caught.exception.code,code)
        with self.assertRaises(AttemptFailure) as caught:
            self.call(Response(encoded()),budget=AttemptBudget(1,1000000,10,100))
        self.assertEqual(caught.exception.code,SourceErrorCode.LIMIT)
        self.assertEqual(caught.exception.received_bytes,101)

    def test_failed_read_partial_bytes_are_charged(self):
        class Partial(Response):
            def read(self,n): raise http.client.IncompleteRead(b'x'*13,20)
        with self.assertRaises(AttemptFailure) as caught: self.call(Partial(b''))
        self.assertEqual(caught.exception.received_bytes,13)
        self.assertEqual(caught.exception.code,SourceErrorCode.TRANSPORT)
        self.assertIsNone(caught.exception.__context__)
        with self.assertRaises(AttemptFailure) as caught:
            self.call(Partial(b''),budget=AttemptBudget(1,1000000,10,10))
        self.assertEqual(caught.exception.received_bytes,13)
        self.assertEqual(caught.exception.code,SourceErrorCode.LIMIT)

    def test_timeout_refreshed_for_headers_and_response_owned_socket(self):
        clock=[0]; observed=[]
        class Socket:
            def settimeout(self,value): observed.append(value)
        class Staged(Connection):
            def connect(self): self.sock=Socket(); clock[0]=1_000_000_000
            def request(self,*args): super().request(*args); clock[0]=8_000_000_000
            def getresponse(self):
                self.header_timeout=observed[-1]
                self.sock=None; clock[0]=9_000_000_000
                return super().getresponse()
        connection=Staged(Response(encoded()))
        with patch('equity_feature_databento.transport.http.client.HTTPSConnection',return_value=connection):
            page=HTTPSDatabentoTransport(DownloadPolicy(),lambda:clock[0])(
                {'schema':'trades'},'private-sentinel',AttemptBudget(1,10_000_000_000,10,524288),lambda:None)
        self.assertEqual(page.row_count,3)
        self.assertEqual(connection.header_timeout,2)
        self.assertEqual(observed,[9,2,1,1])


if __name__=='__main__': unittest.main()
