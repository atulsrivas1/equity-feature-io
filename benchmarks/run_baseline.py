"""Supplied synthetic benchmarks outside core; isolated installed child per case."""
from __future__ import annotations
import argparse
import ctypes
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time


def peak_bytes():
    """Whole process lifetime native resident high-water; never allocation delta."""
    if sys.platform == 'win32':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetCurrentProcess.argtypes = []
        get = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        get.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get.restype = wintypes.BOOL
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        if not get(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.PeakWorkingSetSize), 'Windows PeakWorkingSetSize bytes'
    if sys.platform.startswith('linux'):
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024, 'Linux ru_maxrss KiB times1024'
    raise RuntimeError('native peak units qualified only on Windows/Linux')


def measured(call, rows, repetitions):
    durations=[]
    for _ in range(repetitions):
        start=time.perf_counter_ns(); result=call(); elapsed=time.perf_counter_ns()-start
        if elapsed <= 0: raise AssertionError('nonpositive measurement')
        durations.append(elapsed)
    median=statistics.median(durations)
    return {'samples_ns':durations, 'min_ns':min(durations), 'median_ns':median,
            'max_ns':max(durations), 'rows_per_second':rows*1e9/median}, result


def trade_fixture(rows, seed, skew):
    from equity_feature_contracts import (AvailabilitySpec, BatchMetadata, CanonicalBatch,
        Column, ConfigSpec, Coverage, DataKind, EntityKey, InputScope, Parameter,
        PriceUnit, SessionSpec, SourceBinding, WindowSpec)
    rng=random.Random(seed)
    prices=tuple(rng.randrange(100,201) for _ in range(rows))
    sizes=tuple((100000 if i % 97 == 0 else 1) if skew else rng.randrange(1,101) for i in range(rows))
    fields=(('instrument_id',('A',)*rows),('session_id',('S',)*rows),
            ('event_ns',tuple(range(2,rows+2))),('order_key',tuple(range(rows))),
            ('event_id',tuple(f't{i}' for i in range(rows))),('eligible',(True,)*rows),
            ('price',prices),('size',sizes),('known_at_ns',tuple(range(2,rows+2))))
    unit=PriceUnit(0,'USD'); end=rows+2
    batch=CanonicalBatch(DataKind.TRADE,tuple(Column(n,v) for n,v in fields),
        BatchMetadata('benchmark',SourceBinding('synthetic',f'seed{seed}', 'map1','trades'),
                      Coverage(rows,rows,True),unit,scope=InputScope(1,end,'seeded-v1')))
    config=ConfigSpec('benchmark-trades','v1',(Parameter('eligibility_policy','seeded-v1'),),
        SessionSpec('benchmark','S',1,end,'supplied'),WindowSpec(1,'S',('P','S')),
        AvailabilitySpec(end,end,end),price_unit=unit)
    digest=hashlib.sha256(json.dumps(fields,separators=(',',':')).encode()).hexdigest()
    return batch,config,EntityKey('A','S'),prices,sizes,digest


def verify_trades(result, prices, sizes):
    from equity_feature_contracts import Status
    expected={'session.trade.count':len(prices),'session.trade.volume':sum(sizes),
              'session.trade.notional':sum(p*q for p,q in zip(prices,sizes,strict=True)),
              'session.trade.vwap':float(Fraction(sum(p*q for p,q in zip(prices,sizes,strict=True)),sum(sizes))),
              'session.trade.mean_size':float(Fraction(sum(sizes),len(sizes)))}
    assert all(q.status == Status.AVAILABLE for q in result.quality)
    actual={c.feature_id:c.values[0] for c in result.values}
    assert actual.keys()==expected.keys()
    for name,value in expected.items():
        if type(value) is int: assert type(actual[name]) is int and actual[name]==value
        else: assert math.isclose(actual[name],value,rel_tol=1e-12,abs_tol=1e-12)
    return expected


