"""Literal owned decimal vectors and independently chosen protocol/budget adversaries."""
from dataclasses import replace
from decimal import Decimal, localcontext
import http.client
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from equity_feature_acquisition import AcquisitionLimits, AttemptBudget, AttemptFailure, DownloadApproval
from equity_feature_contracts import AvailabilitySpec, Coverage, DataKind, InputScope, PriceUnit, SourceBinding
from equity_feature_contracts.adapters import AcquisitionRequest, SourceError, SourceErrorCode, validate_delivery
from equity_feature_massive import (DownloadPolicy, HTTPSMassiveTransport, MassiveFactory,
                                   MassiveHistoricalAdapter, MassiveProfile)
from equity_feature_io_contracts import FactoryError
from equity_feature_io_sdk.factories import SourceRegistry

BASE=1700000040000000000; MINUTE=60_000_000_000
GOLD=json.loads((Path(__file__).resolve().parents[1]/'massive_oracle.json').read_text(encoding='utf-8'),parse_float=Decimal)
BAR='{"t":1700000040000,"o":100.000000001,"h":102.000000003,"l":99.000000002,"c":101.000000004,"v":10,"n":3,"vw":101.1}'


def encoded(bars=(BAR,),count=None,base=None,extra=''):
    n=len(bars)
    return ('{"ticker":"AAPL","adjusted":false,"queryCount":'+str(n if base is None else base)+
        ',"resultsCount":'+str(n if count is None else count)+',"status":"OK","results":['+
        ','.join(bars)+']'+extra+'}').encode()


class Credentials:
    def __init__(self):self.names=[]
    def get(self,name):self.names.append(name);return 'private-sentinel'


class Cancel:
    value=False
    def is_cancelled(self):return self.value


