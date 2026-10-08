"""Synthetic wire -> explicit factory -> pure trades; never contacts Databento."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
import time

from equity_feature_acquisition import (AcquisitionLimits, AcquisitionScope, AttemptBudget,
                                       DownloadApproval, Page)
from equity_feature_contracts import (AvailabilitySpec, ConfigSpec, Coverage, DataKind, EntityKey,
    InputScope, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec)
from equity_feature_contracts.adapters import AcquisitionRequest, HistoricalAdapter, validate_delivery
from equity_feature_databento import DatabentoFactory, DatabentoProfile, InstrumentBinding
from equity_feature_io_contracts import ComponentFactory
from equity_feature_io_sdk.factories import SourceRegistry
from equity_features.session import compute_trades

BASE = 1700000000000000000
# Literal owned DBN3 bytes inserted during fixture preparation; not provider data.
OWNED_DBN = bytes.fromhex('44424e03c0000000584e41532e4954434800000000000000040000002a36fe9c97170a002a36fe9c971700000000000000000000004700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000003100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000c0001000100000001002a36fe9c971700e8764817000000020000005442000002002a36fe9c971700000000070000000c0001000100000003002a36fe9c9717007cacbf17000000030000005442000004002a36fe9c971700000000080000000c0001000100000006002a36fe9c971700b2118417000000050000005442000007002a36fe9c97170000000009000000')


class NeverCancelled:
    def is_cancelled(self) -> bool: return False


class SyntheticCredentials:
    def get(self, name: str) -> str | None:
        assert name == 'DATABENTO_API_KEY'
        return 'owned-synthetic-placeholder'


def owned_approval(scope: AcquisitionScope) -> DownloadApproval:
    return DownloadApproval(scope,'example-owned-synthetic-only',time.monotonic_ns()+1_000_000_000,
                            AcquisitionLimits(1,10,10000,1_000_000_000,0))


def owned_transport(parameters: Mapping[str,str], credential: str | None,
                    budget: AttemptBudget, check: Callable[[],None]) -> Page:
    assert parameters['dataset']=='XNAS.ITCH' and parameters['symbols']=='1'
    assert credential=='owned-synthetic-placeholder'
    check()
    return Page(OWNED_DBN,3)


def configuration(*, reconstruction: bool) -> ConfigSpec:
    availability=AvailabilitySpec(BASE+10,BASE+10,BASE+10)
    if reconstruction:
        availability=replace(availability,mode='reconstruction',reconstruction_reason='owned-replay')
    return ConfigSpec('owned-databento-example','v1',(Parameter('eligibility_policy','owned-trades-v1'),),
        SessionSpec('owned-fixture','S',BASE,BASE+10,'supplied'),WindowSpec(1,'S',('S',)),
        availability,price_unit=PriceUnit(9,'USD'))


def main() -> None:
    profile=DatabentoProfile('XNAS.ITCH','trades','owned-fixture',
        SourceBinding('owned-databento','owned-snapshot','owned-mapping','owned-input'),PriceUnit(9,'USD'),
        InputScope(BASE,BASE+10,'owned-trades-v1'),BASE,BASE+10,(InstrumentBinding(1,1,'A','S',True),),
        Coverage(3,3,True),'independent-owned-event-population',(BASE+1,None,BASE+999))
    request=AcquisitionRequest('owned-request',DataKind.TRADE,'owned-fixture',('A',),('S',),BASE,BASE+10,
        'owned-snapshot',PriceUnit(9,'USD'),AvailabilitySpec(BASE+10,BASE+10,BASE+10),max_batch_rows=3)
    factory: ComponentFactory[HistoricalAdapter]=DatabentoFactory(profile,approve=owned_approval,
        cost_upper_micro_usd=0,transport=owned_transport)
    registry: SourceRegistry[HistoricalAdapter]=SourceRegistry()
    registry.register('owned-databento',factory)
    adapter=registry.resolve('owned-databento',{'profile_id':profile.fingerprint},SyntheticCredentials(),request)
    delivery=tuple(adapter.iter_batches(request,NeverCancelled()))
    validate_delivery(request,adapter.capabilities(),delivery)
    batch=delivery[0].batch
    assert batch is not None
    replay=compute_trades(batch,configuration(reconstruction=True),entity=EntityKey('A','S'))
    values={c.feature_id.rsplit('.',1)[1]:c.values[0] for c in replay.values}
    assert values['count']==3 and values['volume']==10 and values['notional']==1011000000000
    vwap,mean=values['vwap'],values['mean_size']
    assert type(vwap) is float and abs(vwap-101.1)<1e-12
    assert type(mean) is float and abs(mean-10/3)<1e-12
    causal=compute_trades(batch,configuration(reconstruction=False),entity=EntityKey('A','S'))
    assert all(c.values[0] is None for c in causal.values)
    print('Owned DBN3/factory/exact pure reconstruction and retained unknown/future causal evidence PASS')


if __name__=='__main__': main()
