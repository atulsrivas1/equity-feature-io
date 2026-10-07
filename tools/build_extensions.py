"""EQ128 committed repeat artifacts, clean public extension composition/typing."""
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

ROOT = Path(__file__).resolve().parents[1]
SCOPED = ('packages', 'examples/third_party', 'examples/factory_consumer', 'tests', 'tools',
          'requirements-dev.txt', '.github/workflows/extensions.yml')


def qualify(stage, dependencies, artifact, form):
    with tempfile.TemporaryDirectory(prefix='extension-install-',dir=ROOT/'work') as temporary:
        location=Path(temporary);foundation.run(sys.executable,'-m','venv',location)
        py=location/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        foundation.run(py,'-m','pip','install','--no-deps','setuptools==80.9.0','mypy==1.15.0','mypy_extensions==1.1.0','typing_extensions==4.16.0')
        pure=[p for p in dependencies if p.name.startswith(('equity_feature_contracts-','equity_features-'))]
        foundation.install(py,pure);before=foundation.fingerprint(py,location)
        foundation.run(py,'-I',stage/'tests/probe_foundation.py','core',cwd=location)
        # The test fixture is not an extension runtime dependency.
        fixture=[p for p in dependencies if p.name.startswith('equity_feature_factory_fixture-')]
        # A separate actual install proves the extension itself needs no calculation library.
        standalone=location/'standalone';foundation.run(sys.executable,'-m','venv',standalone)
        standalone_py=standalone/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        foundation.run(standalone_py,'-m','pip','install','--no-deps','setuptools==80.9.0')
        light=[p for p in dependencies if not p.name.startswith(('equity_features-','equity_feature_factory_fixture-'))]
        foundation.install(standalone_py,light+[artifact])
        foundation.run(standalone_py,'-m','pip','check')
        foundation.run(standalone_py,'-I','-c',"import importlib.util;import equity_feature_example_extensions;assert all(importlib.util.find_spec(n) is None for n in ('equity_features','equity_feature_factory_fixture','numpy','pandas','pyarrow','duckdb','equity_feature_duckdb','equity_feature_duckdb_sink','equity_feature_parquet','equity_feature_workers'))",cwd=standalone)
        foundation.install(py,[p for p in dependencies if p not in pure and p not in fixture]+[artifact])
        foundation.run(py,'-m','pip','check')
        foundation.run(py,'-I','-c',"import importlib.util,sys;import equity_feature_example_extensions;assert 'equity_features' not in sys.modules;assert importlib.util.find_spec('equity_feature_factory_fixture') is None;assert all(importlib.util.find_spec(n) is None for n in ('numpy','pandas','pyarrow','duckdb','equity_feature_duckdb','equity_feature_duckdb_sink','equity_feature_parquet','equity_feature_workers'))",cwd=location)
        foundation.run(py,'-I','-m','equity_feature_example_extensions.demo','--mode','both',cwd=location)
        foundation.install(py,fixture)
        report=location/'extensions.json'
        foundation.run(py,'-I',stage/'tests/extensions/test_extensions.py','--installed','--report-json',report,cwd=location)
        tests=json.loads(report.read_text(encoding='utf-8'))
        assert tests['tests']==12 and tests['passed'] and tests['actual_conformance_cases']==21 and tests['complete_synthetic_results']==18
        assert tests['test_suite_sha256']==foundation.sha(stage/'tests/extensions/test_extensions.py')
        foundation.run(py,'-I','-m','mypy','--strict','-p','equity_feature_example_extensions',cwd=location)
        caller=location/'caller.py'
        caller.write_text('from equity_feature_contracts.adapters import HistoricalAdapter\nfrom equity_feature_io_contracts import ResultSink\nfrom equity_feature_example_extensions import ExampleSource,ExampleSink,SourceFactory,SinkFactory\nfrom equity_feature_example_extensions.protocol_stubs import SourceStub,SinkStub\nfrom equity_feature_io_sdk import SourceRegistry,SinkRegistry\nsource: HistoricalAdapter = ExampleSource()\nsink: ResultSink = ExampleSink()\nsource_stub: HistoricalAdapter = SourceStub()\nsink_stub: ResultSink = SinkStub()\nsources: SourceRegistry[ExampleSource] = SourceRegistry()\nsinks: SinkRegistry[ExampleSink] = SinkRegistry()\nsources.register("example",SourceFactory())\nsinks.register("example",SinkFactory())\n',encoding='utf-8')
        foundation.run(py,'-I','-m','mypy','--strict',caller,cwd=location)
        caller.write_text('from equity_feature_example_extensions import ExampleSource,ExampleSink\nsource = ExampleSource(12)\nExampleSink().begin("wrong")\n',encoding='utf-8')
        rejected=subprocess.run([str(py),'-I','-m','mypy','--strict',str(caller)],cwd=location,text=True,encoding='utf-8',capture_output=True)
        assert rejected.returncode==1 and rejected.stdout.count('error:')==2,rejected.stdout
        after=foundation.fingerprint(py,location);assert before==after
        fingerprint=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
        return dict(form=form,report=tests,core_before_sha256=fingerprint,core_after_sha256=fingerprint,
                    installed_typing=True,external_positive_typing=True,external_rejected_invalid_calls=2,
                    standalone_without_calculation_library=True,runtime_fixture_required=False,backend_required=False,numpy_required=False,pandas_required=False,pyarrow_required=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core-root',required=True,type=Path);args=parser.parse_args()
    core=args.core_root.resolve();commit=foundation.git(ROOT,'rev-parse','HEAD')
    assert foundation.git(core,'rev-parse',foundation.CORE_COMMIT)==foundation.CORE_COMMIT
    assert not foundation.git(ROOT,'status','--porcelain','--',*SCOPED),'Freeze source before qualification'
    paths=foundation.git(ROOT,'ls-files','examples/third_party','tests/extensions','tools/build_extensions.py','tools/build_foundation.py','tests/probe_foundation.py','.github/workflows/extensions.yml').splitlines()
    tracked={p:foundation.sha(ROOT/p) for p in paths};assert len(tracked)>=12
    output=ROOT/'dist-extensions';output.mkdir(exist_ok=True);assert not list(output.iterdir()),'Use a fresh dist-extensions directory'
    with tempfile.TemporaryDirectory(prefix='extension-build-',dir=ROOT/'work') as temporary:
        location=Path(temporary)
        pure=foundation.snapshot(core,foundation.CORE_COMMIT,location/'core',('packages/contracts','packages/features'))
        source=foundation.snapshot(ROOT,commit,location/'component',('packages','examples/factory_consumer','examples/third_party','tests'))
        deps=location/'dependencies'
        for folder in ('contracts','features'):foundation.build(pure/'packages'/folder,deps)
        for folder in ('io-contracts','io-sdk'):foundation.build(source/'packages'/folder,deps)
        foundation.build(source/'examples/factory_consumer',deps)
        dependencies=sorted(deps.glob('*.whl'));assert len(dependencies)==5
        first=location/'first';repeat=location/'repeat'
        for target in (first,repeat):foundation.build(source/'examples/third_party',target)
        artifacts=sorted(first.iterdir());assert len(artifacts)==2
        for artifact in artifacts:
            assert foundation.sha(artifact)==foundation.sha(repeat/artifact.name)
            foundation.inspect(artifact,'equity-feature-example-extensions',['equity-feature-contracts==0.0.4a4','equity-feature-io-sdk==0.1.0a2'])
        forms=[qualify(source,dependencies,next(p for p in artifacts if (p.suffix=='.whl')==(form=='wheel')),form) for form in ('wheel','sdist')]
        assert foundation.git(ROOT,'rev-parse','HEAD')==commit
        assert not foundation.git(ROOT,'status','--porcelain','--',*SCOPED)
        assert all(foundation.sha(ROOT/p)==digest for p,digest in tracked.items())
        for artifact in artifacts+dependencies:shutil.copy2(artifact,output/artifact.name)
        record=dict(schema='example-extension-build1',commit=commit,epoch=foundation.EPOCH,python=platform.python_version(),system=platform.system(),machine=platform.machine(),
                    dependency_commits={'equity-features':foundation.CORE_COMMIT,'equity-feature-io':commit},
                    artifacts={p.name:foundation.sha(p) for p in artifacts},dependency_artifacts={p.name:foundation.sha(p) for p in dependencies},source_sha256=tracked,forms=forms)
        (output/'manifest.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('Actual repeat extension archives, both fresh forms/public example/conformance/typing/core invariance PASS')


if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True)
    main()
