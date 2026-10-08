"""Owned exact JSON/factory/pure BAR consumer; never contacts Massive."""
from collections.abc import Callable
from dataclasses import replace
import time

from equity_feature_acquisition import AcquisitionLimits, AcquisitionScope, AttemptBudget, DownloadApproval
from equity_feature_contracts import (AvailabilitySpec, ConfigSpec, Coverage, DataKind, EntityKey,
    InputScope, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec)
from equity_feature_contracts.adapters import AcquisitionRequest, HistoricalAdapter, validate_delivery
from equity_feature_io_contracts import ComponentFactory
from equity_feature_io_sdk.factories import SourceRegistry
from equity_feature_massive import MassiveFactory, MassiveProfile
from equity_features.session import compute_bars

BASE=1700000040000000000; END=1700000100000000000
OWNED_JSON=b'{"ticker":"AAPL","adjusted":false,"queryCount":1,"resultsCount":1,"status":"OK","results":[{"t":1700000040000,"o":100.000000001,"h":102.000000003,"l":99.000000002,"c":101.000000004,"v":10,"n":3,"vw":101.1}]}'


class NeverCancelled:
    def is_cancelled(self) -> bool: return False


class SyntheticCredentials:
    def get(self,name: str) -> str | None:
        assert name=='MASSIVE_API_KEY'
        return 'owned-synthetic-placeholder'


def owned_approval(scope: AcquisitionScope) -> DownloadApproval:
    return DownloadApproval(scope,'owned-synthetic-only',time.monotonic_ns()+1_000_000_000,
                            AcquisitionLimits(1,10,10000,1_000_000_000,0))


def owned_transport(path: str,credential: str | None,budget: AttemptBudget,
                    check: Callable[[],None]) -> bytes:
    assert path.startswith('/v2/aggs/ticker/AAPL/range/1/minute/')
    assert credential=='owned-synthetic-placeholder'
    check()
    return OWNED_JSON


def configuration(*,reconstruction: bool) -> ConfigSpec:
    availability=AvailabilitySpec(END,END,END)
    if reconstruction:
        availability=replace(availability,mode='reconstruction',reconstruction_reason='owned-replay')
    return ConfigSpec('owned-massive-example','v1',(Parameter('eligibility_policy','owned-minute'),),
        SessionSpec('owned-fixture','S',BASE,END,'supplied'),WindowSpec(1,'S',('P','S')),
        availability,price_unit=PriceUnit(9,'USD'))


def main() -> None:
    profile=MassiveProfile('AAPL','A','S','owned-fixture',
        SourceBinding('owned-massive','owned-snapshot','owned-mapping','owned-input'),PriceUnit(9,'USD'),
        InputScope(BASE,END,'owned-minute'),Coverage(1,1,True),'independent-owned-minute')
    request=AcquisitionRequest('owned-request',DataKind.BAR,'owned-fixture',('A',),('S',),BASE,END,
        'owned-snapshot',PriceUnit(9,'USD'),AvailabilitySpec(END,END,END),max_batch_rows=3,
        selection='completed_intervals')
    factory: ComponentFactory[HistoricalAdapter]=MassiveFactory(profile,approve=owned_approval,
        cost_upper_micro_usd=0,transport=owned_transport)
    registry: SourceRegistry[HistoricalAdapter]=SourceRegistry()
    registry.register('owned-massive',factory)
    adapter=registry.resolve('owned-massive',{'profile_id':profile.fingerprint},SyntheticCredentials(),request)
    delivery=tuple(adapter.iter_batches(request,NeverCancelled()))
    validate_delivery(request,adapter.capabilities(),delivery)
    batch=delivery[0].batch
    assert batch is not None
    notional=batch.column('actual_notional')
    assert notional is not None and notional.values==(None,)
    replay=compute_bars(batch,configuration(reconstruction=True),entity=EntityKey('A','S'))
    values={c.feature_id:c.values[0] for c in replay.values}
    assert values['session.bar.volume']==10 and values['session.bar.notional'] is None
    proxy=values['session.bar.close_weighted_price']
    assert type(proxy) is float and abs(proxy-101.000000004)<1e-12
    causal=compute_bars(batch,configuration(reconstruction=False),entity=EntityKey('A','S'))
    assert all(c.values[0] is None for c in causal.values)
    print('Owned exact Decimal/factory/pure BAR proxy, absent exactnotional and unknown causal evidence PASS')


if __name__=='__main__': main()