def history_case(rows,seed,repetitions):
    from equity_feature_contracts import (AvailabilitySpec,BatchMetadata,CanonicalBatch,
        Column,ConfigSpec,Coverage,DataKind,EntityKey,HistoryContext,Parameter,
        PriceUnit,SessionSpec,SourceBinding,Status,WindowSpec)
    from equity_features.history import compute_history
    rng=random.Random(seed); closes=tuple(rng.randrange(100,201) for _ in range(rows))
    sessions=tuple(SessionSpec('benchmark',f'S{i}',10*i+1,10*i+10,'supplied') for i in range(rows))
    entity=EntityKey('A',sessions[-1].session_id); unit=PriceUnit(0,'USD'); period=min(20,rows)
    context=HistoryContext(entity,'seeded-grid-v1',sessions,(Coverage(1,1,True),)*rows,initialization_anchor='S0')
    fields=(('instrument_id',('A',)*rows),('session_id',tuple(s.session_id for s in sessions)),
            ('start_ns',tuple(s.open_ns for s in sessions)),('end_ns',tuple(s.close_ns for s in sessions)),
            ('close',closes),('known_at_ns',tuple(s.close_ns for s in sessions)))
    batch=CanonicalBatch(DataKind.DAILY,tuple(Column(n,v) for n,v in fields),
        BatchMetadata('benchmark',SourceBinding('synthetic',f'seed{seed}','map1','daily'),Coverage(rows,rows,True),unit))
    end=sessions[-1].close_ns
    config=ConfigSpec('benchmark-averages','v1',(Parameter('period',period),),sessions[-1],
        WindowSpec(period,entity.session_id,tuple(s.session_id for s in sessions),'completed_eod'),
        AvailabilitySpec(end,end,end),price_unit=unit)
    alpha=Fraction(2,period+1); ema=Fraction(sum(closes[:period]),period)
    for close in closes[period:]: ema=alpha*close+(1-alpha)*ema
    expected=(float(Fraction(sum(closes[-period:]),period)),float(ema))
    call=lambda:compute_history(batch,config,context=context,feature_ids=('history.sma','history.ema'))
    result=call()
    assert all(q.status == Status.AVAILABLE for q in result.quality)
    assert all(math.isclose(c.values[0],v,rel_tol=1e-12,abs_tol=1e-12) for c,v in zip(result.values,expected,strict=True))
    returns_config=replace(config,identity='benchmark-return',parameters=(Parameter('period',period-1),),
                           window=replace(config.window,count=period))
    returns=lambda:compute_history(batch,returns_config,context=context,feature_ids=('history.return',))
    returned=returns(); return_golden=float(Fraction(closes[-1],closes[-period])-1)
    assert returned.quality[0].status == Status.AVAILABLE
    assert math.isclose(returned.values[0].values[0],return_golden,rel_tol=1e-12,abs_tol=1e-12)
    return {'rows':rows,'period':period,'anchor':'S0','fixture_sha256':hashlib.sha256(json.dumps(fields,separators=(',',':')).encode()).hexdigest(),
            'independent_golden':expected,'timing':measured(call,rows,repetitions)[0],
            'return_period':period-1,'return_golden':return_golden,'return_timing':measured(returns,rows,repetitions)[0]}


