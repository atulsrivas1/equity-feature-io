"""Fresh core-only installed dependency absence, import denial and literal calculation."""
import importlib.abc
import importlib.util
from importlib.metadata import distribution
from pathlib import Path
import sys

ABSENT=('equity_feature_io_contracts','equity_feature_io_sdk','equity_feature_workers','equity_feature_duckdb',
        'equity_feature_parquet','equity_feature_duckdb_sink','equity_feature_example_extensions',
        'equity_feature_factory_fixture','duckdb','numpy','pandas','pyarrow','requests','httpx')
assert all(importlib.util.find_spec(name) is None for name in ABSENT)
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ABSENT:raise AssertionError('Forbidden core dependency '+fullname)
sys.meta_path.insert(0,Deny())
for name in ('equity-feature-contracts','equity-features'):
    dist=distribution(name)
    assert not any('equity-feature-io' in r or 'equity-feature-workers' in r for r in dist.requires or [])
    assert all('site-packages' in Path(dist.locate_file(p)).resolve().parts for p in dist.files if p.suffix=='.py')
from equity_feature_contracts import *
from equity_features.session import compute_bars
unit=PriceUnit(0,'USD')
config=ConfigSpec('synthetic-bars','v1',(Parameter('eligibility_policy','example-v1'),),SessionSpec('demo','S',100,200,'caller-supplied'),WindowSpec(1,'S',('P','S')),AvailabilitySpec(200,210,210),price_unit=unit)
facts=(('instrument_id',('A','A')),('session_id',('S','S')),('start_ns',(100,150)),('end_ns',(150,200)),('known_at_ns',(150,210)),('open',(100,102)),('high',(103,104)),('low',(99,101)),('close',(102,103)),('volume',(200,300)),('actual_notional',(20300,30900)))
batch=CanonicalBatch(DataKind.BAR,tuple(Column(n,v) for n,v in facts),BatchMetadata('demo',SourceBinding('synthetic','snapshot1','map1','bars1'),Coverage(2,2,True),unit,scope=InputScope(100,200,'example-v1')))
values={c.feature_id:c.values[0] for c in compute_bars(batch,config,entity=EntityKey('A','S')).values}
assert values['session.bar.volume']==500 and values['session.bar.notional']==51200 and values['session.bar.close_weighted_price']==102.6
assert values['session.price.overnight_gap'] is None
assert not any(n.split('.')[0] in ABSENT for n in sys.modules)
print('Actual core-only absence/deny/installed distribution and independent literal calculation PASS')
