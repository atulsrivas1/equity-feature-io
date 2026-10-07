"""Fresh-process measured synthetic workloads; no speedup or hard RSS claim."""
import argparse
import ctypes
import dataclasses
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter


def peak_rss():
    if sys.platform == 'win32':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb',wintypes.DWORD),('faults',wintypes.DWORD)] + [(name,ctypes.c_size_t) for name in ('peak','working','paged_peak','paged','nonpaged_peak','nonpaged','pagefile','pagefile_peak')]
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi',use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        counters = Counters();counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.peak,'Windows GetProcessMemoryInfo PeakWorkingSetSize bytes'
    assert sys.platform == 'linux'
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'Linux getrusage RUSAGE_SELF ru_maxrss KiB converted to bytes'


def filesystem(root):
    if sys.platform == 'win32':
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetVolumeInformationW.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(wintypes.DWORD),wintypes.LPWSTR,wintypes.DWORD]
        name=ctypes.create_unicode_buffer(256)
        if not kernel.GetVolumeInformationW(root.anchor,None,0,None,None,None,name,len(name)):
            raise ctypes.WinError(ctypes.get_last_error())
        return name.value
    candidates=[]
    for line in Path('/proc/self/mountinfo').read_text(encoding='utf-8').splitlines():
        fields=line.split();mount=Path(fields[4].replace('\\040',' '))
        if root.is_relative_to(mount):candidates.append((len(str(mount)),fields[fields.index('-')+1]))
    assert candidates
    return max(candidates)[1]


def child(count, installed):
    import pyarrow as pa
    from equity_feature_contracts.results import EntityKey
    from equity_feature_factory_fixture.publication_facts import synthetic_results
    from equity_feature_io_contracts import SinkRequirements
    from equity_feature_io_sdk.codec import encode_result
    from equity_feature_io_sdk.publication import prepare_publication,publish
    from equity_feature_parquet import ParquetSink
    if installed:
        import equity_feature_parquet
        assert 'site-packages' in Path(equity_feature_parquet.__file__).resolve().parts
    baseline,method=peak_rss()
    base=synthetic_results()[1]
    entities=tuple(EntityKey('I'+str(index),'S') for index in range(count))
    values=tuple(-(2**63)+index for index in range(count))
    result=dataclasses.replace(base,values=(dataclasses.replace(base.values[0],entities=entities,values=values),),quality=tuple(dataclasses.replace(base.quality[0],entity=entity) for entity in entities))
    logical=encode_result(result)
    envelope=prepare_publication((result,),destination_scope='synthetic-resources',generation_id='generation',job_id='job',partition_id='partition',limits=SinkRequirements(max_results=100,max_chunk_bytes=1048576,max_total_bytes=10485760,max_result_cells=100000,max_evidence_rows=100000))
    times={}
    with TemporaryDirectory() as temporary:
        root=Path(temporary)
        fs=filesystem(root)
        with ParquetSink(root,'synthetic-resources') as sink:
            start=perf_counter();session=sink.begin(envelope);times['begin_seconds']=perf_counter()-start
            start=perf_counter();sink.write(session,0,result);times['write_seconds']=perf_counter()-start
            start=perf_counter();receipt=sink.commit(session);times['commit_seconds']=perf_counter()-start
            start=perf_counter();observed=sink.read(receipt);times['read_seconds']=perf_counter()-start
            assert len(observed)==1 and encode_result(observed[0])==logical
            assert observed[0].values[0].values==values
            assert all(q.status==base.quality[0].status for q in observed[0].quality)
            physical=sum(a.byte_length for a in receipt.artifacts)
            controls=sum(p.stat().st_size for p in (root/'.efio-parquet1').rglob('*.json') if p.name in ('reservation.json','complete.json'))
            assert physical<=67108864 and len(logical)<=1048576
        peak,_=peak_rss()
        return dict(cells=count,results=1,evidence_rows=len(result.evidence),logical_bytes=len(logical),physical_bytes=physical,control_bytes=controls,logical_sha256=hashlib.sha256(logical).hexdigest(),parity=True,filesystem=fs,import_lifetime_peak_bytes=baseline,lifetime_peak_rss_bytes=peak,rss_method=method,arrow_peak_bytes=pa.default_memory_pool().max_memory(),timings=times,installed_public_execution=installed,python=platform.python_version(),system=platform.system(),machine=platform.machine(),platform=platform.platform(),parquet=version('equity-feature-parquet'),pyarrow=version('pyarrow'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--child',type=int);parser.add_argument('--installed',action='store_true');parser.add_argument('--report-json',type=Path);args=parser.parse_args()
    if args.child:
        print(json.dumps(child(args.child,args.installed),sort_keys=True))
    else:
        reports=[]
        for count in (64,2048):
            command=[sys.executable,'-I',str(Path(__file__).resolve()),'--child',str(count)]
            if args.installed:command.append('--installed')
            reports.append(json.loads(subprocess.check_output(command,text=True,encoding='utf-8',timeout=120)))
        record=dict(schema='parquet-resources1',workloads=reports,probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),fresh_processes=True,hard_rss_cap=False,speedup_claim=False,private_execution=False,power_loss_certification=False)
        assert args.report_json is not None
        args.report_json.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print('Two fresh-process measured workloads, exact int64/result/status parity PASS')
