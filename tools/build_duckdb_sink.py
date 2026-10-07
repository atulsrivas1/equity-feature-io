"""EQ127 committed repeat archives and real fresh installed sink qualification."""
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

import build_foundation as foundation

ROOT=Path(__file__).resolve().parents[1]
SCOPED=('packages','tools','tests','examples/factory_consumer','requirements-dev.txt','requirements-duckdb-sink.txt','.github/workflows/duckdb-sink.yml')


def qualify(stage, dependencies, artifact, form):
    with tempfile.TemporaryDirectory(prefix='duckdb-sink-install-',dir=ROOT/'work') as temporary:
        location=Path(temporary)
        foundation.run(sys.executable,'-m','venv',location)
        py=location/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        foundation.run(py,'-m','pip','install','--no-deps','setuptools==80.9.0','mypy==1.15.0','mypy_extensions==1.1.0','typing_extensions==4.16.0','duckdb==1.5.6')
        pure=[p for p in dependencies if p.name.startswith(('equity_feature_contracts-','equity_features-'))]
        foundation.install(py,pure)
        before=foundation.fingerprint(py,location)
        foundation.run(py,'-I',stage/'tests/probe_foundation.py','core',cwd=location)
        foundation.install(py,[p for p in dependencies if p not in pure]+[artifact])
        foundation.run(py,'-m','pip','check')
        foundation.run(py,'-I','-c',"import importlib.util;assert importlib.util.find_spec('numpy') is None;assert importlib.util.find_spec('pandas') is None;assert importlib.util.find_spec('pyarrow') is None",cwd=location)
        reports={}
        for script,key in (('test_sink.py','roundtrip'),('test_process.py','process'),('resource_probe.py','resources')):
            report=location/(key+'.json')
            foundation.run(py,'-I',stage/'tests/duckdb-sink'/script,'--installed','--report-json',report,cwd=location)
            reports[key]=json.loads(report.read_text(encoding='utf-8'))
        assert reports['roundtrip']['tests']==18 and reports['roundtrip']['passed']
        assert reports['process']['tests']==9 and reports['process']['passed'] and reports['process']['actual_owned_child_processes']
        assert reports['roundtrip']['test_suite_sha256']==foundation.sha(stage/'tests/duckdb-sink/test_sink.py')
        assert reports['process']['test_suite_sha256']==foundation.sha(stage/'tests/duckdb-sink/test_process.py')
        assert reports['process']['child_sha256']==foundation.sha(stage/'tests/duckdb-sink/process_child.py')
        assert reports['resources']['probe_sha256']==foundation.sha(stage/'tests/duckdb-sink/resource_probe.py')
        assert [w['cells'] for w in reports['resources']['workloads']]==[64,2048]
        assert all(w['parity'] and w['installed_public_execution'] for w in reports['resources']['workloads'])
        for namespace in ('equity_feature_duckdb_sink','equity_feature_io_contracts','equity_feature_io_sdk','equity_feature_factory_fixture'):
            foundation.run(py,'-I','-m','mypy','--strict','-p',namespace,cwd=location)
        caller=location/'caller.py'
        caller.write_text("from pathlib import Path\nfrom equity_feature_duckdb_sink import DuckDBSink, DuckDBSinkFactory\nfrom equity_feature_io_contracts import ResultSink\nfrom equity_feature_io_sdk.factories import SinkRegistry\nsink: ResultSink = DuckDBSink(Path('output.db'), 'synthetic')\nregistry: SinkRegistry[DuckDBSink] = SinkRegistry()\nregistry.register('custom.duckdb-sink', DuckDBSinkFactory())\n",encoding='utf-8')
        foundation.run(py,'-I','-m','mypy','--strict',caller,cwd=location)
        caller.write_text("from pathlib import Path\nfrom equity_feature_duckdb_sink import DuckDBSink\nsink = DuckDBSink(Path('.'), 12)\nsink.begin('wrong')\n",encoding='utf-8')
        rejected=subprocess.run([str(py),'-I','-m','mypy','--strict',str(caller)],cwd=location,text=True,encoding='utf-8',capture_output=True)
        assert rejected.returncode==1 and rejected.stdout.count('error:')==2,rejected.stdout
        after=foundation.fingerprint(py,location);assert before==after
        fingerprint=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
        return dict(form=form,reports=reports,core_before_sha256=fingerprint,core_after_sha256=fingerprint,installed_typing=True,external_positive_typing=True,external_rejected_invalid_calls=2,numpy_required=False,pandas_required=False,pyarrow_required=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core-root',required=True,type=Path);args=parser.parse_args()
    core=args.core_root.resolve();commit=foundation.git(ROOT,'rev-parse','HEAD')
    assert foundation.git(core,'rev-parse',foundation.CORE_COMMIT)==foundation.CORE_COMMIT
    assert not foundation.git(ROOT,'status','--porcelain','--',*SCOPED),'Freeze source before qualification'
    tracked={p:foundation.sha(ROOT/p) for p in ('tools/build_duckdb_sink.py','tools/build_foundation.py','tests/probe_foundation.py','tests/duckdb-sink/test_sink.py','tests/duckdb-sink/test_process.py','tests/duckdb-sink/process_child.py','tests/duckdb-sink/resource_probe.py','requirements-duckdb-sink.txt')}
    output=ROOT/'dist-duckdb-sink';output.mkdir(exist_ok=True)
    assert not list(output.iterdir()),'Use a fresh dist-duckdb-sink directory'
    with tempfile.TemporaryDirectory(prefix='duckdb-sink-build-',dir=ROOT/'work') as temporary:
        location=Path(temporary)
        pure=foundation.snapshot(core,foundation.CORE_COMMIT,location/'core',('packages/contracts','packages/features'))
        source=foundation.snapshot(ROOT,commit,location/'component',('packages','examples/factory_consumer','tests'))
        deps=location/'dependencies'
        for folder in ('contracts','features'):foundation.build(pure/'packages'/folder,deps)
        for folder in ('io-contracts','io-sdk'):foundation.build(source/'packages'/folder,deps)
        foundation.build(source/'examples/factory_consumer',deps)
        dependencies=sorted(deps.glob('*.whl'));assert len(dependencies)==5
        first=location/'first';repeat=location/'repeat'
        for target in (first,repeat):foundation.build(source/'packages/duckdb-sink',target)
        artifacts=sorted(first.iterdir());assert len(artifacts)==2
        for artifact in artifacts:
            assert foundation.sha(artifact)==foundation.sha(repeat/artifact.name)
            foundation.inspect(artifact,'equity-feature-duckdb-sink',['equity-feature-io-sdk==0.1.0a2','duckdb==1.5.6'])
        forms=[qualify(source,dependencies,next(p for p in artifacts if (p.suffix=='.whl')==(form=='wheel')),form) for form in ('wheel','sdist')]
        assert foundation.git(ROOT,'rev-parse','HEAD')==commit
        assert not foundation.git(ROOT,'status','--porcelain','--',*SCOPED)
        assert all(foundation.sha(ROOT/p)==digest for p,digest in tracked.items())
        for artifact in artifacts+dependencies:shutil.copy2(artifact,output/artifact.name)
        record=dict(schema='duckdb-sink-build1',commit=commit,epoch=foundation.EPOCH,python=platform.python_version(),system=platform.system(),machine=platform.machine(),dependency_commits={'equity-features':foundation.CORE_COMMIT,'equity-feature-io':commit},artifacts={p.name:foundation.sha(p) for p in artifacts},dependency_artifacts={p.name:foundation.sha(p) for p in dependencies},source_sha256=tracked,forms=forms)
        (output/'manifest.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('Actual DuckDB sink repeat archives, both fresh forms, process/resource/typing/core parity PASS')


if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True)
    main()
