"""Repeat optional adapter/core artifacts and qualify both installed forms."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from _r4_artifact_helpers import EPOCH, core_fingerprint, digest, inspect, normalize_sdist
from build_foundation import snapshot

ROOT = Path(__file__).resolve().parents[1]
CORE_COMMIT = "2cd51cd35c0a3081f88e1752c7c1c41ffe0e62af"


def run(*args, cwd=ROOT, **kwargs):
    subprocess.run(args, check=True, cwd=cwd, **kwargs)


def inspect_adapter(path):
    package = 'equity_feature_duckdb'
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            files = {n: archive.read(n) for n in archive.namelist() if not n.endswith('/')}
        assert all(n.startswith((package+'/', package+'-')) for n in files)
        assert package+'/py.typed' in files
        meta = next(v for n,v in files.items() if n.endswith('/METADATA'))
        assert b'License-Expression: Apache-2.0' in meta
        assert b'Requires-Dist: duckdb==1.5.6' in meta
        assert b'Requires-Dist: numpy==2.2.6' in meta
        assert b'Requires-Dist: equity-feature-contracts==0.0.4a4' in meta
        assert any(n.endswith('/licenses/LICENSE') for n in files)
    else:
        with tarfile.open(path,'r:gz') as archive:
            assert not any(m.issym() or m.islnk() for m in archive.getmembers())
            files = {m.name: archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
        prefix = path.name.removesuffix('.tar.gz')+'/'
        allowed = {prefix+x for x in ('LICENSE','PKG-INFO','README.md','pyproject.toml','setup.cfg')}
        assert all(n.startswith((prefix+'src/'+package+'/',prefix+'src/'+package+'.egg-info/')) or n in allowed for n in files)
        assert prefix+'src/'+package+'/py.typed' in files
    for name, content in files.items():
        assert not name.startswith(('/','\\')) and '..' not in Path(name).parts
        assert not any(x in name for x in ('__pycache__','.pyc','.env','fixtures','work/'))
        assert not any(x in content for x in (b'C:\\Users\\',b'N:/',b'/home/runner/',b'Monikasrivas1'))


def qualify(output, form, source_commit):
    work = ROOT/'work/duckdb-installs'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        env = Path(tmp).resolve()
        run(sys.executable,'-m','venv',str(env))
        py = env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        paths = sorted(p for p in output.glob('equity_feature_contracts-*') if (p.suffix=='.whl')==(form=='whl'))
        paths += sorted(p for p in output.glob('equity_features-*') if (p.suffix=='.whl')==(form=='whl'))
        assert len(paths)==2
        if form=='gz':run(str(py),'-m','pip','install','--no-deps','setuptools==80.9.0')
        run(str(py),'-m','pip','install','--no-index','--no-deps','--no-build-isolation',*[str(p) for p in paths])
        run(str(py),'-I','-c',"import importlib.util; assert importlib.util.find_spec('duckdb') is None; import equity_features,equity_feature_contracts; print('Installed pure core imports without DuckDB')",cwd=env)
        before = core_fingerprint(py)
        adapter = next(p for p in output.glob('equity_feature_duckdb-*') if (p.suffix=='.whl')==(form=='whl'))
        run(str(py),'-m','pip','install','--no-deps','duckdb==1.5.6','numpy==2.2.6')
        run(str(py),'-m','pip','install','--no-index','--no-deps','--no-build-isolation',str(adapter))
        run(str(py),'-m','pip','check')
        assert before==core_fingerprint(py),'adapter installation changed installed core'
        old_env = env/'old-installed'
        run(sys.executable,'-m','venv',str(old_env))
        old_py = old_env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if form=='gz':run(str(old_py),'-m','pip','install','--no-deps','setuptools==80.9.0')
        old_adapter = next(p for p in (ROOT/'work/duckdb-baseline').glob('equity_feature_duckdb-*') if (p.suffix=='.whl')==(form=='whl'))
        run(str(old_py),'-m','pip','install','--no-deps','duckdb==1.5.6','numpy==2.2.6')
        run(str(old_py),'-m','pip','install','--no-index','--no-deps','--no-build-isolation',*[str(p) for p in paths],str(old_adapter))
        run(str(old_py),'-m','pip','check')
        compatibility_path=output/f'compatibility-{platform.system()}-{form}.json'
        run(sys.executable,str(ROOT/'tools/check_compatibility.py'),'--old-python',str(old_py),
            '--new-python',str(py),'--output',str(compatibility_path))
        compatibility=json.loads(compatibility_path.read_text())
        compatibility.update(system=platform.system(),form=form,core_source_commit=CORE_COMMIT,
            old_adapter_artifact={old_adapter.name:digest(old_adapter)},new_artifacts={p.name:digest(p) for p in [*paths,adapter]})
        compatibility_path.write_text(json.dumps(compatibility,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        run(str(py),'-I','-c',"from pathlib import Path; import equity_feature_duckdb as d,duckdb,numpy; assert 'site-packages' in Path(d.__file__).parts; assert d.__version__=='0.1.0a8'; assert duckdb.__version__=='1.5.6'; assert numpy.__version__=='2.2.6'",cwd=env)
        result=subprocess.run([str(py),'-I','-m','unittest','discover','-s',str(ROOT/'tests/duckdb')],cwd=env,text=True,capture_output=True)
        print(result.stdout+result.stderr)
        result.check_returncode()
        count=int(re.search(r'Ran (\d+) tests',result.stderr).group(1))
        run(str(py),'-I',str(ROOT/'benchmarks/duckdb_read.py'),'--quick',
            '--output',str(output/f'read-{platform.system()}-{form}.json'),cwd=env)
        conformance_path=output/f'conformance-{platform.system()}-{form}.json'
        run(str(py),'-I',str(ROOT/'examples/duckdb_conformance.py'),'--installed',
            '--output',str(conformance_path),cwd=env)
        conformance=json.loads(conformance_path.read_text(encoding='utf-8'))
        assert conformance['installed_public_execution'] and len(conformance['cases'])==30
        assert all(c['passed'] and c['expected']==c['observed'] for c in conformance['cases'])
        assert len(conformance['numerical'])==16 and conformance['independent_numerical_unit_quality_binding_parity']
        conformance.update(form=form,artifacts={p.name:digest(p) for p in [*paths,adapter]})
        conformance_path.write_bytes((json.dumps(conformance,sort_keys=True,indent=2)+'\n').encode('utf-8'))
        run(str(py),'-m','pip','install','--no-deps','mypy==1.15.0','mypy_extensions==1.1.0','typing_extensions==4.16.0')
        run(str(py),'-I','-m','mypy','--strict','-p','equity_feature_duckdb',cwd=env)
        run(str(py),'-I','-m','mypy','--strict',str(ROOT/'examples/duckdb_conformance.py'),cwd=env)
        run(str(py),'-I','-c',"""import sys
