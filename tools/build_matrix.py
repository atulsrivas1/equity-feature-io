"""EQ129 committed three-repository repeat builds and clean compatibility matrix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import build_foundation as foundation

ROOT=Path(__file__).resolve().parents[1]
CORE='45d0fb292234060f8196ba6569ce7805dd921846'
ACCEPTED_IO='395beba80b3bcb2e9db344c6a9d2bcab085be1a6'
WORKER='8ee8719eda773efef838805475173f2b474488df'
OLD_WORKER='b2f13c9a167cf099b080408bb35147cefdefb87a'
OLD_IO='8461ee52a2631ac8aa1be52f6cf222ac7a14b87b'
IO_A1='8f3208d53da095bcf730cdf95f65a749028af2d6'
SCOPED=('packages','examples/third_party','examples/duckdb_conformance.py','tests','tools','requirements-dev.txt','.github/workflows/matrix.yml')
VERSIONS={'equity-feature-contracts':'0.0.4a4','equity-features':'0.0.4a4','equity-feature-io-contracts':'0.1.0a2',
          'equity-feature-io-sdk':'0.1.0a2','equity-feature-duckdb':'0.1.0a8','equity-feature-parquet':'0.1.0a0',
          'equity-feature-duckdb-sink':'0.1.0a0','equity-feature-example-extensions':'0.1.0a0','equity-feature-workers':'0.1.0a1'}

def run_result(*args,cwd):
    return subprocess.run([str(a) for a in args],cwd=cwd,text=True,encoding='utf-8',capture_output=True)

def environment(location):
    foundation.run(sys.executable,'-m','venv',location)
    py=location/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    foundation.run(py,'-m','pip','install','--no-deps','setuptools==80.9.0','mypy==1.15.0','mypy_extensions==1.1.0','typing_extensions==4.16.0')
    return py

def qualify(stage,archives,historical,form):
    with tempfile.TemporaryDirectory(prefix='matrix-install-',dir=ROOT/'work') as temp:
        location=Path(temp);py=environment(location)
        selected=[p for p in archives if (p.suffix=='.whl')==(form=='wheel')]
        pure=[p for p in selected if p.name.startswith(('equity_feature_contracts-','equity_features-'))]
        foundation.install(py,pure);before=foundation.fingerprint(py,location)
        foundation.run(py,'-I',stage/'tests/matrix/probe_core.py',cwd=location)
        standalone=location/'standalone';light_py=environment(standalone)
        light=[p for p in selected if p.name.startswith(('equity_feature_contracts-','equity_feature_io_contracts-','equity_feature_io_sdk-','equity_feature_example_extensions-'))]
        foundation.install(light_py,light);foundation.run(light_py,'-m','pip','check')
        foundation.run(light_py,'-I','-c',"import importlib.util;import equity_feature_example_extensions;assert all(importlib.util.find_spec(n) is None for n in ('equity_features','equity_feature_workers','equity_feature_factory_fixture','equity_feature_duckdb','equity_feature_parquet','equity_feature_duckdb_sink','numpy','pandas','pyarrow','duckdb'))",cwd=standalone)
        foundation.run(py,'-m','pip','install','--no-deps','duckdb==1.5.6','numpy==2.2.6','pyarrow==20.0.0')
        foundation.install(py,[p for p in selected if p not in pure]);foundation.run(py,'-m','pip','check')
        report=location/'composition.json'
        foundation.run(py,'-I',stage/'tests/matrix/test_composition.py','--installed','--report-json',report,cwd=location)
        tests=json.loads(report.read_text(encoding='utf-8'));assert tests['passed'] and tests['tests']==6 and tests['full_result_sink_compositions']==9
        assert tests['actual_installed_modules'] and tests['test_suite_sha256']==foundation.sha(stage/'tests/matrix/test_composition.py')
        foundation.run(py,'-I','-m','mypy','--strict','-p','equity_feature_workers',cwd=location)
        caller=location/'caller.py'
        caller.write_text('from pathlib import Path\nfrom equity_feature_contracts.adapters import HistoricalAdapter\nfrom equity_feature_io_contracts import ResultSink\nfrom equity_feature_example_extensions import ExampleSource,ExampleSink\nfrom equity_feature_parquet import ParquetSink\nfrom equity_feature_duckdb_sink import DuckDBSink\nsource: HistoricalAdapter = ExampleSource()\nsinks: tuple[ResultSink,...] = (ExampleSink(),ParquetSink(Path("out"),"scope"),DuckDBSink(Path("out.db"),"scope"))\n',encoding='utf-8')
        foundation.run(py,'-I','-m','mypy','--strict',caller,cwd=location)
        caller.write_text('from equity_feature_example_extensions import ExampleSource\nfrom equity_feature_duckdb_sink import DuckDBSink\nfrom equity_feature_parquet import ParquetSink\nExampleSource(12)\nDuckDBSink("bad","scope")\nParquetSink("bad","scope")\n',encoding='utf-8')
        wrong=run_result(py,'-I','-m','mypy','--strict',caller,cwd=location);assert wrong.returncode==1 and wrong.stdout.count('error:')==3,wrong.stdout
        # Every requested transitive candidate is present; these fail because exact pins conflict.
        candidates=[p for p in selected+historical if (p.suffix=='.whl')==(form=='wheel')]
        offline=location/'offline';offline.mkdir()
        for path in candidates:shutil.copy2(path,offline/path.name)
        conflicts=[]
        for pair,words in [(('equity-feature-workers==0.1.0a0','equity-feature-io-sdk==0.1.0a2'),('equity-feature-io-sdk==0.1.0a0','equity-feature-io-sdk==0.1.0a2')),
                           (('equity-feature-io-contracts==0.1.0a1','equity-feature-io-sdk==0.1.0a2'),('equity-feature-io-contracts==0.1.0a2','equity-feature-io-contracts==0.1.0a1'))]:
            result=run_result(py,'-m','pip','install','--dry-run','--ignore-installed','--no-index','--no-build-isolation','--find-links',offline,*pair,cwd=location)
            output=result.stdout+result.stderr
            assert result.returncode==1 and 'ResolutionImpossible' in output and 'No matching distribution' not in output,output
            assert all(w in output for w in words),output
            conflicts.append({'pair':pair,'actual_resolver_conflict':True,'all_candidates_present':True})
        # Force each invalid combination in its own real fresh environment and inspect pip check.
        for index,(old_name,current_name) in enumerate((('equity_feature_workers-0.1.0a0','equity_feature_io_sdk-0.1.0a2'),('equity_feature_io_contracts-0.1.0a1','equity_feature_io_sdk-0.1.0a2'))):
            invalid=location/f'invalid-{index}';invalid_py=environment(invalid)
            base=[p for p in selected if p.name.startswith(('equity_feature_contracts-','equity_feature_io_contracts-','equity_feature_io_sdk-')) and not (index==1 and p.name.startswith('equity_feature_io_contracts-'))]
            old=next(p for p in historical if p.name.startswith(old_name) and (p.suffix=='.whl')==(form=='wheel'))
            foundation.install(invalid_py,base+[old])
            result=run_result(invalid_py,'-m','pip','check',cwd=invalid)
            assert result.returncode==1 and ('0.1.0a0' if index==0 else '0.1.0a1') in result.stdout and '0.1.0a2' in result.stdout,result.stdout
            conflicts[index]['actual_forced_pip_check_rejection']=True
        after=foundation.fingerprint(py,location);assert before==after
        fingerprint=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
        return {'form':form,'report':tests,'core_before_sha256':fingerprint,'core_after_sha256':fingerprint,
                'core_only_absence_and_deny':True,'light_extension_without_calculation':True,
                'installed_typing':True,'external_positive_typing':True,'external_invalid_calls':3,'conflicts':conflicts}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core-root',required=True,type=Path);parser.add_argument('--worker-root',required=True,type=Path);a=parser.parse_args()
    roots={'core':a.core_root.resolve(),'io':ROOT,'worker':a.worker_root.resolve()}
    for key,pin in [('core',CORE),('worker',WORKER)]:assert foundation.git(roots[key],'rev-parse',pin)==pin
    commit=foundation.git(ROOT,'rev-parse','HEAD');assert not foundation.git(ROOT,'status','--porcelain','--',*SCOPED)
    tracked={p:foundation.sha(ROOT/p) for p in foundation.git(ROOT,'ls-files',*SCOPED).splitlines()}
    output=ROOT/'dist-matrix';output.mkdir(exist_ok=True);assert not list(output.iterdir()),'Use fresh dist-matrix'
    with tempfile.TemporaryDirectory(prefix='matrix-build-',dir=ROOT/'work') as temp:
        location=Path(temp)
        core=foundation.snapshot(roots['core'],CORE,location/'core',('packages/contracts','packages/features'))
        component=foundation.snapshot(ROOT,commit,location/'component',('packages','examples','tests'))
        worker=foundation.snapshot(roots['worker'],WORKER,location/'worker',('packages',))
        sources=[core/'packages/contracts',core/'packages/features',component/'packages/io-contracts',component/'packages/io-sdk',
                 component/'packages/duckdb',component/'packages/parquet',component/'packages/duckdb-sink',component/'examples/third_party',worker/'packages/workers']
        projects={tomllib.loads((s/'pyproject.toml').read_text(encoding='utf-8'))['project']['name']:s for s in sources}
        assert set(projects)==set(VERSIONS)
        for name,source in projects.items():assert tomllib.loads((source/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']==VERSIONS[name]
        first=location/'first';repeat=location/'repeat'
        for target in (first,repeat):
            for source in sources:foundation.build(source,target)
        archives=sorted(first.iterdir());assert len(archives)==18
        accepted=json.loads((ROOT/'tests/matrix/accepted_archives.json').read_text(encoding='utf-8'))[platform.system()]
        for path in archives:
            assert foundation.sha(path)==foundation.sha(repeat/path.name),path.name
            name=next(n for n in VERSIONS if path.name.startswith(n.replace('-','_')+'-'))
            project=tomllib.loads((projects[name]/'pyproject.toml').read_text(encoding='utf-8'))['project']
            requirements=list(project.get('dependencies',[]))
            for extra,deps in project.get('optional-dependencies',{}).items():
                requirements.extend(f'{dep}; extra == "{extra}"' for dep in deps)
            foundation.inspect(path,name,requirements)
            if name!='equity-feature-workers':assert foundation.sha(path)==accepted[path.name],path.name
        old=foundation.snapshot(roots['worker'],OLD_WORKER,location/'old-worker',('packages',))
        oldio=foundation.snapshot(ROOT,OLD_IO,location/'old-io',('packages/io-contracts','packages/io-sdk'))
        ioa1=foundation.snapshot(ROOT,IO_A1,location/'io-a1',('packages/io-contracts',))
        historical=location/'historical'
        for source in (old/'packages/workers',oldio/'packages/io-contracts',oldio/'packages/io-sdk',ioa1/'packages/io-contracts'):foundation.build(source,historical)
        oldarchives=sorted(historical.iterdir());assert len(oldarchives)==8
        forms=[qualify(component,archives,oldarchives,form) for form in ('wheel','sdist')]
        assert foundation.git(ROOT,'rev-parse','HEAD')==commit and not foundation.git(ROOT,'status','--porcelain','--',*SCOPED)
        assert all(foundation.sha(ROOT/p)==digest for p,digest in tracked.items())
        (output/'historical').mkdir()
        for p in archives:shutil.copy2(p,output/p.name)
        for p in oldarchives:shutil.copy2(p,output/'historical'/p.name)
        record={'schema':'three-repository-matrix1','commit':commit,'epoch':foundation.EPOCH,'python':platform.python_version(),'system':platform.system(),'machine':platform.machine(),
                'dependency_commits':{'equity-features':CORE,'equity-feature-workers':WORKER,'accepted-equity-feature-io':ACCEPTED_IO},
                'historical_commits':{'workers.a0':OLD_WORKER,'SDK.a0':OLD_IO,'contracts.a1':IO_A1},'versions':VERSIONS,
                'artifacts':{p.name:foundation.sha(p) for p in archives},'historical_artifacts':{p.name:foundation.sha(p) for p in oldarchives},
                'source_sha256':tracked,'forms':forms,'accepted_nonworker_archive_equality':True}
        (output/'manifest.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('Nine packages/18 repeat archives/two fresh forms/core-light-full/compositions/conflicts/typing/source guards PASS')
if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True);main()