class Massive(unittest.TestCase):
    def setUp(self):self.clock=10;self.calls=[];self.credentials=Credentials();self.cancel=Cancel()

    def profile(self,**changes):
        return replace(MassiveProfile('AAPL','A','S','owned-fixture',
            SourceBinding('owned-massive','owned-snapshot','owned-mapping','owned-input'),
            PriceUnit(9,'USD'),InputScope(BASE,BASE+MINUTE,'owned-minute')),**changes)

    def request(self,**changes):
        return replace(AcquisitionRequest('owned-request',DataKind.BAR,'owned-fixture',('A',),('S',),
            BASE,BASE+MINUTE,'owned-snapshot',PriceUnit(9,'USD'),AvailabilitySpec(BASE+MINUTE,BASE+MINUTE,BASE+MINUTE),
            max_batch_rows=3,selection='completed_intervals'),**changes)

    def approve(self,scope):
        return DownloadApproval(scope,'owned-synthetic-only',1000000,
            AcquisitionLimits(1,min(10,scope.request.max_rows),524288,1000000,0))

    def adapter(self,raw=None,profile=None,**kwargs):
        raw=encoded() if raw is None else raw
        def transport(path,credential,budget,check):
            self.calls.append((path,credential,budget));check();return raw
        return MassiveHistoricalAdapter(profile or self.profile(),approve=kwargs.pop('approve',self.approve),
            credentials=self.credentials,clock_ns=lambda:self.clock,cost_upper_micro_usd=kwargs.pop('cost_upper_micro_usd',0),
            transport=kwargs.pop('transport',transport),**kwargs)

    def deliver(self,adapter,request=None):
        request=request or self.request();result=tuple(adapter.iter_batches(request,self.cancel))
        validate_delivery(request,adapter.capabilities(),result);return result

    def error(self,code,callback):
        with self.assertRaises(SourceError) as caught:callback()
        error=caught.exception;self.assertEqual(error.code,code)
        self.assertNotIn('private-sentinel',str(error))
        self.assertIsNone(error.__context__);self.assertIsNone(error.__cause__)

    def test_exact_literal_coefficients_and_null_notional(self):
        result=self.deliver(self.adapter());b=result[0].batch
        for name,value in GOLD['coefficients'].items():self.assertEqual(b.column(name).values,(value,))
        self.assertEqual(b.column('volume').values,(10,));self.assertEqual(b.column('trade_count').values,(3,))
        self.assertEqual(b.column('actual_notional').values,(None,))
        self.assertEqual(b.column('start_ns').values,(GOLD['start_ns'],))
        self.assertEqual(b.column('end_ns').values,(GOLD['end_ns'],))
        self.assertEqual(result[0].source_coverage,Coverage(None,1,False))
        self.assertEqual(self.calls[0][0],'/v2/aggs/ticker/AAPL/range/1/minute/1700000040000/1700000099999?adjusted=false&sort=asc&limit=10')
        self.assertEqual(self.credentials.names,['MASSIVE_API_KEY'])

    def test_decimal_context_does_not_round_prices(self):
        with localcontext() as context:
            context.prec=3
            b=self.deliver(self.adapter())[0].batch
            self.assertEqual(b.column('open').values,(100000000001,))

    def test_fractional_volume_and_excess_price_precision_reject(self):
        for old,new in ((b'"v":10',b'"v":10.25'),(b'100.000000001',b'100.0000000001')):
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter(encoded().replace(old,new))))

    def test_empty_is_observed_unknown_not_missing(self):
        r=self.deliver(self.adapter(encoded(bars=())))[0]
        self.assertEqual(r.batch.row_count,0);self.assertEqual(r.source_coverage,Coverage(None,0,False))

    def test_original_known_at_and_complete_policy_preserved(self):
        p=self.profile(known_at_ns=BASE+MINUTE+999)
        self.assertEqual(self.deliver(self.adapter(profile=p))[0].batch.column('known_at_ns').values,(BASE+MINUTE+999,))
        self.error(SourceErrorCode.SCHEMA,lambda:self.profile(coverage=Coverage(1,1,True)))
        p=self.profile(coverage=Coverage(1,1,True),coverage_policy='independent-owned-minute')
        self.assertEqual(self.deliver(self.adapter(profile=p))[0].source_coverage,Coverage(1,1,True))
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(profile=replace(p,coverage=Coverage(2,2,True)))))

    def test_no_approval_unknown_and_paid_cost_precede_credentials(self):
        for kwargs,code in (({'approve':lambda _:None},SourceErrorCode.ENTITLEMENT),
            ({'cost_upper_micro_usd':None},SourceErrorCode.ENTITLEMENT),
            ({'cost_upper_micro_usd':1},SourceErrorCode.LIMIT)):
            self.error(code,lambda:self.deliver(self.adapter(**kwargs)))
        self.assertEqual(self.credentials.names,[]);self.assertEqual(self.calls,[])

    def test_scope_mismatch_expiry_and_cancel_precede_credentials(self):
        self.error(SourceErrorCode.ENTITLEMENT,lambda:self.deliver(self.adapter(
            approve=lambda s:replace(self.approve(s),scope=replace(s,dataset='OTHER')))))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(
            approve=lambda s:replace(self.approve(s),expires_ns=10))))
        self.cancel.value=True
        self.error(SourceErrorCode.CANCELLED,lambda:self.deliver(self.adapter()))
        self.assertEqual(self.credentials.names,[])

    def test_policy_time_expired_during_approval_or_credential(self):
        def slow(s):self.clock=31;return self.approve(s)
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(approve=slow,policy=DownloadPolicy(max_elapsed_ns=20))))
        self.assertEqual(self.credentials.names,[])
        self.clock=10
        def slow_key(name):self.clock=31;return 'private-sentinel'
        with patch.object(self.credentials,'get',side_effect=slow_key):
            self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=DownloadPolicy(max_elapsed_ns=20))))
        self.assertEqual(self.calls,[])

    def test_exact_population_request_and_profile_alignment(self):
        for changes in ({'instruments':('OTHER',)},{'sessions':('OTHER',)},{'start_ns':BASE+1}):
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter(),self.request(**changes)))
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.profile(scope=InputScope(BASE+1,BASE+MINUTE,'owned-minute')))
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.profile(price_unit=PriceUnit(9,'EUR')))
        self.assertEqual(self.credentials.names,[])

    def test_sensitive_callback_transport_and_credential_exceptions(self):
        def bad(*args):raise RuntimeError('private-sentinel')
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(approve=bad)))
        self.error(SourceErrorCode.TRANSPORT,lambda:self.deliver(self.adapter(transport=bad)))
        with patch.object(self.credentials,'get',side_effect=RuntimeError('private-sentinel')):
            self.error(SourceErrorCode.AUTHENTICATION,lambda:self.deliver(self.adapter()))

    def test_pagination_cap_and_count_inconsistency_rejected(self):
        for raw,code in ((encoded(extra=',"next_url":"private-sentinel"'),SourceErrorCode.LIMIT),
            (encoded(base=10),SourceErrorCode.LIMIT),(encoded(count=2),SourceErrorCode.SCHEMA),
            (encoded(base=0),SourceErrorCode.SCHEMA),(encoded(base=2),SourceErrorCode.SCHEMA)):
            self.error(code,lambda:self.deliver(self.adapter(raw)))

    def test_ticker_adjustment_status_and_offgrid_rejected(self):
        for old,new in ((b'AAPL',b'OTHER'),(b'"adjusted":false',b'"adjusted":true'),
            (b'"status":"OK"',b'"status":"ERROR"'),(b'1700000040000',b'1700000040001'),
            (b'1700000040000',b'1700000100000')):
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter(encoded().replace(old,new))))

    def test_bool_float_duplicate_key_and_nonfinite_rejected(self):
        for old,new in ((b'1700000040000',b'1700000040000.0'),(b'"v":10',b'"v":true'),
            (b'"v":10',b'"v":NaN'),(b'"v":10',b'"v":10,"v":10')):
            self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(encoded().replace(old,new))))

    def test_order_duplicate_invalid_ohlc_reject_before_prefix(self):
        second=BAR.replace('1700000040000','1700000100000')
        p=self.profile(scope=InputScope(BASE,BASE+2*MINUTE,'owned-minute'))
        for bars in ((second,BAR),(BAR,BAR)):
            iterator=self.adapter(encoded(bars),profile=p).iter_batches(self.request(end_ns=BASE+2*MINUTE,max_batch_rows=1),self.cancel)
            self.error(SourceErrorCode.SCHEMA,lambda:next(iterator))
        for old,new in ((b'"h":102.000000003',b'"h":98'),(b'"v":10',b'"v":0'),(b'"o":100.000000001',b'"o":-1')):
            self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(encoded().replace(old,new))))

    def test_rows_bytes_depth_numeric_and_chunk_caps(self):
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=DownloadPolicy(max_rows=1))))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=DownloadPolicy(max_bytes=100,read_chunk_bytes=50))))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(b'['*9+b']'*9)))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(encoded().replace(b'101.1',b'1.'+b'1'*128))))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=DownloadPolicy(max_numeric_chars=3))))
        p=self.profile(scope=InputScope(BASE,BASE+2*MINUTE,'owned-minute'))
        second=BAR.replace('1700000040000','1700000100000')
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(encoded((BAR,second)),profile=p),
            self.request(end_ns=BASE+2*MINUTE,max_batch_rows=1,max_batches=1)))

    def test_chunks_and_record_known_times_bind_identity(self):
        p=self.profile(scope=InputScope(BASE,BASE+2*MINUTE,'owned-minute'),record_known_at_ns=(None,BASE+999))
        second=BAR.replace('1700000040000','1700000100000')
        result=self.deliver(self.adapter(encoded((BAR,second)),profile=p),self.request(end_ns=BASE+2*MINUTE,max_batch_rows=1))
        self.assertEqual([r.final for r in result],[False,True])
        self.assertNotEqual(result[0].source.input_id,result[1].source.input_id)
        self.assertEqual([r.batch.column('known_at_ns').values[0] for r in result],[None,BASE+999])
        self.assertEqual([r.source_coverage.observed for r in result],[2,2])

    def test_single_use_and_concurrent(self):
        a=self.adapter();it=a.iter_batches(self.request(),self.cancel);next(it)
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(a));it.close()
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(a))

    def test_factory_is_explicit_and_identity_bound(self):
        p=self.profile();f=MassiveFactory(p,approve=self.approve)
        for config in ({},{'profile_id':'wrong'},{'profile_id':p.fingerprint,'key':'private-sentinel'}):
            with self.assertRaises(FactoryError):f.validate_config(config)
        registry=SourceRegistry();registry.register('owned-massive',f)
        a=registry.resolve('owned-massive',{'profile_id':p.fingerprint},self.credentials,self.request())
        self.assertEqual(a.capabilities().kinds,(DataKind.BAR,));self.assertEqual(self.credentials.names,[])


