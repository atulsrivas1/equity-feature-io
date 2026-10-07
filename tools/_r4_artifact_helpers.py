"""Preserved R4 artifact inspection helpers; installed core remains canonical."""
import gzip,hashlib,io,json,os,platform,subprocess,sys,tarfile,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EPOCH=1700000000

def normalize_sdist(path):
    with tarfile.open(path,'r:gz') as src:
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w',format=tarfile.PAX_FORMAT) as dst:
            for member in sorted(src.getmembers(),key=lambda x:x.name):
                member.mtime=EPOCH;member.uid=member.gid=0;member.uname=member.gname=''
                member.pax_headers={};member.mode=0o755 if member.isdir() else 0o644
                dst.addfile(member,src.extractfile(member) if member.isfile() else None)
    with path.open('wb') as output:
        with gzip.GzipFile(fileobj=output,mode='wb',filename='',mtime=EPOCH) as out:
            out.write(data.getvalue())

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect(path):
    consumer=path.name.startswith('equity_feature_demo-')
    package='equity_feature_demo' if consumer else 'equity_feature_contracts' if 'contracts' in path.name else 'equity_features'
    if path.suffix=='.whl':
        with zipfile.ZipFile(path) as z: files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
        assert all(n.startswith((package+'/',package+'-')) for n in files),files.keys()
        assert package+'/py.typed' in files
        metadata=next(v for k,v in files.items() if k.endswith('/METADATA'))
        assert b'License-Expression: Apache-2.0' in metadata
        assert any(k.endswith('/licenses/LICENSE') for k in files)
    else:
        with tarfile.open(path,'r:gz') as t:
            assert not any(m.issym() or m.islnk() for m in t.getmembers())
            files={m.name:t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
        assert any(k.endswith('/src/'+package+'/py.typed') for k in files)
        assert any(k.endswith('/LICENSE') for k in files)
        assert any(k.endswith('/pyproject.toml') for k in files)
        if consumer:
            prefix=path.name.removesuffix('.tar.gz')+'/'
            assert all(n.startswith((prefix+'src/'+package+'/',prefix+'src/'+package+'.egg-info/')) or n in {prefix+x for x in ('LICENSE','PKG-INFO','pyproject.toml','setup.cfg')} for n in files),files.keys()
    for name,content in files.items():
        assert not name.startswith(('/','\\')) and '..' not in Path(name).parts,name
        assert not any(x in name for x in ['__pycache__','.pyc','.env','fixtures','work/']),name
        assert b'C:\\Users\\' not in content and b'/home/runner/' not in content,name

def core_fingerprint(py):
    """Actual installed core bytes before and after independent installation."""
    code='''import hashlib,json
from importlib.metadata import distribution
from pathlib import Path
import equity_features as f,equity_feature_contracts as c
roots=(Path(f.__file__).parent,Path(c.__file__).parent)
assert all('site-packages' in root.parts for root in roots)
result={root.name+'/'+p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for root in roots for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
for name in ('equity-features','equity-feature-contracts'):
    dist=distribution(name)
    for relative in dist.files:
        path=Path(dist.locate_file(relative)).resolve()
        assert 'site-packages' in path.parts
        if '__pycache__' not in path.parts and path.is_file():result[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(result,sort_keys=True))
'''
    return json.loads(subprocess.check_output([str(py),'-I','-c',code],text=True,cwd=ROOT))
