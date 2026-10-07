"""Independent supplied calendar, warm-up, actual read and reference expectations."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
import unittest

import duckdb
from equity_feature_contracts import (
    ActionPolicy, AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch,
    Column, ConfigSpec, Coverage, DataKind, EntityKey, InputScope, Parameter, PriceUnit,
    Reason, SessionSpec, SourceBinding, Status, WindowSpec,
)
from equity_feature_contracts.adapters import SourceError, SourceErrorCode, validate_delivery
from equity_feature_duckdb import (
    CatalogConfig, DuckDBHistoricalAdapter, GovernedCalendar, MappingPolicy, ReadConfig,
    ReferenceRequest, SourceSelection, make_history_context, parse_utc_ns, plan_history,
    resolve_source, resolve_supplied_reference,
)
from equity_features.history import compute_history
from equity_features.policies import admit_action_policy, admit_classification
import test_reader as source_fixture

DAY=86400*10**9
UNIT=PriceUnit(0,'USD')


def calendar(n=5):
    pairs=tuple(((date(1970,1,1)+timedelta(days=i)).isoformat(),
        SessionSpec('gov',f'S{i+1}',i*DAY,(i+1)*DAY,'UTC')) for i in range(n))
    return GovernedCalendar('gov','supplied-grid1','fixture-evidence1',pairs,
        grid_kind='utc_daily_intervals')


def daily(cal,missing=(1,),null=()):
    indices=tuple(i for i in range(len(cal.sessions)) if i not in missing)
    values=dict(instrument_id=('A',)*len(indices),session_id=tuple(cal.sessions[i].session_id for i in indices),
        start_ns=tuple(cal.sessions[i].open_ns for i in indices),end_ns=tuple(cal.sessions[i].close_ns for i in indices),
        close=tuple(None if i in null else (i+1)*10 for i in indices))
    return CanonicalBatch(DataKind.DAILY,tuple(Column(n,v) for n,v in values.items()),
        BatchMetadata('gov',SourceBinding('caller-fixture','r1','daily1','d1'),Coverage(None,len(indices),False),UNIT))


def certificates(cal,missing=(1,)):
    return tuple(Coverage(1,int(i not in missing),i not in missing) for i in range(len(cal.sessions)))


def reference(kind='sector_membership',known=210,snapshot='ref-r1',text='sector-old'):
    values=dict(instrument_id=('A',),session_id=('R',),reference_id=('fact1',),fact_kind=(kind,),
        effective_start_ns=(100,),known_at_ns=(known,))
    if kind=='split_factor':values.update(factor_num=(1,),factor_den=(2,))
    else:values['text']=(text,)
    return CanonicalBatch(DataKind.REFERENCE,tuple(Column(n,v) for n,v in values.items()),
        BatchMetadata('gov',SourceBinding('caller-fixture',snapshot,'ref1','r1'),Coverage(1,1,True),None))


def ref_config(availability=None,adjustment=None):
    return ConfigSpec('reference-test','v1',(),SessionSpec('gov','R',0,200,'supplied'),
        WindowSpec(1,'R',('R',),'completed_eod'),availability or AvailabilitySpec(200,210,220),
        price_unit=UNIT,adjustment=adjustment or AdjustmentSpec())


class GovernanceTests(unittest.TestCase):
    def error(self,code,call):
        with self.assertRaises(SourceError) as caught:call()
        self.assertEqual(caught.exception.code,code)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_owned_calendar_identity_and_closure(self):
        c=calendar();rows=list(c.dated_sessions)
        owned=replace(c,dated_sessions=rows,closed_dates=['1970-01-06']);rows.clear()
        self.assertEqual(len(owned.sessions),5)
        self.assertEqual(owned.partition_sessions[2],('1970-01-03','S3'))
        self.assertNotEqual(c.identity_digest,owned.identity_digest)
        self.assertNotEqual(c.identity_digest,replace(c,version='r2').identity_digest)
        with self.assertRaises(FrozenInstanceError):owned.version='mutated'
        self.error(SourceErrorCode.SCHEMA,lambda:replace(c,closed_dates=('1970-01-03',)))

    def test_supplied_dst_and_early_close_exact_bounds(self):
        stamps=(('2026-03-06','14:30:00','21:00:00'),('2026-03-09','13:30:00','20:00:00'),
                ('2026-11-27','14:30:00','18:00:00'))
        pairs=[]
        for i,(d,op,cl) in enumerate(stamps):
            early=i==2
            pairs.append((d,SessionSpec('gov',f'X{i}',parse_utc_ns(d+'T'+op+'Z'),parse_utc_ns(d+'T'+cl+'Z'),
                'caller-Eastern',scheduled_close_ns=parse_utc_ns(d+'T21:00:00Z') if early else None,early_close=early)))
        c=GovernedCalendar('gov','fictional-hours1','caller-schedule1',pairs,('2026-03-10',))
        self.assertEqual(tuple((s.close_ns-s.open_ns)//10**9 for s in c.sessions),(23400,23400,12600))
        p=plan_history(c,WindowSpec(1,'X2',('X0','X1','X2'),'completed_eod'))
        req=p.acquisition_request('r',DataKind.BAR,('A',),'r1',UNIT,AvailabilitySpec(c.sessions[-1].close_ns,c.sessions[-1].close_ns,c.sessions[-1].close_ns))
        self.assertEqual(req.end_ns,parse_utc_ns('2026-11-27T18:00:00Z'))
        self.assertEqual(req.sessions,('X2',))
        self.error(SourceErrorCode.UNSUPPORTED,lambda:p.acquisition_request('r',DataKind.DAILY,('A',),'r1',UNIT,req.availability))

    def test_invalid_calendar_is_not_sorted_or_inferred(self):
        c=calendar()
        for kwargs in (dict(dated_sessions=tuple(reversed(c.dated_sessions))),dict(namespace='other'),
                       dict(dated_sessions=(c.dated_sessions[0],)*2),dict(max_sessions=4),
                       dict(dated_sessions=((c.dated_sessions[0][0],replace(c.sessions[0],close_ns=DAY-1)),))):
            code=SourceErrorCode.LIMIT if 'max_sessions' in kwargs else SourceErrorCode.SCHEMA
            self.error(code,lambda:replace(c,**kwargs))

    def test_finite_prior_only_and_anchored_requirements(self):
        c=calendar();ids=tuple(s.session_id for s in c.sessions)
        p=plan_history(c,WindowSpec(3,'S5',ids,'completed_eod'))
        self.assertEqual(p.required_session_ids,('S3','S4','S5'));self.assertTrue(p.history_complete)
        prior=plan_history(c,WindowSpec(2,'S5',ids,'prior_only'))
        self.assertEqual(prior.required_session_ids,('S3','S4'))
        anchor=plan_history(c,WindowSpec(3,'S5',ids,'completed_eod'),'S1')
        self.assertEqual(anchor.required_session_ids,ids)
        previous=plan_history(c,WindowSpec(3,'S5',ids,'completed_eod'),'S2',True)
        self.assertEqual(previous.required_session_ids,ids)
        self.assertNotEqual(p.identity_digest,anchor.identity_digest)
        self.assertEqual(prior.dated_sessions[-1][1].session_id,'S4')

    def test_insufficient_anchor_grid_and_limits(self):
        c=calendar();ids=tuple(s.session_id for s in c.sessions)
        p=plan_history(c,WindowSpec(6,'S5',ids,'completed_eod'))
        self.assertFalse(p.history_complete)
        self.error(SourceErrorCode.UNAVAILABLE,lambda:p.acquisition_request('r',DataKind.DAILY,('A',),'r1',UNIT,AvailabilitySpec(5*DAY,5*DAY,5*DAY)))
        for anchor,previous in [('absent',False),('S1',True)]:
            self.error(SourceErrorCode.UNAVAILABLE,lambda:plan_history(c,WindowSpec(3,'S5',ids,'completed_eod'),anchor,previous))
        self.error(SourceErrorCode.SCHEMA,lambda:plan_history(c,WindowSpec(2,'S5',('S3','S4','S5'),'completed_eod')))
        self.error(SourceErrorCode.LIMIT,lambda:plan_history(c,WindowSpec(3,'S5',ids,'completed_eod'),max_sessions=2))

    def test_history_gap_finite_recovery_and_recursive_unavailability(self):
        c=calendar();b=daily(c);entity=EntityKey('A','S5')
        ctx=make_history_context(c,entity,b,certificates(c),'S1')
        cfg=ConfigSpec('history-test','v1',(Parameter('period',3),),c.sessions[-1],
            WindowSpec(3,'S5',tuple(s.session_id for s in c.sessions),'completed_eod'),
            AvailabilitySpec(5*DAY,5*DAY,5*DAY,'reconstruction','unknown retained source availability'),price_unit=UNIT)
        result=compute_history(b,cfg,context=ctx,feature_ids=('history.sma','history.ema'))
        self.assertEqual(result.values[0].values,(40.0,));self.assertEqual(result.quality[0].status,Status.AVAILABLE)
        self.assertEqual(result.values[1].values,(None,));self.assertEqual(result.quality[1].status,Status.INCOMPLETE_COVERAGE)
        self.assertIn(Reason.GOVERNED_GAP,result.quality[1].reasons)
        self.assertEqual(ctx.slot_coverage[1],Coverage(1,0,False))

    def test_actual_row_certificates_and_intervals_required(self):
        c=calendar();b=daily(c);entity=EntityKey('A','S5');cert=certificates(c)
        self.error(SourceErrorCode.SCHEMA,lambda:make_history_context(c,entity,b,certificates(c,())))
        self.error(SourceErrorCode.SCHEMA,lambda:make_history_context(c,entity,None,cert))
        cols=tuple(Column(x.name,tuple(v+1 for v in x.values)) if x.name=='end_ns' else x for x in b.columns)
        self.error(SourceErrorCode.SCHEMA,lambda:make_history_context(c,entity,replace(b,columns=cols),cert))
        self.error(SourceErrorCode.SCHEMA,lambda:make_history_context(c,EntityKey('B','S5'),b,cert))
        missing=make_history_context(c,entity,None,certificates(c,tuple(range(5))))
        self.assertTrue(all(x.observed==0 and not x.complete for x in missing.slot_coverage))

    def test_null_close_is_present_not_filled(self):
        c=calendar();b=daily(c,null=(3,));ctx=make_history_context(c,EntityKey('A','S5'),b,certificates(c))
        self.assertEqual(ctx.slot_coverage[3],Coverage(1,1,True))
        self.assertEqual(b.column('close').values,(10,30,None,50))

    def test_actual_parquet_plan_prior_only_and_missing_prefix(self):
        fixture=source_fixture.ReaderTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.init_catalog('ohlcv-1d');c=calendar()
        for i,(d,_) in enumerate(c.dated_sessions):
            if i==1:continue
            price=(i+1)*10
            fixture.add_file(f"SELECT 7 instrument_id,'{d}T00:00:00Z' ts_utc,{price}::DOUBLE open,{price}::DOUBLE high,{price}::DOUBLE low,{price}::DOUBLE \"close\",1::UBIGINT volume",1)
            with duckdb.connect(str(fixture.db)) as con:
                con.execute('UPDATE catalog.catalog.files SET session_date=? WHERE path=?',[d,str(fixture.parts[-1])])
        resolved=resolve_source(CatalogConfig(fixture.db),SourceSelection('prepared','frozen1','FICTION','ohlcv-1d',tuple(d for d,_ in c.dated_sessions)))
        mapping=MappingPolicy('ohlcv-1d',UNIT,'binary64_exact','exact',((7,'A'),),'receive_aggregation')
        adapter=DuckDBHistoricalAdapter(ReadConfig(fixture.db,resolved,mapping,'gov','synthetic',c.version,
            c.sessions,c.partition_sessions,InputScope(0,5*DAY,'fixture1')))
        ids=tuple(s.session_id for s in c.sessions);av=AvailabilitySpec(5*DAY,5*DAY,5*DAY)
        prior=plan_history(c,WindowSpec(2,'S5',ids,'prior_only'))
        req=prior.acquisition_request('prior',DataKind.DAILY,('A',),'frozen1',UNIT,av)
        r=adapter.read(req);validate_delivery(req,adapter.capabilities(),r.batches)
        self.assertEqual(r.canonical.column('close').values,(30,40))
        self.assertEqual(sum(r.canonical.column('close').values)/2,35)
        self.assertEqual(req.end_ns,4*DAY)
        full=plan_history(c,WindowSpec(3,'S5',ids,'completed_eod'),'S1')
        prefix=adapter.read(full.acquisition_request('prefix',DataKind.DAILY,('A',),'frozen1',UNIT,av))
        self.assertIsNone(prefix.canonical);self.assertEqual(prefix.batches[0].disposition,'missing')
        finite=plan_history(c,WindowSpec(3,'S5',ids,'completed_eod'))
        acquired=adapter.read(finite.acquisition_request('finite',DataKind.DAILY,('A',),'frozen1',UNIT,av)).canonical
        self.assertEqual(acquired.column('close').values,(30,40,50))
        ctx=make_history_context(c,EntityKey('A','S5'),acquired,certificates(c,(0,1)),'S1')
        cfg=ConfigSpec('acquired-history','v1',(Parameter('period',3),),c.sessions[-1],finite.window,
            AvailabilitySpec(5*DAY,5*DAY,5*DAY,'reconstruction','fixture unknown retained availability'),price_unit=UNIT)
        numerical=compute_history(acquired,cfg,context=ctx,feature_ids=('history.sma','history.ema'))
        self.assertEqual(numerical.values[0].values,(40.0,))
        self.assertEqual(numerical.quality[0].status,Status.AVAILABLE)
        self.assertEqual(numerical.values[1].values,(None,))
        self.assertEqual(numerical.quality[1].status,Status.INCOMPLETE_COVERAGE)

    def test_reference_unavailable_and_unknown_preserved(self):
        req=ReferenceRequest('gov','ref-r1',('A',),('sector_membership',),AvailabilitySpec(200,210,220))
        absent=resolve_supplied_reference(req);self.assertEqual((absent.disposition,absent.evidence_gaps),('unavailable',('not_supplied',)))
        b=reference(known=None);r=resolve_supplied_reference(req,b)
        self.assertIs(r.batch,b);self.assertEqual(r.evidence_gaps,('unknown_availability',))
        self.assertEqual(r.batch.column('known_at_ns').values,(None,))
        self.assertNotEqual(r.identity_digest,absent.identity_digest)

    def test_reference_revisions_and_causal_reconstruction_admission(self):
        cfg=ref_config();entity=EntityKey('A','R')
        req=ReferenceRequest('gov','ref-r1',('A',),('sector_membership',),cfg.availability)
        old=resolve_supplied_reference(req,reference());new=resolve_supplied_reference(replace(req,snapshot_id='ref-r2'),reference(snapshot='ref-r2',known=211,text='sector-new'))
        self.assertNotEqual(old.identity_digest,new.identity_digest);self.assertEqual(new.evidence_gaps,('future_knowledge',))
        causal=admit_classification(new.batch,cfg,entity=entity,effective_ns=200,fact_kind='sector_membership')
        self.assertEqual(causal.status,Status.MISSING_INPUT)
        reconstruction=replace(cfg,availability=AvailabilitySpec(200,210,220,'reconstruction','late supplied revision'))
        r=admit_classification(new.batch,reconstruction,entity=entity,effective_ns=200,fact_kind='sector_membership')
        self.assertEqual(r.status,Status.AVAILABLE)
        self.assertNotEqual(causal.identity_digest,r.identity_digest)
        self.assertEqual(new.batch.column('known_at_ns').values,(211,))

    def test_split_reference_exact_revision_and_knowledge(self):
        adjust=AdjustmentSpec('split','split-factors-v1','ref-r1','R');cfg=ref_config(adjustment=adjust)
        req=ReferenceRequest('gov','ref-r1',('A',),('split_factor',),cfg.availability)
        result=resolve_supplied_reference(req,reference(kind='split_factor',known=211))
        policy=ActionPolicy(adjust,200)
        causal=admit_action_policy(result.batch,policy,cfg,entity=EntityKey('A','R'))
        self.assertEqual(causal.status,Status.MISSING_INPUT)
        reconstructed=admit_action_policy(result.batch,policy,replace(cfg,availability=AvailabilitySpec(200,210,220,'reconstruction','late split evidence')),entity=EntityKey('A','R'))
        self.assertEqual(reconstructed.status,Status.AVAILABLE)
        self.assertEqual((reconstructed.facts[0].factor_num,reconstructed.facts[0].factor_den),(1,2))

    def test_reference_mismatch_count_limits_and_no_hidden_filter(self):
        req=ReferenceRequest('gov','ref-r1',('A',),('sector_membership',),AvailabilitySpec(200,210,220))
        b=reference()
        for kwargs in (dict(namespace='other'),dict(snapshot_id='other'),dict(instruments=('B',)),dict(fact_kinds=('split_factor',))):
            self.error(SourceErrorCode.SCHEMA,lambda:resolve_supplied_reference(replace(req,**kwargs),b))
        two=CanonicalBatch(DataKind.REFERENCE,tuple(Column(x.name,x.values+(("fact2",) if x.name=='reference_id' else x.values)) for x in b.columns),replace(b.metadata,coverage=Coverage(2,2,True)))
        self.error(SourceErrorCode.LIMIT,lambda:resolve_supplied_reference(replace(req,max_rows=1),two))
        partial=replace(b,metadata=replace(b.metadata,coverage=Coverage(None,1,False)))
        self.assertEqual(resolve_supplied_reference(req,partial).evidence_gaps,('incomplete_coverage',))


if __name__=='__main__':unittest.main()
