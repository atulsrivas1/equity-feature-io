"""Actual trusted synthetic producer/export/read/replay, with an explicit missing ref."""
from equity_feature_contracts import (
    AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ConfigSpec, Coverage,
    DataKind, EntityKey, InputScope, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec,
)
from equity_feature_evidence import (
    EnvironmentDeclaration, PackageVersion, ExecutionClaim, EvidenceDisclosure,
    make_content_receipt, canonical_content,
)
from equity_feature_bundles import PublicationDeclaration, read_bundle, write_bundle
from equity_feature_bundles.replay import replay_bundle
from equity_features.session import compute_trades

configuration = ConfigSpec('bundle-demo','v1',(Parameter('eligibility_policy','example-v1'),),
    SessionSpec('demo','S',100,200,'caller'), WindowSpec(1,'S',('P','S')),
    AvailabilitySpec(200,210,210), price_unit=PriceUnit(0,'USD'))
batch = CanonicalBatch(DataKind.TRADE, tuple(Column(name, values) for name, values in (
    ('instrument_id',('A',)*3),('session_id',('S',)*3),('event_ns',(110,130,160)),
    ('order_key',(1,2,3)),('event_id',('t1','t2','t3')),('eligible',(True,)*3),
    ('price',(100,102,101)),('size',(2,3,5)),('known_at_ns',(110,130,210)),
)), BatchMetadata('demo',SourceBinding('synthetic','snapshot1','map1','trades1'),
    Coverage(3,3,True),PriceUnit(0,'USD'),scope=InputScope(100,200,'example-v1')))
result = compute_trades(batch, configuration, entity=EntityKey('A','S'))
assert tuple(c.values[0] for c in result.values) == (3,10,1011,101.1,10/3)
receipt = make_content_receipt(result, configuration, (('trades',batch),),
    EnvironmentDeclaration('CPython','3.12','caller-declared',(
        PackageVersion('equity-feature-contracts','0.0.4a4'),PackageVersion('equity-features','0.0.4a5'))),
    ExecutionClaim(), EvidenceDisclosure('not_supplied',0))
publication = PublicationDeclaration('synthetic','Caller-created synthetic example','caller_owned')
raw = write_bundle(receipt, configuration, result, (('trades',batch),), publication)
bundle = read_bundle(raw)
assert canonical_content(bundle.result) == canonical_content(result)
report = replay_bundle(bundle)
assert report.status == 'matched' and report.result_match is True and report.calculation_count == 1
assert report.declared_environment_verified is False
reference = read_bundle(write_bundle(receipt,configuration,result,(),publication))
assert replay_bundle(reference).status == 'unavailable'
assert replay_bundle(reference,(('trades',batch),)).status == 'matched'
assert replay_bundle(bundle,cancel_before_start=True).status == 'cancelled_before_start'
print('Actual five-output core/bundle replay and explicit reference resolution passed; no original-environment authentication.')