class Response:
    def __init__(self,raw,status=200,headers=None):self.stream=io.BytesIO(raw);self.status=status;self.headers=headers or {};self.reads=[]
    def getheader(self,name,default=None):return self.headers.get(name,default)
    def read(self,n):self.reads.append(n);return self.stream.read(n)


class Connection:
    sock=None
    def __init__(self,response):self.response=response;self.requests=[];self.closed=False
    def connect(self):pass
    def request(self,*args,**kwargs):self.requests.append((args,kwargs))
    def getresponse(self):return self.response
    def close(self):self.closed=True


class HTTPS(unittest.TestCase):
    def call(self,response,budget=None):
        connection=Connection(response)
        with patch('equity_feature_massive.transport.http.client.HTTPSConnection',return_value=connection) as constructor:
            raw=HTTPSMassiveTransport(DownloadPolicy(),lambda:10)('/owned-route?limit=10','private-sentinel',
                budget or AttemptBudget(1,1000000,10,524288),lambda:None)
        return raw,connection,constructor

    def test_fixed_host_bearer_header_and_finite_reads(self):
        r=Response(encoded());raw,c,constructor=self.call(r)
        self.assertEqual(raw,encoded());self.assertEqual(constructor.call_args.args,('api.massive.com',))
        args,kwargs=c.requests[0];self.assertEqual(args,('GET','/owned-route?limit=10'))
        self.assertNotIn('private-sentinel',args[1]);self.assertEqual(kwargs['headers']['Authorization'],'Bearer private-sentinel')
        self.assertTrue(c.closed);self.assertLessEqual(max(r.reads),16384)

    def test_status_no_redirect_retry_or_error_body(self):
        for status,code in ((302,SourceErrorCode.UNSUPPORTED),(401,SourceErrorCode.AUTHENTICATION),
            (403,SourceErrorCode.ENTITLEMENT),(404,SourceErrorCode.UNAVAILABLE),
            (429,SourceErrorCode.RATE_LIMIT),(500,SourceErrorCode.TRANSPORT)):
            r=Response(b'private-sentinel',status)
            with self.assertRaises(AttemptFailure) as caught:self.call(r)
            self.assertEqual(caught.exception.code,code);self.assertEqual(r.reads,[])
            self.assertIsNone(caught.exception.__context__);self.assertIsNone(caught.exception.__cause__)

    def test_compressed_declared_and_streamed_body_limits(self):
        for r,code in ((Response(encoded(),headers={'Content-Encoding':'gzip'}),SourceErrorCode.UNSUPPORTED),
            (Response(encoded(),headers={'Content-Length':'524289'}),SourceErrorCode.LIMIT),
            (Response(encoded(),headers={'Content-Length':'1'}),SourceErrorCode.SCHEMA)):
            with self.assertRaises(AttemptFailure) as caught:self.call(r)
            self.assertEqual(caught.exception.code,code)
        with self.assertRaises(AttemptFailure) as caught:self.call(Response(encoded()),AttemptBudget(1,1000000,10,100))
        self.assertEqual(caught.exception.code,SourceErrorCode.LIMIT);self.assertEqual(caught.exception.received_bytes,101)

    def test_partial_read_charged_and_timeout_refreshed(self):
        class Partial(Response):
            def read(self,n):raise http.client.IncompleteRead(b'x'*13,20)
        with self.assertRaises(AttemptFailure) as caught:self.call(Partial(b''))
        self.assertEqual(caught.exception.received_bytes,13);self.assertIsNone(caught.exception.__context__)
        clock=[0];timeouts=[]
        class Socket:
            def settimeout(self,v):timeouts.append(v)
        class Staged(Connection):
            def connect(self):self.sock=Socket();clock[0]=1_000_000_000
            def request(self,*args,**kwargs):super().request(*args,**kwargs);clock[0]=8_000_000_000
            def getresponse(self):self.sock=None;clock[0]=9_000_000_000;return super().getresponse()
        c=Staged(Response(encoded()))
        with patch('equity_feature_massive.transport.http.client.HTTPSConnection',return_value=c):
            HTTPSMassiveTransport(DownloadPolicy(),lambda:clock[0])('/owned-route','private-sentinel',
                AttemptBudget(1,10_000_000_000,10,524288),lambda:None)
        self.assertEqual(timeouts,[9,2,1,1,1])


if __name__=='__main__':unittest.main()
