"""Independent fake clock/transport qualification; synthetic data only."""
import json
import traceback
import unittest
from dataclasses import replace
from pathlib import Path

from equity_feature_contracts import AvailabilitySpec, DataKind, PriceUnit
from equity_feature_contracts.adapters import AcquisitionRequest, SourceError, SourceErrorCode as C
from equity_feature_acquisition import (
    AcquisitionController, AcquisitionLimits, AcquisitionScope, AttemptFailure,
    CachePolicy, DownloadApproval, ImmutableCache, Page, RetentionApproval, RetryPolicy,
)

G = json.loads((Path(__file__).parent.parent / 'acquisition_goldens.json').read_text())
SECRET = 'SENTINEL_PRIVATE_KEY_NEVER_PUBLIC'


class Clock:
    def __init__(self, now=0):
        self.now, self.waits, self.cancel = now, [], False
    def read(self): return self.now
    def sleep(self, ns):
        self.waits.append(ns)
        self.now += ns


class Credentials:
    def __init__(self, hostile=False): self.calls, self.hostile = 0, hostile
    def get(self, name):
        self.calls += 1
        if self.hostile: raise RuntimeError('https://user:' + SECRET + '@host?token=' + SECRET)
        return SECRET
    def __repr__(self): return SECRET


def scope():
    r = AcquisitionRequest('r', DataKind.TRADE, 'synthetic', ('A',), ('S',),
        1700000000000000001, 1700000000000000009, 'revision1', PriceUnit(6, 'USD'),
        AvailabilitySpec(1700000000000000009, 1700000000000000009, 1700000000000000009),
        max_batch_rows=2, max_rows=10, max_batches=5)
    return AcquisitionScope(r, 'synthetic', 'owned', 'fixture', 'historical', 's1', 'm1')


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.s, self.clock, self.creds = scope(), Clock(), Credentials()
        self.approval = DownloadApproval(self.s, 'authorized-A', 1000, AcquisitionLimits(10, 10, 100, 1000, 0))
    def controller(self, approval='default', retry=None):
        return AcquisitionController(self.approval if approval == 'default' else approval,
            clock_ns=self.clock.read, sleep_ns=self.clock.sleep, cancelled=lambda: self.clock.cancel,
            retry=retry or RetryPolicy(4, 100, 400, 1000))
    def execute(self, c, transport, **kw):
        return c.execute(self.s, transport, cost_upper_micro_usd=kw.pop('cost', 0),
            credentials=self.creds, credential_name='token', **kw)
    def error(self, code, fn):
        try: fn()
        except SourceError as e:
            self.assertEqual(e.code, code)
            self.assertIsNone(e.__context__)
            self.assertIsNone(e.__cause__)
            self.assertNotIn(SECRET, ''.join(traceback.format_exception(e)))
            return
        self.fail('SourceError required')
    def never(self, secret, budget): self.fail('transport must not run')
    def test_no_consent_precedes_credentials(self):
        self.error(C.ENTITLEMENT, lambda: self.execute(self.controller(None), self.never))
        self.assertEqual(self.creds.calls, 0)
    def test_scope_complete_identity_mismatches(self):
        requests = [replace(self.s.request, request_id='other'), replace(self.s.request, instruments=('B',)),
            replace(self.s.request, sessions=('T',)), replace(self.s.request, end_ns=self.s.request.end_ns+1),
            replace(self.s.request, snapshot_id='other'), replace(self.s.request, price_unit=PriceUnit(4, 'USD')),
            replace(self.s.request, availability=AvailabilitySpec(self.s.request.end_ns,self.s.request.end_ns+10,self.s.request.end_ns+10))]
        scopes = [replace(self.s, request=r) for r in requests]
        scopes += [replace(self.s, **{key: value}) for key, value in
            [('provider','other'), ('dataset','other'), ('endpoint','other'), ('mode','live'),
             ('source_revision','other'), ('mapping_revision','other')]]
        for s in scopes:
            self.error(C.ENTITLEMENT, lambda: self.execute(self.controller(replace(self.approval, scope=s)), self.never))
        self.assertEqual(self.creds.calls, 0)
    def test_unknown_cost_and_zero_reject_paid_precredential(self):
        for cost in (None, 1):
            self.error(C.ENTITLEMENT if cost is None else C.LIMIT,
                lambda: self.execute(self.controller(), self.never, cost=cost))
        self.assertEqual(self.creds.calls, 0)
    def test_expiry_and_cancel_precredential(self):
        self.clock.now = 1000
        self.error(C.LIMIT, lambda: self.execute(self.controller(), self.never))
        self.clock.now, self.clock.cancel = 0, True
        self.error(C.CANCELLED, lambda: self.execute(self.controller(), self.never))
        self.assertEqual(self.creds.calls, 0)
    def test_one_success_exact_budget_and_ledger(self):
        c = self.controller()
        observed = []
        def transport(secret, budget):
            self.assertEqual(secret, SECRET)
            observed.append((budget.ordinal, budget.deadline_ns, budget.remaining_rows, budget.remaining_bytes))
            return Page(b'abc', 2)
        self.assertEqual(self.execute(c, transport), Page(b'abc', 2))
        self.assertEqual(observed, [(1, 1000, 10, 100)])
        self.assertEqual((c.ledger.calls,c.ledger.received_bytes,c.ledger.rows,c.ledger.reserved_cost_micro_usd),(1,3,2,0))
        self.assertNotIn(SECRET, repr(c) + repr(c.ledger) + repr(self.approval))
    def test_exponential_literal_schedule(self):
        c = self.controller(); calls = []
        def transport(secret, budget):
            calls.append(budget.ordinal)
            if len(calls) < 4: raise AttemptFailure(C.TRANSPORT)
            return Page(b'ok', 1)
        self.execute(c, transport, idempotent=True)
        self.assertEqual(calls, [1,2,3,4])
        self.assertEqual(self.clock.waits, G['retry_exponential_waits_ns'])
    def test_retry_after_schedule(self):
        c = self.controller(); calls = []
        def transport(secret, budget):
            calls.append(1)
            if len(calls) < 3: raise AttemptFailure(C.RATE_LIMIT, retry_after_ns=250 if len(calls)==1 else 0)
            return Page(b'ok', 1)
        self.execute(c, transport, idempotent=True)
        self.assertEqual(self.clock.waits, G['retry_after_waits_ns'])
    def test_deadline_equal_retry_no_sleep(self):
        v = G['deadline_equal_wait']; c = self.controller(replace(self.approval,expires_ns=v['expiry_ns']))
        def transport(secret, budget): raise AttemptFailure(C.RATE_LIMIT,retry_after_ns=v['retry_after_ns'])
        self.error(C.LIMIT, lambda: self.execute(c, transport, idempotent=True))
        self.assertEqual(c.ledger.calls, v['calls']); self.assertEqual(self.clock.waits, v['waits'])
    def test_retries_reserve_cost_without_refund(self):
        v = G['cost_limit']; c = self.controller(replace(self.approval,limits=replace(self.approval.limits,max_cost_micro_usd=v['max_micro_usd'])))
        def transport(secret, budget): raise AttemptFailure(C.TRANSPORT)
        self.error(C.LIMIT,lambda: self.execute(c,transport,idempotent=True,cost=v['upper_per_call']))
        self.assertEqual((c.ledger.calls,c.ledger.reserved_cost_micro_usd,self.creds.calls),(v['calls'],v['reserved_micro_usd'],1))
    def test_failed_bytes_count_against_later_success(self):
        v=G['bytes_limit']; c=self.controller(replace(self.approval,limits=replace(self.approval.limits,max_bytes=v['max_bytes'])))
        def transport(secret,budget):
            if budget.ordinal==1: raise AttemptFailure(C.TRANSPORT,received_bytes=v['failed_bytes'])
            self.assertEqual(budget.remaining_bytes,2)
            return Page(b'abc',1)
        self.error(C.LIMIT,lambda:self.execute(c,transport,idempotent=True))
        self.assertEqual(c.ledger.received_bytes,v['observed_bytes'])
    def test_total_calls_rows_bytes_across_explicit_pages(self):
        for changes, page in [({'max_calls':1},Page(b'a',1)),({'max_rows':1},Page(b'a',1)),({'max_bytes':1},Page(b'a',0))]:
            c=self.controller(replace(self.approval,limits=replace(self.approval.limits,**changes)))
            self.execute(c,lambda s,b:page)
            self.error(C.LIMIT,lambda:self.execute(c,self.never))
        self.assertEqual(self.creds.calls,3)
    def test_no_retry_nonidempotent_or_other_codes(self):
        for code in C:
            for idempotent in (False,True):
                if idempotent and code in (C.RATE_LIMIT,C.TRANSPORT): continue
                c=self.controller()
                def transport(secret,budget): raise AttemptFailure(code)
                self.error(code,lambda:self.execute(c,transport,idempotent=idempotent))
                self.assertEqual(c.ledger.calls,1)
        self.assertEqual(self.clock.waits,[])
    def test_attempt_bound_keeps_last_typed_outcome(self):
        c=self.controller(retry=RetryPolicy(2,100,400,1000))
        def transport(secret,budget): raise AttemptFailure(C.RATE_LIMIT)
        self.error(C.RATE_LIMIT,lambda:self.execute(c,transport,idempotent=True))
        self.assertEqual(c.ledger.calls,2);self.assertEqual(self.clock.waits,[100])
    def test_mid_sleep_cancel_no_second_credentials(self):
        def sleep(ns): self.clock.sleep(ns);self.clock.cancel=True
        c=AcquisitionController(self.approval,clock_ns=self.clock.read,sleep_ns=sleep,cancelled=lambda:self.clock.cancel,retry=RetryPolicy(4,100,400,25))
        def transport(secret,budget):raise AttemptFailure(C.RATE_LIMIT)
        self.error(C.CANCELLED,lambda:self.execute(c,transport,idempotent=True))
        self.assertEqual(self.clock.waits,[25]);self.assertEqual(self.creds.calls,1)
    def test_raw_credential_exception_not_retained(self):
        self.creds=Credentials(True)
        self.error(C.AUTHENTICATION,lambda:self.execute(self.controller(),self.never))
    def test_raw_transport_exception_and_source_error_redacted(self):
        for error in (RuntimeError(SECRET),SourceError(C.SCHEMA,SECRET)):
            def transport(secret,budget): raise error
            c=self.controller();self.error(C.TRANSPORT if type(error) is RuntimeError else C.SCHEMA,lambda:self.execute(c,transport,idempotent=True))
            self.assertEqual(c.ledger.calls,1)
    def test_cancel_after_transport_preserves_consumed_ledger(self):
        c=self.controller()
        def transport(secret,budget):self.clock.cancel=True;return Page(b'a',1)
        self.error(C.CANCELLED,lambda:self.execute(c,transport))
        self.assertEqual((c.ledger.calls,c.ledger.rows,c.ledger.received_bytes),(1,1,1))
    def test_elapsed_transport_late_result_not_returned(self):
        c=self.controller()
        def transport(secret,budget):self.clock.now=1000;return Page(b'a',1)
        self.error(C.LIMIT,lambda:self.execute(c,transport))
        self.assertEqual(c.ledger.calls,1)
    def test_credential_lookup_time_rechecked(self):
        c=self.controller();clock=self.clock
        class SlowCredentials:
            def get(self,name):clock.now=1000;return SECRET
        self.error(C.LIMIT,lambda:c.execute(self.s,self.never,cost_upper_micro_usd=0,credentials=SlowCredentials(),credential_name='token'))
        self.assertEqual(c.ledger.calls,0)
    def test_reentrant_controller_rejected(self):
        c=self.controller()
        def transport(secret,budget):
            self.error(C.LIMIT,lambda:self.execute(c,self.never))
            return Page(b'a',1)
        self.execute(c,transport);self.assertEqual(c.ledger.calls,1)
    def test_bad_clock_and_nonadvancing_sleep(self):
        self.error(C.SCHEMA,lambda:AcquisitionController(self.approval,clock_ns=lambda:True,sleep_ns=lambda n:None,cancelled=lambda:False))
        c=AcquisitionController(self.approval,clock_ns=self.clock.read,sleep_ns=lambda n:None,cancelled=lambda:False,retry=RetryPolicy(2,100,400,25))
        def transport(secret,budget):raise AttemptFailure(C.TRANSPORT)
        self.error(C.SCHEMA,lambda:self.execute(c,transport,idempotent=True))
    def test_integer_controls_reject_bool_negative_and_unbounded(self):
        for bad in (True,0,-1,2**63,1.0):
            self.error(C.SCHEMA,lambda:AcquisitionLimits(bad,1,1,1))
        for bad in (True,-1,2**63,1.0):
            self.error(C.SCHEMA,lambda:Page(b'a',bad))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock(100);self.s=scope()
        self.a=RetentionApproval(self.s,'A',1000,True)
        self.cache=ImmutableCache(clock_ns=self.clock.read,policy=CachePolicy(2,5,10))
    def test_disabled_stores_nothing(self):
        c=ImmutableCache(clock_ns=lambda:self.fail('disabled clock called'))
        c.put(self.a,Page(b'abc',1),page_key='p')
        self.assertIsNone(c.get(self.a,page_key='p'));self.assertEqual(c.stored_bytes,0)
    def test_literal_ttl_boundary_does_not_slide(self):
        v=G['ttl'];self.cache.put(self.a,Page(b'abc',1),page_key='p')
        self.clock.now=v['hit_ns'];self.assertEqual(self.cache.get(self.a,page_key='p'),Page(b'abc',1))
        self.clock.now=v['miss_ns'];self.assertIsNone(self.cache.get(self.a,page_key='p'))
        self.assertEqual((self.cache.entry_count,self.cache.stored_bytes),(0,0))
    def test_authorization_page_and_revision_partitions(self):
        self.cache.put(self.a,Page(b'abc',1),page_key='p')
        for a,key in [(replace(self.a,authorization_scope='B'),'p'),(self.a,'q'),
            (replace(self.a,scope=replace(self.s,mapping_revision='m2')),'p'),
            (replace(self.a,scope=replace(self.s,source_revision='s2')),'p')]:
            self.assertIsNone(self.cache.get(a,page_key=key))
    def test_literal_capacity_and_too_large_preserves_other(self):
        self.cache.put(self.a,Page(b'abc',1),page_key='first')
        self.cache.put(self.a,Page(b'def',1),page_key='second')
        self.assertIsNone(self.cache.get(self.a,page_key='first'))
        with self.assertRaises(SourceError) as e:self.cache.put(self.a,Page(b'abcdef',1),page_key='third')
        self.assertEqual(e.exception.code,C.LIMIT)
        self.assertEqual(self.cache.get(self.a,page_key='second'),Page(b'def',1))
        self.assertEqual((self.cache.entry_count,self.cache.stored_bytes),(1,3))
    def test_entry_count_fifo_replacement_clear(self):
        for key in ('a','b','c'):self.cache.put(self.a,Page(b'x',0),page_key=key)
        self.assertIsNone(self.cache.get(self.a,page_key='a'))
        self.cache.put(self.a,Page(b'yy',0),page_key='b')
        self.assertEqual((self.cache.entry_count,self.cache.stored_bytes),(2,3))
        self.cache.clear();self.assertEqual((self.cache.entry_count,self.cache.stored_bytes),(0,0))
    def test_unauthorized_mutable_live_or_expired(self):
        for a in (replace(self.a,immutable_revision=False),replace(self.a,scope=replace(self.s,mode='live')),replace(self.a,expires_ns=100)):
            with self.assertRaises(SourceError) as e:self.cache.get(a,page_key='p')
            self.assertEqual(e.exception.code,C.ENTITLEMENT)
        self.assertEqual(self.cache.entry_count,0)
    def test_no_raw_payloads_in_reprs(self):
        self.assertNotIn(SECRET,repr(Page(SECRET.encode(),0))+repr(self.cache)+repr(self.a))


if __name__ == '__main__':unittest.main()
