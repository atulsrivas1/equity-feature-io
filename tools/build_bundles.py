"""EQ098 closed paired-Git repeat archives and four fresh installed forms per OS."""
from __future__ import annotations
import argparse
import base64
import csv
from email.parser import BytesParser
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/_versions.py, also when loaded by path from tests
from _versions import CONTRACTS, FEATURES, EVIDENCE, OWN

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/bundles'
CORE_HEAD='710fe05b812d4acc06d7e828c96ac1922e3203dc'
EPOCH=1700000000
PACKAGES={'contracts':('equity_feature_contracts',CONTRACTS),
    'features':('equity_features',FEATURES),'evidence':('equity_feature_evidence',EVIDENCE),
    'bundles':('equity_feature_bundles',OWN['equity-feature-bundles'])}


def run(*args, cwd=ROOT, env=None):
    clean = dict(os.environ if env is None else env)
    # Fresh installed typing must not resolve a caller's checkout through
    # mypy/Python search-path configuration. Runtime probes also use -I.
    for name in ('MYPYPATH', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONUSERBASE'):
        clean.pop(name, None)
    subprocess.run([str(a) for a in args], cwd=cwd, env=clean, check=True)


def sha(data): return hashlib.sha256(data).hexdigest()


def contents(path):
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist(); assert len(names) == len(set(names))
            files = {name:archive.read(name) for name in names if not name.endswith('/')}
    else:
        with tarfile.open(path, 'r:gz') as archive:
            members = archive.getmembers(); assert len(members) == len({m.name for m in members})
            assert all(m.isfile() or m.isdir() for m in members)
            files = {m.name:archive.extractfile(m).read() for m in members if m.isfile()}
    for name in files:
        assert not name.startswith(('/', '\\')) and '\\' not in name and '..' not in PurePosixPath(name).parts
        assert not any(p in ('.git','__pycache__','.env') for p in PurePosixPath(name).parts)
        assert not name.endswith(('.pyc','.pyo'))
    return files


def normalize(path):
    raw = io.BytesIO()
    with tarfile.open(path, 'r:gz') as source, tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as target:
        for member in sorted(source.getmembers(), key=lambda m:m.name):
            member.mtime=EPOCH; member.uid=member.gid=0; member.uname=member.gname=''; member.pax_headers={}
            member.mode=0o755 if member.isdir() else 0o644
            target.addfile(member, source.extractfile(member) if member.isfile() else None)
    with path.open('wb') as output, gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=EPOCH) as zipped:
        zipped.write(raw.getvalue())


def inspect(path, name, source):
    module,version = PACKAGES[name]; files = contents(path); wheel=path.suffix=='.whl'
    prefix='' if wheel else path.name.removesuffix('.tar.gz')+'/'
    metadata_name=next(n for n in files if (n.endswith('/METADATA') if wheel else n==prefix+'PKG-INFO'))
    metadata=BytesParser().parsebytes(files[metadata_name])
    assert metadata['Name']==module.replace('_','-') and metadata['Version']==version
    assert metadata['License-Expression']=='Apache-2.0' and metadata['Requires-Python']=='<3.13,>=3.12'
    if name=='bundles':
        assert metadata.get_all('Requires-Dist',[])==[f'equity-feature-contracts=={CONTRACTS}',f'equity-feature-evidence=={EVIDENCE}',f'equity-features=={FEATURES}; extra == \"replay\"']
        assert metadata.get_all('Provides-Extra',[])==['replay']
    if name=='evidence': assert metadata.get_all('Requires-Dist',[])==[f'equity-feature-contracts=={CONTRACTS}']
    package_prefix=module+'/' if wheel else prefix+'src/'+module+'/'
    expected={p.relative_to(source/'src').as_posix():p.read_bytes() for p in (source/'src'/module).rglob('*') if p.is_file()}
    actual={module+'/'+n.removeprefix(package_prefix):body for n,body in files.items() if n.startswith(package_prefix)}
    assert actual==expected and module+'/py.typed' in actual
    license_name=next(n for n in files if n.endswith('/licenses/LICENSE')) if wheel else prefix+'LICENSE'
    assert files[license_name]==(source/'LICENSE').read_bytes()
    if wheel:
        assert all(n.startswith((module+'/',module+'-')) for n in files)
        record=next(n for n in files if n.endswith('/RECORD'))
        rows=list(csv.reader(io.StringIO(files[record].decode('utf-8'))))
        assert len(rows)==len(files) and {r[0] for r in rows}==set(files)
        for relative,digest,size in rows:
            if relative==record: assert digest==size==''
            else:
                assert digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(files[relative]).digest()).rstrip(b'=').decode()
                assert int(size)==len(files[relative])
    else:
        allowed={prefix+n for n in ('LICENSE','README.md','pyproject.toml','PKG-INFO','setup.cfg')}
        assert all(n in allowed or n.startswith((prefix+'src/'+module+'/',prefix+'src/'+module+'.egg-info/')) for n in files)
        assert files[prefix+'pyproject.toml']==(source/'pyproject.toml').read_bytes()
    return {'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size,'version':version,
            'entries':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in sorted(files.items())},
            'source_map':{n:sha(b) for n,b in sorted(expected.items())},'record_verified':wheel}


