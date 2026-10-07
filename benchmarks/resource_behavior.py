"""External version-specific retained-state diagnostics; public kernel calls only."""
from __future__ import annotations
import argparse
from dataclasses import asdict,replace
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import types
from unittest.mock import patch


def reachable(root):
    """Deduplicated reachable Python bytes; excludes code/globals/native buffers."""
    seen=set(); counts={}; excluded=set()
    def visit(value):
        if id(value) in seen:return 0
        if isinstance(value,(types.ModuleType,type,types.FunctionType,types.MethodType)):
            excluded.add(type(value).__name__);return 0
        kind=type(value);owned=kind.__module__.startswith(('equity_features','equity_feature_contracts'))
        if not owned and kind not in (dict,list,tuple,set,frozenset,str,bytes,int,float,bool,type(None)):
            excluded.add(kind.__name__);return 0
        seen.add(id(value));counts[kind.__name__]=counts.get(kind.__name__,0)+1
        size=sys.getsizeof(value)
        if kind is dict:size+=sum(visit(k)+visit(v) for k,v in value.items())
        elif kind in (list,tuple,set,frozenset):size+=sum(visit(v) for v in value)
        elif owned and hasattr(value,'__dict__'):size+=visit(vars(value))
        return size
    return {'bytes':visit(root),'object_counts':dict(sorted(counts.items())),
            'excluded_types':sorted(excluded),'scope':'deduplicated reachable builtin/owned Python objects; not exclusive ownership/native memory'}