def child(args):
    if sys.flags.optimize:
        raise RuntimeError('parity assertions require Python without optimization')
    import equity_feature_contracts as c
    import equity_features as f
    import numpy as np
    import pyarrow as pa
    from equity_feature_contracts import Column,Coverage,Parameter,PrefixCoverage,StreamPopulation,TopKTrades
    from equity_feature_contracts.columnar import to_arrow,from_arrow,to_numpy,from_numpy
    from equity_features.session import compute_trades,compute_top_k
    from equity_features.incremental import SessionAccumulator
    assert 'site-packages' in Path(c.__file__).parts and 'site-packages' in Path(f.__file__).parts, 'actual installed pair required'
    assert c.__version__==f.__version__==f.contracts_version
    pa.set_cpu_count(1); pa.set_io_thread_count(1)
    before,method=peak_bytes(); start=time.perf_counter_ns()
    batch,config,entity,prices,sizes,digest=trade_fixture(args.rows,args.seed,args.skew)
    construction_ns=time.perf_counter_ns()-start; after_fixture,_=peak_bytes()
    aggregate=lambda:compute_trades(batch,config,entity=entity)
    golden=verify_trades(aggregate(),prices,sizes)
    top_config=replace(config,parameters=config.parameters+(Parameter('top_k',args.k),Parameter('evidence_limit',args.k)))
    top=lambda:compute_top_k(batch,top_config,entity=entity)
    result=top(); cell=result.values[0].values[0]; assert isinstance(cell,TopKTrades)
    winners=sorted(range(args.rows),key=lambda i:(-sizes[i],i+2,i,f't{i}'))[:args.k]
    assert [r.event_id for r in cell.rows]==[f't{i}' for i in winners]
    aggregate_timing,_=measured(aggregate,args.rows,args.repetitions)
    top_timing,_=measured(top,args.rows,args.repetitions)
    streams=[]
    for chunk_size in args.chunks:
        start=time.perf_counter_ns()
        chunks=tuple(replace(batch,columns=tuple(Column(c.name,c.values[i:i+chunk_size]) for c in batch.columns),
                     metadata=replace(batch.metadata,coverage=Coverage(min(chunk_size,args.rows-i),min(chunk_size,args.rows-i),True)))
                     for i in range(0,args.rows,chunk_size))
        materialization=time.perf_counter_ns()-start
        def stream():
            accumulator=SessionAccumulator('trades',config,entity=entity,population=StreamPopulation.from_batch(batch))
            ordinal=0
            for chunk in chunks:
                accumulator.update(chunk,start_ordinal=ordinal); ordinal+=len(chunk.columns[0].values)
            return accumulator.finalize(PrefixCoverage(config.session.close_ns,Coverage(args.rows,args.rows,True)))
        streamed=stream();verify_trades(streamed,prices,sizes)
        assert streamed.values==aggregate().values and streamed.quality==aggregate().quality
        streams.append({'chunk_size':chunk_size,'chunks':len(chunks),'chunk_materialization_ns':materialization,
                        'timing_update_and_finalize':measured(stream,args.rows,args.repetitions)[0]})
    arrow=to_arrow(batch); numpy=to_numpy(batch)
    assert from_arrow(arrow)==batch and from_numpy(batch.kind,numpy,batch.metadata)==batch
    numpy_bytes=sum(a.nbytes+mask.nbytes for a,mask in numpy.values())
    original=batch.column('price').values[0]
    restored=from_numpy(batch.kind,numpy,batch.metadata)
    numpy['price'][0][0]=original+1
    assert batch.column('price').values[0]==restored.column('price').values[0]==original
    numpy['price'][0][0]=original
    copies={'arrow_visible_buffer_bytes':arrow.nbytes,'numpy_arrays_and_masks_bytes':numpy_bytes,
            'numpy_owned_array_count':len(numpy)*2,'mutation_isolation_pass':True,
            'to_arrow':measured(lambda:to_arrow(batch),args.rows,args.repetitions)[0],
            'from_arrow':measured(lambda:from_arrow(arrow),args.rows,args.repetitions)[0],
            'to_numpy':measured(lambda:to_numpy(batch),args.rows,args.repetitions)[0],
            'from_numpy':measured(lambda:from_numpy(batch.kind,numpy,batch.metadata),args.rows,args.repetitions)[0]}
    history=history_case(min(args.rows,512),args.seed,args.repetitions)
    end_peak,_=peak_bytes();assert 0<before<=after_fixture<=end_peak
    clock=time.get_clock_info('perf_counter')
    return {'schema':'benchmark1','seed':args.seed,'rows':args.rows,'skew':args.skew,'k':args.k,
            'fixture_sha256':digest,'fixture_construction_ns':construction_ns,'golden':golden,
            'parity_before_timing':True,'aggregate':aggregate_timing,'top_k':top_timing,'streams':streams,
            'copies':copies,'history':history,'native_peak':{'method':method,'initial_bytes':before,
            'after_trade_fixture_bytes':after_fixture,'end_bytes':end_peak,'scope':'whole child process lifetime including inputs/imports/reference/conversions/results'},
            'runtime':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),
            'cpu':platform.processor() or os.environ.get('PROCESSOR_IDENTIFIER','unknown'),'logical_cpus':os.cpu_count(),
            'python':platform.python_version(),'contracts':c.__version__,'features':f.__version__,
            'numpy':np.__version__,'pyarrow':pa.__version__,'arrow_cpu_count':pa.cpu_count(),'arrow_io_thread_count':pa.io_thread_count(),
            'requested_thread_environment':{n:os.environ.get(n) for n in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
            'other_effective_backend_threads':'not independently introspected','gc_policy':'default enabled',
            'clock':clock.implementation,'clock_resolution_seconds':clock.resolution}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',action='store_true');parser.add_argument('--quick',action='store_true')
    parser.add_argument('--rows',type=int);parser.add_argument('--seed',type=int,default=41001)
    parser.add_argument('--skew',action='store_true');parser.add_argument('--k',type=int,default=8)
    parser.add_argument('--chunks',type=int,nargs='+',default=[128,1024]);parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if ((args.rows is not None and not 8<=args.rows<=100000) or not 1<=args.k<=min(args.rows or 128,10000)
            or not 2<=args.repetitions<=20 or any(n<=0 for n in args.chunks)):parser.error('bounded positive cases/repetitions required')
    if args.child:
        if args.rows is None:parser.error('child needs explicit rows')
        print(json.dumps(child(args),sort_keys=True));return
    env=os.environ.copy()
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[name]='1'
    cases=[(args.rows,args.skew)] if args.rows is not None else ([(128,False)] if args.quick else [(128,False),(16384,False),(16384,True)])
    results=[]
    for rows,skew in cases:
        command=[sys.executable,'-I',str(Path(__file__).resolve()),'--child','--rows',str(rows),
                 '--seed',str(args.seed),'--k',str(args.k),'--repetitions',str(args.repetitions),
                 '--chunks',*[str(n) for n in args.chunks]]
        if skew:command.append('--skew')
        results.append(json.loads(subprocess.check_output(command,text=True,env=env)))
    root=Path(__file__).resolve().parent.parent
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain','--','benchmarks','tools/build_foundation.py','tests/unit/test_benchmark_evidence.py'],cwd=root,text=True).strip())
    document={'schema':'benchmark-suite1','source_commit':source,'measurement_source_dirty':dirty,
              'harness_sha256':hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
              'harness_hash_encoding':'UTF8 with normalized LF',
              'cases':results,'timing_scope':'full public checked calls; no source I/O or fixture/conversion creation in calculator timings',
              'limits':'single run baseline; native lifetime peaks are not calculator allocations; no universal performance target'}
    text=json.dumps(document,indent=2,sort_keys=True)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text+'\n',encoding='utf-8')
    else:print(text)


if __name__=='__main__':main()