def installed_map(py, names):
    script='''import hashlib,importlib,json,sys
from pathlib import Path
from importlib.metadata import distribution
result={}
for name in sys.argv[1:]:
    module=importlib.import_module(name); root=Path(module.__file__).resolve().parent
    assert 'site-packages' in root.parts
    for relative in distribution(name.replace('_','-')).files:
        path=Path(distribution(name.replace('_','-')).locate_file(relative)).resolve()
        if path.is_file() and '__pycache__' not in path.parts:
            assert 'site-packages' in path.parts
            result[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(result,sort_keys=True))
'''
    return json.loads(subprocess.check_output([str(py),'-I','-c',script,*names],cwd=py.parent,encoding='utf-8'))


def verify_installed(mapping, paths):
    expected={}
    for path in paths:
        module=path.name.split('-')[0]
        files=contents(path)
        prefix=module+'/' if path.suffix=='.whl' else path.name.removesuffix('.tar.gz')+'/src/'+module+'/'
        expected.update({module+'/'+n.removeprefix(prefix):sha(b) for n,b in files.items() if n.startswith(prefix)})
    modules=tuple(module for module,version in PACKAGES.values())
    actual={n:digest for n,digest in mapping.items() if any(n.startswith(module+'/') for module in modules)}
    assert actual==expected, 'installed source/archive complete payload differs'