def fixture(family,rows,k=8,observations=5,windows=2):
    from equity_feature_contracts import (AvailabilitySpec,BatchMetadata,CanonicalBatch,
        Column,ConfigSpec,Coverage,DataKind,EntityKey,InputScope,IntervalCoverage,
        IntervalSpec,Parameter,PriceUnit,SessionSpec,SourceBinding,WindowSpec)
    unit=PriceUnit(0,'USD');end=rows+1
    parameters=[Parameter('eligibility_policy','resource-v1')]
    intervals=()
    fields={'instrument_id':('A',)*rows,'session_id':('S',)*rows}
    if family in ('bars','structure'):
        kind=DataKind.BAR
        fields.update(start_ns=tuple(range(1,rows+1)),end_ns=tuple(range(2,rows+2)),known_at_ns=tuple(range(2,rows+2)),
                      open=(100,)*rows,high=(100,)*rows,low=(100,)*rows,close=(100,)*rows,volume=(10,)*rows,actual_notional=(1000,)*rows)
        if family=='structure':
            intervals=tuple(IntervalSpec(f'w{i}',1+i*(rows//windows),end if i==windows-1 else 1+(i+1)*(rows//windows)) for i in range(windows))
    else:
        kind=DataKind.TRADE if family in ('trades','top_k') else DataKind.QUOTE
        fields.update(event_ns=tuple(range(1,rows+1)),known_at_ns=tuple(range(1,rows+1)),
                      order_key=tuple(range(rows)),event_id=tuple(f'e{i}' for i in range(rows)))
        if kind==DataKind.TRADE:fields.update(eligible=(True,)*rows,price=(100,)*rows,size=(1,)*rows)
        else:fields.update(bid=(100,)*rows,ask=(102,)*rows)
        if family=='top_k':parameters.extend((Parameter('top_k',k),Parameter('evidence_limit',k)))
        elif family=='quotes':parameters.append(Parameter('observation_limit',observations))
        elif family=='continuous':parameters.extend((Parameter('max_age_ns',1),Parameter('initial_state','unknown')))
    interval_coverage=tuple(IntervalCoverage(w.name,w.start_ns,w.end_ns,Coverage(w.end_ns-w.start_ns,w.end_ns-w.start_ns,True)) for w in intervals)
    metadata=BatchMetadata('resource',SourceBinding('synthetic','resource-seed1','map1','input1'),Coverage(rows,rows,True),unit,
        sampling='continuous' if family=='continuous' else 'trade_snapshot' if family=='quotes' else 'none',
        scope=InputScope(1,end,'resource-v1'),interval_coverage=interval_coverage)
    batch=CanonicalBatch(kind,tuple(Column(n,v) for n,v in fields.items()),metadata)
    config=ConfigSpec('resource-'+family,'v1',tuple(parameters),SessionSpec('resource','S',1,end,'supplied',intervals=intervals),
        WindowSpec(1,'S',('P','S')),AvailabilitySpec(end,end,end),price_unit=unit)
    return batch,config,EntityKey('A','S')


def slice_batch(batch,start,end):
    from equity_feature_contracts import Column,Coverage
    return replace(batch,columns=tuple(Column(c.name,c.values[start:end]) for c in batch.columns),
                   metadata=replace(batch.metadata,coverage=Coverage(end-start,end-start,True),interval_coverage=()))


def semantic_equal(left,right):
    if type(left) is float:
        assert type(right) is float and math.isclose(left,right,rel_tol=1e-12,abs_tol=1e-12)
    elif type(left) is dict:
        assert left.keys()==right.keys()
        for key in left:semantic_equal(left[key],right[key])
    elif type(left) in (tuple,list):
        assert type(left) is type(right) and len(left)==len(right)
        for x,y in zip(left,right,strict=True):semantic_equal(x,y)
    else:assert left==right


def check_golden(family,result,rows,k,observations,config):
    from equity_feature_contracts import IntervalVolumeShares,SampledSpread,TimeWeightedSpread,TopKTrades
    values={c.feature_id:c.values[0] for c in result.values}
    if family=='trades':
        assert values['session.trade.count']==values['session.trade.volume']==rows
        assert values['session.trade.notional']==100*rows and values['session.trade.vwap']==100.0
    elif family=='bars':
        assert values['session.bar.volume']==10*rows and values['session.bar.notional']==1000*rows
        assert values['session.bar.close_weighted_price']==100.0
    elif family=='top_k':
        cell=next(iter(values.values()));assert isinstance(cell,TopKTrades)
        assert [r.event_id for r in cell.rows]==[f'e{i}' for i in range(min(k,rows))]
    elif family=='structure':
        shares=next(v for v in values.values() if isinstance(v,IntervalVolumeShares))
        assert all(math.isclose(row.share,(w.end_ns-w.start_ns)/rows,rel_tol=1e-12,abs_tol=1e-12)
                   for row,w in zip(shares.rows,config.session.intervals,strict=True))
    elif family=='quotes':
        spread=values['session.quote.sampled_spread'];assert isinstance(spread,SampledSpread)
        assert spread.total==spread.valid==rows and spread.mean_spread==2.0
        assert math.isclose(spread.mean_bps,20000/101,rel_tol=1e-12,abs_tol=1e-12)
        assert len(spread.rows)==min(observations,rows)
    else:
        spread=next(iter(values.values()));assert isinstance(spread,TimeWeightedSpread)
        assert spread.durations.normal==spread.durations.valid==spread.durations.total==rows
        assert spread.mean_spread==2.0 and math.isclose(spread.mean_bps,20000/101,rel_tol=1e-12,abs_tol=1e-12)


def run_case(family,rows,chunk_size=128,k=8,observations=5,windows=2):
    from equity_feature_contracts import ContractError,Coverage,ErrorCode,PrefixCoverage,StreamPopulation,PartitionSpan
    from equity_features.incremental import SessionAccumulator
    from equity_features.session import compute_bars,compute_structure,compute_trades,compute_top_k,compute_quotes,compute_time_weighted
    if sys.flags.optimize:raise RuntimeError('resource assertions need Python without optimization')
    functions=dict(bars=compute_bars,structure=compute_structure,trades=compute_trades,top_k=compute_top_k,quotes=compute_quotes,continuous=compute_time_weighted)
    batch,config,entity=fixture(family,rows,k,observations,windows)
    population=StreamPopulation.from_batch(batch)
    accumulator=SessionAccumulator(family,config,entity=entity,population=population)
    def denied(*args,**kwargs):raise AssertionError('owned kernel attempted hidden thread/process creation')
    # Excludes arbitrary callbacks/backends; these owned canonical reducers are synchronous.
    with patch('threading.Thread.start',denied),patch('multiprocessing.process.BaseProcess.start',denied),patch('subprocess.Popen',denied):
        for start in range(0,rows,chunk_size):accumulator.update(slice_batch(batch,start,min(rows,start+chunk_size)),start_ordinal=start)
        before=accumulator.export_state();state=json.loads(before.payload);retained=reachable(accumulator)
        assert retained['object_counts'].get('CanonicalBatch',0)==0, 'raw input retained by accumulator'
        assert len(state['top']['rows'])==min(k,rows) if state['top'] is not None else True
        assert len(state['quotes']['rows'])==min(observations,rows) if state['quotes'] is not None else True
        assert len(state['windows'])==(windows if family=='structure' else 0)
        failed=[]
        corrupted=dict(state);corrupted['observed']=-1
        corrupted_text=json.dumps(corrupted,sort_keys=True,separators=(',',':'))
        corrupted_state=replace(before,payload=corrupted_text,payload_digest=hashlib.sha256(corrupted_text.encode()).hexdigest())
        for name,operation in (
            ('wrong_ordinal',lambda:accumulator.update(slice_batch(batch,0,1),start_ordinal=rows+1)),
            ('contradictory_certificate',lambda:accumulator.snapshot(PrefixCoverage(config.session.close_ns,Coverage(rows+1,rows+1,True)))),
            ('incompatible_restore',lambda:SessionAccumulator.restore_state(replace(before,implementation_version='0.0.0'),family,config,entity=entity,population=population)),
            ('corrupt_restore',lambda:SessionAccumulator.restore_state(corrupted_state,family,config,entity=entity,population=population))):
            try:operation()
            except ContractError as error:failed.append({'case':name,'code':error.code.value})
            else:raise AssertionError('invalid operation accepted')
            assert accumulator.export_state()==before
        restored=SessionAccumulator.restore_state(before,family,config,entity=entity,population=population)
        certificate=PrefixCoverage(config.session.close_ns,batch.metadata.coverage,batch.metadata.interval_coverage)
        result=accumulator.finalize(certificate);batch_result=functions[family](batch,config,entity=entity)
        semantic_equal(asdict(result),asdict(batch_result));semantic_equal(asdict(restored.finalize(certificate)),asdict(result))
        check_golden(family,result,rows,k,observations,config)
        # Adjacent caller-certified disjoint partitions; originals are immutable on merge.
        merge=None
        if family!='continuous':
            left=SessionAccumulator(family,config,entity=entity,population=population)
            right=SessionAccumulator(family,config,entity=entity,population=population)
            midpoint=rows//2
            left.update(slice_batch(batch,0,midpoint),start_ordinal=0);right.update(slice_batch(batch,midpoint,rows),start_ordinal=0)
            originals=(left.export_state(),right.export_state())
            merged=left.merge_partitions(right,left=PartitionSpan(0,midpoint),right=PartitionSpan(midpoint,rows))
            assert originals==(left.export_state(),right.export_state())
            semantic_equal(asdict(merged.finalize(certificate)),asdict(result))
            merge={'three_coexisting_states_python_bytes':reachable((left,right,merged))['bytes'],
                   'merged_payload_bytes':len(merged.export_state().payload.encode()),'originals_unchanged':True}
    return {'family':family,'rows':rows,'chunk_size':chunk_size,'chunks':(rows+chunk_size-1)//chunk_size,
            'fixture_sha256':hashlib.sha256(json.dumps(asdict(batch),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'config_sha256':hashlib.sha256(config.to_json().encode()).hexdigest(),
            'k':k,'observation_limit':observations,'windows':windows if family=='structure' else 0,
            'retained_python':retained,'input_python':reachable(batch),'result_python':reachable(result),
            'payload_bytes_unsealed':len(before.payload.encode()),'payload_bytes_sealed':len(accumulator.export_state().payload.encode()),
            'retained_top_rows':len(state['top']['rows']) if state['top'] is not None else 0,
            'retained_quote_rows':len(state['quotes']['rows']) if state['quotes'] is not None else 0,
            'retained_window_rows':len(state['windows']),'atomic_rejections':failed,'batch_stream_restore_merge_parity':True,
            'no_hidden_pool_creation_observed':True,'merge':merge}


def controls():
    from equity_feature_contracts import ContractError,Parameter,PrefixCoverage,Coverage,StreamPopulation
    from equity_feature_contracts.adapters import SourceError,SourceErrorCode
    from equity_features.incremental import SessionAccumulator
    from equity_features.session import compute_trades
    from equity_feature_demo.adapter import adapter_fixture,NeverCancelled
    class Cancel:
        def __init__(self,after):self.after=after;self.calls=0
        def is_cancelled(self):self.calls+=1;return self.calls>self.after
    adapter,request=adapter_fixture();request=replace(request,max_batch_rows=1)
    outcomes=[]
    for name,request_case,cancellation in (('cancel_before',request,Cancel(0)),('row_limit',replace(request,max_rows=1),NeverCancelled()),
                                          ('chunk_limit',replace(request,max_batches=1),NeverCancelled())):
        try:tuple(adapter.iter_batches(request_case,cancellation))
        except SourceError as error:
            assert error.code==(SourceErrorCode.CANCELLED if name.startswith('cancel') else SourceErrorCode.LIMIT)
            outcomes.append({'case':name,'code':error.code.value,'yielded':0})
        else:raise AssertionError('resource rejection expected')
    iterator=adapter.iter_batches(request,Cancel(2));first=next(iterator);assert first.delivery_coverage.observed==1
    try:next(iterator)
    except SourceError as error:assert error.code==SourceErrorCode.CANCELLED;outcomes.append({'case':'cancel_between','code':error.code.value,'yielded':1})
    else:raise AssertionError('betweenchunks cancellation expected')
    batch,config,entity=fixture('trades',8)
    accumulator=SessionAccumulator('trades',config,entity=entity,population=StreamPopulation.from_batch(batch))
    accumulator.update(slice_batch(batch,0,1),start_ordinal=0)
    prefix=accumulator.snapshot(PrefixCoverage(2,Coverage(1,1,True)))
    assert {c.feature_id:c.values[0] for c in prefix.values}['session.trade.count']==1
    for name in ('threads','cancelled'):
        try:compute_trades(batch,replace(config,parameters=config.parameters+(Parameter(name,1),)),entity=entity)
        except ContractError as error:outcomes.append({'case':'unsupported_kernel_'+name,'code':error.code.value})
        else:raise AssertionError('unsupported kernel parameter accepted')
    return {'adapter_outcomes':outcomes,'caller_stopped_prefix_count':1,'midkernel_cancel':'unsupported','kernel_thread_budget':'unsupported',
            'caller_serializes_accumulator':True,'arbitrary_callback_resources':'not certified'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--child',action='store_true')
    parser.add_argument('--quick',action='store_true');parser.add_argument('--family',choices=('bars','structure','trades','top_k','quotes','continuous'))
    parser.add_argument('--rows',type=int);parser.add_argument('--chunk-size',type=int,default=128)
    parser.add_argument('--k',type=int,default=8);parser.add_argument('--observations',type=int,default=5);parser.add_argument('--windows',type=int,default=2)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=128 if args.rows is None else args.rows
    if not 8<=rows<=16384 or args.chunk_size<1 or not 1<=args.k<=10000 or not 0<=args.observations<=10000 or not 1<=args.windows<=rows:parser.error('bounded valid diagnostics required')
    if args.rows is not None and args.family is None:parser.error('custom rows requires family')
    if args.child:
        if args.family is None:parser.error('child family required')
        import equity_feature_contracts as c,equity_features as f,equity_feature_demo as d
        assert all('site-packages' in Path(m.__file__).parts for m in (c,f,d)), 'actual installed core and consumer required'
        assert c.__version__==f.__version__==f.contracts_version
        spec=importlib.util.spec_from_file_location('native_probe',Path(__file__).with_name('run_baseline.py'));native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
        initial,method=native.peak_bytes();result=run_case(args.family,rows,args.chunk_size,args.k,args.observations,args.windows)
        result['controls']=controls()
        result['native_process']={'initial_bytes':initial,'peak_bytes':native.peak_bytes()[0],'method':method,
            'scope':'child lifetime high-water through calculations/control checks, before JSON output; includes input/diagnostics/restore/partitions/results'}
        from importlib.metadata import version
        result['runtime']={'system':platform.system(),'machine':platform.machine(),'python':platform.python_version(),
                           'python_implementation':platform.python_implementation(),'core':f.__version__,'consumer':version('equity-feature-demo')}
        print(json.dumps(result,sort_keys=True));return
    families=('bars','structure','trades','top_k','quotes','continuous')
    cases=([(args.family,rows,args.chunk_size,args.k,args.observations,args.windows)] if args.family is not None
           else [(f,n,128,8,5,2) for n in ((128,) if args.quick else (128,2048,8192)) for f in families])
    if not args.quick and args.family is None:cases.extend([('top_k',8192,16,64,5,2),('quotes',8192,16,8,50,2),('structure',8192,16,8,5,20)])
    results=[]
    for family,rows,chunk,k,obs,windows in cases:
        command=[sys.executable,'-I',str(Path(__file__).resolve()),'--child','--family',family,'--rows',str(rows),'--chunk-size',str(chunk),'--k',str(k),'--observations',str(obs),'--windows',str(windows)]
        results.append(json.loads(subprocess.check_output(command,text=True)))
    root=Path(__file__).resolve().parents[1]
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain','--','benchmarks','tools/build_foundation.py','tests/unit/test_resource_behavior.py'],cwd=root,text=True).strip())
    report={'schema':'resource-suite1','source_commit':source,'measurement_source_dirty':dirty,
            'harness_sha256':hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
            'native_probe_sha256':hashlib.sha256(Path(__file__).with_name('run_baseline.py').read_text(encoding='utf-8').encode()).hexdigest(),
            'harness_hash_encoding':'UTF8 with normalized LF',
            'diagnostic_scope':'version-specific owned graph traversal, not private API/total allocation/nativeRSS','cases':results}
    text=json.dumps(report,sort_keys=True,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text+'\n',encoding='utf-8')
    else:print(text)


if __name__=='__main__':main()
