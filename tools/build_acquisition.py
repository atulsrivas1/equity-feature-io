"""Committed repeat builds and fresh native wheel/sdist acquisition qualification."""
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
CORE = '4689892117bdf70ef47726c1dee754e3e23b0658'
PATHS = ('packages/acquisition','packages/io-contracts','tests/acquisition',
         'tests/acquisition_goldens.json','tests/acquisition_probe.py',
         'examples/acquisition_consumer.py','tools/build_acquisition.py',
         'tools/build_foundation.py','requirements-dev.txt','.github/workflows/acquisition.yml')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core-root',required=True,type=Path)
    core=parser.parse_args().core_root.resolve()
    assert git(core,'rev-parse',CORE)==CORE
    head=git(ROOT,'rev-parse','HEAD')
    assert not git(ROOT,'status','--porcelain','--',*PATHS), 'Freeze source before qualification'
    output=ROOT/'dist-acquisition';output.mkdir(exist_ok=True)
    assert not list(output.iterdir()), 'Use fresh output'
    with tempfile.TemporaryDirectory(prefix='acquisition-build-',dir=ROOT/'work') as temporary:
        stage=Path(temporary)
        component=snapshot(ROOT,head,stage/'component',PATHS)
        canonical=snapshot(core,CORE,stage/'core',('packages/contracts','packages/features'))
        dependencies=stage/'deps'
        for folder in ('contracts','features'):build(canonical/'packages'/folder,dependencies)
        build(component/'packages/io-contracts',dependencies)
        first,repeat=stage/'first',stage/'repeat'
        for target in (first,repeat):build(component/'packages/acquisition',target)
        archives=sorted(first.iterdir());assert len(archives)==2
        for archive in archives:
            assert sha(archive)==sha(repeat/archive.name),'Nonrepeatable acquisition archive'
            inspect(archive,'equity-feature-acquisition',['equity-feature-io-contracts==0.1.0a2'])
        deps=sorted(dependencies.glob('*.whl'));assert len(deps)==3
        forms=[]
        for form in ('wheel','sdist'):
            with tempfile.TemporaryDirectory(prefix='acquisition-install-',dir=ROOT/'work') as isolated:
                cwd=Path(isolated)
                run(sys.executable,'-m','venv',cwd)
                py=cwd/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
                run(py,'-m','pip','install','--no-deps','setuptools==80.9.0','mypy==1.15.0',
                    'mypy_extensions==1.1.0','typing_extensions==4.16.0')
                pure=[p for p in deps if not p.name.startswith('equity_feature_io_contracts-')]
                install(py,pure);before=fingerprint(py,cwd)
                selected=[p for p in archives if (p.suffix=='.whl')==(form=='wheel')]
                install(py,[p for p in deps if p not in pure]+selected)
                run(py,'-m','pip','check',cwd=cwd)
                for relative in ('tests/acquisition','tests/acquisition_goldens.json','examples/acquisition_consumer.py'):
                    source=component/relative;target=cwd/relative
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if source.is_dir():shutil.copytree(source,target)
                    else:shutil.copy2(source,target)
                report=cwd/'report.json'
                run(py,'-I',component/'tests/acquisition_probe.py',cwd,report,cwd=cwd)
                after=fingerprint(py,cwd);assert before==after and len(before)==61
                public=json.loads(report.read_text());assert public['tests_run']==29
                fp=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
                public.update({'form':form,'source_commit':head,'core_before_sha256':fp,'core_after_sha256':fp})
                forms.append(public)
        assert git(ROOT,'rev-parse','HEAD')==head
        assert not git(ROOT,'status','--porcelain','--',*PATHS)
        source_bytes={}
        for relative in PATHS:
            path=component/relative
            for entry in sorted(path.rglob('*')) if path.is_dir() else [path]:
                if entry.is_file():source_bytes[str(entry.relative_to(component)).replace('\\','/')]=sha(entry)
        for archive in archives+deps:shutil.copy2(archive,output/archive.name)
        record={'schema':'acquisition1','commit':head,'core_commit':CORE,'source_dirty':False,
            'python':platform.python_version(),'system':platform.system(),
            'archives':{p.name:sha(p) for p in archives+deps},'source_sha256':source_bytes,'forms':forms}
        (output/'manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Repeat acquisition archives, fresh wheel/sdist,29 independent tests per form,61 core files invariant PASS')


if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True)
    main()
