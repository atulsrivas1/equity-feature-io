"""Committed repeat builds and fresh native wheel/sdist files qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

from build_foundation import build, fingerprint, git, inspect, install, run, sha, snapshot

ROOT = Path(__file__).resolve().parents[1]
CORE = '9a180da540a426d9cefb3edb34fc81c26a9bd5d9'
PATHS = ('packages/files','packages/acquisition','packages/io-contracts','packages/io-sdk',
         'tests/files','tests/file_goldens.json','tests/files_probe.py','examples/files_consumer.py',
         'tools/build_files.py','tools/build_foundation.py','requirements-dev.txt','.github/workflows/files.yml')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core-root',required=True,type=Path)
    core=parser.parse_args().core_root.resolve()
    assert git(core,'rev-parse',CORE)==CORE
    head=git(ROOT,'rev-parse','HEAD')
    assert not git(ROOT,'status','--porcelain','--',*PATHS), 'Freeze source before qualification'
    output=ROOT/'dist-files';output.mkdir(exist_ok=True)
    assert not list(output.iterdir()), 'Use fresh output'
    with tempfile.TemporaryDirectory(prefix='files-build-',dir=ROOT/'work') as temporary:
        stage=Path(temporary)
        component=snapshot(ROOT,head,stage/'component',PATHS)
        # Freeze committed inputs before setuptools creates build/egg-info files.
        source_bytes={}
        for relative in PATHS:
            path=component/relative
            for entry in sorted(path.rglob('*')) if path.is_dir() else [path]:
                if entry.is_file():source_bytes[str(entry.relative_to(component)).replace('\\','/')]=sha(entry)
        committed=set(git(ROOT,'ls-tree','-r','--name-only',head,'--',*PATHS).splitlines())
        assert set(source_bytes)==committed
        canonical=snapshot(core,CORE,stage/'core',('packages/contracts','packages/features'))
        dependencies=stage/'deps'
        for folder in ('contracts','features'):build(canonical/'packages'/folder,dependencies)
        for folder in ('io-contracts','io-sdk','acquisition'):build(component/'packages'/folder,dependencies)
        first,repeat=stage/'first',stage/'repeat'
        for target in (first,repeat):build(component/'packages/files',target)
        archives=sorted(first.iterdir());assert len(archives)==2
        for archive in archives:
            assert sha(archive)==sha(repeat/archive.name),'Nonrepeatable acquisition archive'
            inspect(archive,'equity-feature-files',[
                'equity-feature-acquisition==0.1.0a0','equity-feature-io-sdk==0.1.0a2',
                'pyarrow==20.0.0; extra == "parquet"','databento-dbn==0.70.0; extra == "dbn"',
                'pyarrow==20.0.0; extra == "full"','databento-dbn==0.70.0; extra == "full"'])
        deps=sorted(dependencies.glob('*.whl'));assert len(deps)==5
        forms=[]
        for form in ('wheel','sdist'):
            with tempfile.TemporaryDirectory(prefix='files-install-',dir=ROOT/'work') as isolated:
                cwd=Path(isolated)
                run(sys.executable,'-m','venv',cwd)
                py=cwd/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
                run(py,'-m','pip','install','--no-deps','setuptools==80.9.0','mypy==1.15.0',
                    'mypy_extensions==1.1.0','typing_extensions==4.16.0')
                pure=[p for p in deps if p.name.startswith(('equity_feature_contracts-','equity_features-'))]
                install(py,pure);before=fingerprint(py,cwd)
                selected=[p for p in archives if (p.suffix=='.whl')==(form=='wheel')]
                install(py,[p for p in deps if p not in pure]+selected)
                run(py,'-m','pip','check',cwd=cwd)
                for relative in ('tests/files','tests/file_goldens.json','examples/files_consumer.py'):
                    source=component/relative;target=cwd/relative
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if source.is_dir():shutil.copytree(source,target)
                    else:shutil.copy2(source,target)
                report=cwd/'report.json'
                light=cwd/'light.json'
                run(py,'-I',component/'tests/files_probe.py',cwd,light,'light',cwd=cwd)
                run(py,'-m','pip','install','--no-deps','pyarrow==20.0.0','databento-dbn==0.70.0')
                run(py,'-m','pip','check',cwd=cwd)
                run(py,'-I',component/'tests/files_probe.py',cwd,report,'full',cwd=cwd)
                after=fingerprint(py,cwd);assert before==after and len(before)==61
                public=json.loads(report.read_text());assert public['tests_run']==43
                fp=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
                public.update({'light':json.loads(light.read_text()),'form':form,'source_commit':head,'core_before_sha256':fp,'core_after_sha256':fp})
                forms.append(public)
        assert git(ROOT,'rev-parse','HEAD')==head
        assert not git(ROOT,'status','--porcelain','--',*PATHS)
        for archive in archives+deps:shutil.copy2(archive,output/archive.name)
        record={'schema':'files1','commit':head,'core_commit':CORE,'source_dirty':False,
            'python':platform.python_version(),'system':platform.system(),
            'archives':{p.name:sha(p) for p in archives+deps},'source_sha256':source_bytes,'forms':forms}
        (output/'manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Repeat files archives, default/light and full fresh wheel/sdist,43 independent tests per form,61 core files invariant PASS')


if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True)
    main()