def install(paths, directory):
    run(sys.executable,'-m','venv',directory)
    py=directory/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if paths[0].suffix!='.whl': run(py,'-m','pip','install','--no-deps','setuptools==80.9.0')
    run(py,'-m','pip','install','--no-index','--no-deps','--no-build-isolation',*paths)
    run(py,'-m','pip','check')
    return py


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--core-root',required=True,type=Path)
    args=parser.parse_args()
    core=args.core_root.resolve()
    assert core!=ROOT.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    assert not list(OUT.iterdir()), 'fresh dist/bundles required; preserve prior qualification'
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=core,encoding='utf-8').strip()==CORE_HEAD
    own_scopes=['packages/bundles','tests/bundles','tests/fixtures/bundle_oracle.json',
        'examples/bundles_consumer.py','tools/build_bundles.py','tools/check_bundles.py',
        '.github/workflows/bundles.yml','requirements-dev.txt']
    core_scopes=['packages/contracts','packages/features','packages/evidence']
    snapshots={}; materialized={}; identities={}; inventories={}
    roots={'canonical':(core,CORE_HEAD,core_scopes),'companion':(ROOT,head,own_scopes)}
    for label,(root,commit,scopes) in roots.items():
        paths=tuple(subprocess.check_output(['git','ls-files','--',*scopes],cwd=root,encoding='utf-8').splitlines())
        assert paths
        inventories[label]=paths
        for name in paths:
            data=subprocess.check_output(['git','show',commit+':'+name],cwd=root)
            live=(root/name).read_bytes()
            assert live==data or live.replace(b'\r\n',b'\n')==data, 'uncommitted build input'
            key=label+'/'+name
            snapshots[key]=data; materialized[key]=live
            identities[key]={'git_sha256':sha(data),'materialized_sha256':sha(live),'built_from':'committed-Git-bytes'}
    def closure():
        for label,(root,commit,scopes) in roots.items():
            assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,encoding='utf-8').strip()==commit
            assert tuple(subprocess.check_output(['git','ls-files','--',*scopes],cwd=root,encoding='utf-8').splitlines())==inventories[label]
            assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*scopes],cwd=root)
            assert all((root/name).read_bytes()==materialized[label+'/'+name] for name in inventories[label])
    report={'schema':'bundle-qualification:1','source_commit':head,'canonical_dependency':CORE_HEAD,
        'system':platform.system(),'python':platform.python_version(),'source':identities,
        'artifacts':{},'installed':[],'status':'running','epoch':EPOCH}
    def save(): (OUT/'qualification.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    closure(); save()
    work=ROOT/'work'; work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bundles-',dir=work) as owned:
        owned=Path(owned).resolve(); assert owned.is_relative_to(work.resolve())
        verification=owned/'verification'
        for key,data in snapshots.items():
            target=verification/key; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
        component=verification/'companion'
        env=dict(os.environ,SOURCE_DATE_EPOCH=str(EPOCH),PYTHONHASHSEED='0')
        for repeat in (0,1):
            dest=owned/f'build-{repeat}'; dest.mkdir()
            for name,(module,_) in PACKAGES.items():
                source=owned/f'source-{repeat}-{name}'
                prefix=('companion' if name=='bundles' else 'canonical')+'/packages/'+name+'/'
                for key,data in snapshots.items():
                    if key.startswith(prefix):
                        target=source/key.removeprefix(prefix); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
                run(sys.executable,'-m','build','--no-isolation','--outdir',dest,source,env=env)
                artifacts=list(dest.glob(module+'-*')); assert len(artifacts)==2
                for path in artifacts:
                    if path.suffix!='.whl': normalize(path)
                    inspection=inspect(path,name,source)
                    if repeat==0:
                        report['artifacts'][path.name]=inspection; shutil.copyfile(path,OUT/path.name)
                    else: assert inspection==report['artifacts'][path.name], 'repeat archive differs'
        assert len(report['artifacts'])==8; report['repeat_archive_parity']=True; save()
        for form,suffix in [('wheel','.whl'),('sdist','.tar.gz')]:
            archives={n:next(OUT.glob(module+'-*'+suffix)) for n,(module,_) in PACKAGES.items()}
            for combined in (False,True):
                baseline=['contracts','evidence']+(['features'] if combined else [])
                selected=[archives[n] for n in baseline]
                py=install(selected,owned/(form+('-replay' if combined else '-light')))
                before=installed_map(py,[PACKAGES[n][0] for n in baseline]); verify_installed(before,selected)
                run(py,'-m','pip','install','--no-index','--no-deps','--no-build-isolation',archives['bundles'])
                run(py,'-m','pip','check')
                modules=[PACKAGES[n][0] for n in baseline]+['equity_feature_bundles']
                after=installed_map(py,modules); verify_installed(after,[*selected,archives['bundles']])
                assert all(after[n]==digest for n,digest in before.items())
                probe="""import base64,importlib.util,json,sys
from pathlib import Path
from equity_feature_bundles import read_bundle,write_bundle
from equity_feature_bundles.replay import replay_bundle
fixture=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
raw=base64.b64decode(fixture['archive_base64']); b=read_bundle(raw)
assert write_bundle(b.receipt,b.configuration,b.result,tuple((x.role,x.batch) for x in b.inputs),b.manifest.publication)==raw
assert all(importlib.util.find_spec(n) is None for n in ('equity_feature_io_sdk','equity_feature_workers','equity_feature_strategies','equity_feature_labels','numpy','pyarrow'))
if sys.argv[2]=='light':
    assert importlib.util.find_spec('equity_features') is None
    report=replay_bundle(b)
    assert report.status=='incompatible' and report.calculation_count==0
    assert 'equity_features' not in sys.modules
else:
    report=replay_bundle(b)
    assert report.status=='matched' and report.calculation_count==1 and report.result_match is True
assert report.declared_environment_verified is False
print('Installed known-byte archive and actual optional replay behavior passed.')
"""
                run(py,'-I','-c',probe,component/'tests/fixtures/bundle_oracle.json','replay' if combined else 'light',cwd=py.parent)
                run(py,'-I','-m','unittest','discover','-s',component/'tests/bundles',cwd=py.parent)
                if combined: run(py,'-I',component/'examples/bundles_consumer.py',cwd=py.parent)
                typing=py.parent/'bundles_typed_consumer.py'
                typing.write_text("from equity_feature_bundles import ReproductionBundle,ReplayReport,read_bundle\nfrom equity_feature_bundles.replay import replay_bundle\ndef use(raw: bytes) -> ReplayReport:\n    bundle: ReproductionBundle = read_bundle(raw)\n    return replay_bundle(bundle)\n",encoding='utf-8')
                run(sys.executable,'-m','mypy','--strict','--python-executable',py,typing,cwd=py.parent)
                assert after==installed_map(py,modules)
                report['installed'].append({'form':form,'combined_actual_core_producer':combined,
                    'optional_independence':not combined,'installed_map':after,'unchanged_original_packages':True,
                    'tests_passed':True,'typing_passed':True}); save()
    closure(); report['source_head_and_materialization_closure']=True; report['status']='completed'; save()


if __name__=='__main__': main()
