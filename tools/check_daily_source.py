import argparse, importlib, pathlib, sys, unittest
root=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--core-root',type=pathlib.Path,required=True)
parser.add_argument('--pattern',default='test_daily_observations_inputs.py')
parser.add_argument('--test-name')
parser.add_argument('--test-root',type=pathlib.Path,default=root/'tests/ef1')
args=parser.parse_args()
core=args.core_root.resolve(strict=True)
selected={
 'equity_feature_contracts':core/'packages/contracts/src',
 'equity_features':core/'packages/features/src',
 'equity_feature_duckdb':root/'packages/duckdb/src',
 'equity_feature_io_contracts':root/'packages/io-contracts/src',
 'equity_feature_io_sdk':root/'packages/io-sdk/src',
 'equity_feature_duckdb_sink':root/'packages/duckdb-sink/src',
}
for p in reversed(tuple(selected.values())): sys.path.insert(0,str(p))
sys.path.insert(0,str(root/'tests/ef1'))
sys.dont_write_bytecode=True
for name,source in selected.items():
 m=importlib.import_module(name)
 assert pathlib.Path(m.__file__).resolve().is_relative_to(source)
 print(name,m.__file__,flush=True)
suite=unittest.defaultTestLoader.loadTestsFromName(args.test_name) if args.test_name else unittest.defaultTestLoader.discover(str(args.test_root),pattern=args.pattern)
r=unittest.TextTestRunner(verbosity=2).run(suite)
for name,m in tuple(sys.modules.items()):
 for prefix,source in selected.items():
  if name==prefix or name.startswith(prefix+'.'):
   assert pathlib.Path(m.__file__).resolve().is_relative_to(source),(name,m.__file__)
sys.exit(0 if r.wasSuccessful() else 1)
