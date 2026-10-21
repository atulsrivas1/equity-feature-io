"""Explicit source origins and bounded focused suite; no implicit producer execution."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--core-root', type=Path, required=True)
parser.add_argument('--pattern', default='test_regular_first_trade_price_inputs.py')
parser.add_argument('--test-name')
parser.add_argument('--test-root', type=Path, default=root/'tests/ef1')
parser.add_argument('--allow-producer', action='store_true')
parser.add_argument('--failfast', action='store_true')
args = parser.parse_args()
core = args.core_root.resolve(strict=True)
selected = {'equity_feature_contracts': core/'packages/contracts/src',
    'equity_feature_duckdb': root/'packages/duckdb/src',
    'equity_feature_io_contracts': root/'packages/io-contracts/src',
    'equity_feature_io_sdk': root/'packages/io-sdk/src',
    'equity_feature_duckdb_sink': root/'packages/duckdb-sink/src'}
if args.allow_producer:
    selected['equity_features'] = core/'packages/features/src'
for path in reversed(tuple(selected.values())):
    sys.path.insert(0, str(path))
sys.path.insert(0, str(root/'tests/ef1'))
sys.dont_write_bytecode = True
for name, source in selected.items():
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(source), (name, module.__file__)
    print(name, module.__file__, flush=True)
suite = (unittest.defaultTestLoader.loadTestsFromName(args.test_name) if args.test_name else
    unittest.defaultTestLoader.discover(str(args.test_root), pattern=args.pattern))
result = unittest.TextTestRunner(verbosity=2, failfast=args.failfast).run(suite)
origins = {}
for name, module in tuple(sys.modules.items()):
    if not args.allow_producer:
        assert name != 'equity_features' and not name.startswith('equity_features.'), name
    for prefix, source in selected.items():
        if name == prefix or name.startswith(prefix+'.'):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(source), (name, path)
            origins[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
print(json.dumps({'loaded_origins': origins, 'producer_authorized': args.allow_producer}, sort_keys=True), flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
