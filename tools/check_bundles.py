"""Static bundle boundary and closed typed registry checks; no runtime acquisition."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/bundles/src/equity_feature_bundles'
ALLOWED = {'__future__', 'collections', 'contextlib', 'dataclasses', 'hashlib',
    'importlib', 'json', 'math', 're', 'struct', 'time', 'typing', 'zlib',
    'equity_feature_contracts', 'equity_feature_evidence'}


def main():
    for path in SOURCE.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.level: continue
                names = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                for name in names:
                    assert name is not None
                    root = name.split('.')[0]
                    if root == 'equity_features':
                        assert path.name == 'replay.py' and isinstance(node, ast.ImportFrom) and name == 'equity_features.session'
                        assert [a.name for a in node.names] == ['compute_trades']
                    else: assert root in ALLOWED, (path, name)
                    if root in ('time', 'importlib'): assert path.name == 'replay.py'
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in ('eval','exec','getattr','setattr','__import__','open','compile','globals','locals','vars')
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in ('extract','extractall','load_module','import_module','loads_pickle','system','popen')
    tree=ast.parse((SOURCE/'_typed.py').read_text(encoding='utf-8'))
    tags=[n.comparators[0].value for n in ast.walk(tree) if isinstance(n,ast.Compare)
        and isinstance(n.left,ast.Name) and n.left.id=='tag' and isinstance(n.comparators[0],ast.Constant)]
    assert len(tags)==len(set(tags))==35
    assert len(list(SOURCE.glob('*.py')))==9
    print('Bundle imports, no extraction/executable hooks and 35 fixed typed branches passed.')


if __name__=='__main__': main()