class Deny:
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='duckdb' or fullname.startswith('duckdb.'):raise RuntimeError('core attempted DuckDB import')
sys.meta_path.insert(0,Deny())
import equity_feature_contracts,equity_features
from equity_features.registry import builtin_registry
assert len(builtin_registry().list_features())==39
print('Pure core registry executes with DuckDB forbidden')
""",cwd=env)
        after = core_fingerprint(py)
        assert before==after,'adapter execution changed installed core'
        fingerprint = lambda x: hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
        report = dict(schema='duckdb-install1',source_commit=source_commit,
                      form=form,system=platform.system(),python=platform.python_version(),duckdb='1.5.6',numpy='2.2.6',adapter='0.1.0a8',
                      artifacts={p.name:digest(p) for p in [*paths,adapter]},synthetic_tests=count,
                      test_suite_sha256=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'tests/duckdb').glob('test_*.py')))).hexdigest(),
                      before_core_sha256=fingerprint(before),after_core_sha256=fingerprint(after),
                      installed_public_execution=True,core_without_duckdb=True,real_data_qualified=False)
        (output/f'installed-{platform.system()}-{form}.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--core-root',type=Path,required=True)
    args=parser.parse_args()
    assert not subprocess.check_output(['git','status','--porcelain','--','packages','tools','tests','examples','benchmarks','requirements-duckdb.txt'],cwd=ROOT,text=True).strip(), 'Freeze extraction sources before qualification'
    work=ROOT/'work';work.mkdir(exist_ok=True)
    staging=tempfile.TemporaryDirectory(prefix='source-',dir=work)
    source_root=Path(staging.name)
    run(sys.executable,str(ROOT/'tools/check_extraction.py'),'--core-root',str(args.core_root.resolve()))
    core=snapshot(args.core_root.resolve(),CORE_COMMIT,source_root/'core',('packages/contracts','packages/features','packages/duckdb'))
    component_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    component=snapshot(ROOT,component_commit,source_root/'component',('packages/duckdb',))
    output=ROOT/'dist/duckdb';repeat=ROOT/'work/duckdb-repeat'
    build_env=dict(os.environ,SOURCE_DATE_EPOCH=str(EPOCH))
    baseline=ROOT/'work/duckdb-baseline'
    baseline.mkdir(parents=True,exist_ok=True)
    for old in baseline.glob('equity_feature_duckdb-*'):
        assert old.is_file()
        old.unlink()
    run(sys.executable,'-m','build','--no-isolation','--outdir',str(baseline),str(core/'packages/duckdb'),env=build_env)
    for path in baseline.glob('*.tar.gz'):normalize_sdist(path)
    for out in (output,repeat):
        assert out.resolve().is_relative_to(ROOT.resolve())
        out.mkdir(parents=True,exist_ok=True)
        for pattern in ('equity_feature_duckdb-*','equity_feature_contracts-*','equity_features-*','installed-*.json','read-*.json','conformance-*.json','compatibility-*.json','manifest.json'):
            for old in out.glob(pattern):
                assert old.is_file()
                old.unlink()
        for source in ('contracts','features','duckdb'):
            run(sys.executable,'-m','build','--no-isolation','--outdir',str(out),str((component if source=='duckdb' else core)/'packages'/source),env=build_env)
        for path in out.glob('*.tar.gz'):normalize_sdist(path)
    paths=sorted([*output.glob('*.whl'),*output.glob('*.tar.gz')])
    assert len(paths)==6
    for path in paths:
        assert digest(path)==digest(repeat/path.name),'repeat artifact mismatch'
        (inspect_adapter if path.name.startswith('equity_feature_duckdb-') else inspect)(path)
    qualify(output,'whl',component_commit);qualify(output,'gz',component_commit)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==component_commit, 'Source head changed during qualification'
    assert not subprocess.check_output(['git','status','--porcelain','--','packages','tools','tests','examples','benchmarks','requirements-duckdb.txt'],cwd=ROOT,text=True).strip(), 'Sources changed during qualification'
    manifest=dict(schema='duckdb-build1',commit=component_commit,
                  source_dirty=bool(subprocess.check_output(['git','status','--porcelain','--','packages','tools/build_duckdb.py','tests/duckdb','benchmarks/duckdb_read.py','examples/duckdb_conformance.py'],cwd=ROOT,text=True).strip()),
                  system=platform.system(),python=platform.python_version(),epoch=EPOCH,
                  core_source_commit=CORE_COMMIT,
                  artifacts={p.name:digest(p) for p in paths})
    (output/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    staging.cleanup()
    print('Six committed-source repeat archives; actual installed94cases/SDK30numeric16/core invariance passed.')


if __name__=='__main__':main()
