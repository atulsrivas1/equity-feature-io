"""Exact caller-approved single-use historical minute-bar acquisition."""
from collections.abc import Callable, Iterator
from dataclasses import replace
import hashlib
import json
from threading import Lock
import time
from types import MappingProxyType

from equity_feature_acquisition import (AcquisitionController, AcquisitionScope, AttemptBudget,
    AttemptFailure, DownloadApproval, Page)
from equity_feature_contracts import BatchMetadata, CanonicalBatch, Column, Coverage, DataKind
from equity_feature_contracts.adapters import (AcquisitionRequest, AdapterBatch, AdapterCapabilities,
    Cancellation, HistoricalAdapter, SourceError, SourceErrorCode, require_adapter_capability)
from equity_feature_contracts.inputs import I64_MAX, SourceBinding
from equity_feature_io_contracts import CredentialProvider, FactoryError, FactoryErrorCode, PublicConfig
from .codec import FIELDS, Row, safe_decode
from .model import MassiveProfile, DownloadPolicy, fail
from .transport import HTTPSMassiveTransport, MassiveTransport

Approval=Callable[[AcquisitionScope],DownloadApproval | None]


class MassiveHistoricalAdapter:
    def __init__(self,profile: MassiveProfile,*,approve: Approval,credentials: CredentialProvider,
                 policy: DownloadPolicy=DownloadPolicy(),cost_upper_micro_usd: int | None=None,
                 clock_ns: Callable[[],int]=time.monotonic_ns,transport: MassiveTransport | None=None) -> None:
        if type(profile) is not MassiveProfile or type(policy) is not DownloadPolicy: fail()
        if cost_upper_micro_usd is not None and (type(cost_upper_micro_usd) is not int
                or not 0<=cost_upper_micro_usd<=I64_MAX): fail()
        if profile.record_known_at_ns is not None and len(profile.record_known_at_ns)>policy.max_rows:
            fail(SourceErrorCode.LIMIT)
        self._profile,self._policy=profile,policy
        self._approve,self._credentials,self._clock,self._cost=approve,credentials,clock_ns,cost_upper_micro_usd
        self._transport=transport if transport is not None else HTTPSMassiveTransport(policy,clock_ns)
        self._lock,self._used=Lock(),False

    def __repr__(self) -> str: return 'MassiveHistoricalAdapter(<opaque>)'

    def capabilities(self) -> AdapterCapabilities:
        p=self._profile
        return AdapterCapabilities((DataKind.BAR,),(p.namespace,),(p.price_unit,),
                                   max_batch_rows=self._policy.max_batch_rows)

    def acquisition_scope(self,request: AcquisitionRequest) -> AcquisitionScope:
        p=self._profile;require_adapter_capability(self.capabilities(),request)
        if (request.instruments!=(p.instrument_id,) or request.sessions!=(p.session_id,)
                or request.start_ns!=p.scope.start_ns or request.end_ns!=p.scope.end_ns
                or request.snapshot_id!=p.source.snapshot_id or request.adjustment.policy_version!='raw-v1'
                or request.adjustment.action_snapshot!='none' or request.adjustment.anchor!='none'):
            fail(SourceErrorCode.UNSUPPORTED)
        return AcquisitionScope(request,'massive','stocks','aggregates:1minute','historical',
                                p.source.input_id,p.fingerprint)

    def iter_batches(self,request: AcquisitionRequest,cancellation: Cancellation) -> Iterator[AdapterBatch]:
        if not self._lock.acquire(blocking=False): fail(SourceErrorCode.LIMIT)
        error: SourceErrorCode | None=None
        try:
            if self._used: fail(SourceErrorCode.LIMIT)
            self._used=True
            try: yield from self._iterate(request,cancellation)
            except SourceError as caught: error=caught.code
            except Exception: error=SourceErrorCode.SCHEMA
        finally: self._lock.release()
        if error is not None: fail(error)

    def _iterate(self,request: AcquisitionRequest,cancellation: Cancellation) -> Iterator[AdapterBatch]:
        scope=self.acquisition_scope(request);p,policy=self._profile,self._policy
        started=self._clock()
        if type(started) is not int or not 0<=started<=I64_MAX: fail()
        last,deadline=started,started+policy.max_elapsed_ns

        def check() -> None:
            nonlocal last
            cancelled,now=cancellation.is_cancelled(),self._clock()
            if type(cancelled) is not bool or type(now) is not int or not last<=now<=I64_MAX: fail()
            last=now
            if cancelled: fail(SourceErrorCode.CANCELLED)
            if now>=deadline: fail(SourceErrorCode.LIMIT)

        check();approval=self._approve(scope)
        if approval is not None:
            if type(approval) is not DownloadApproval or approval.scope!=scope: fail(SourceErrorCode.ENTITLEMENT)
            deadline=min(deadline,approval.expires_ns,started+approval.limits.max_elapsed_ns)
            approval=replace(approval,expires_ns=deadline)
        check()
        controller=AcquisitionController(approval,clock_ns=self._clock,sleep_ns=lambda _:None,
                                         cancelled=cancellation.is_cancelled)
        limit=min(policy.max_rows,request.max_rows,approval.limits.max_rows if approval is not None else request.max_rows)
        path=(f'/v2/aggs/ticker/{p.ticker}/range/1/minute/{p.scope.start_ns//1_000_000}/'
              f'{p.scope.end_ns//1_000_000-1}?adjusted=false&sort=asc&limit={limit}')
        rows: tuple[Row,...] | None=None

        def read(credential: str | None,budget: AttemptBudget) -> Page:
            nonlocal rows
            raw=b'';error: SourceErrorCode | None=None; result: Page | None=None
            try:
                check();raw=self._transport(path,credential,budget,check);check()
                if type(raw) is not bytes: fail()
                if len(raw)>min(policy.max_bytes,budget.remaining_bytes): fail(SourceErrorCode.LIMIT)
                rows=safe_decode(raw,p,policy,limit,check)
                result=Page(raw,len(rows))
            except AttemptFailure:
                raise
            except SourceError as caught: error=caught.code
            except Exception: error=SourceErrorCode.TRANSPORT
            if result is None:
                assert error is not None
                raise AttemptFailure(error,received_bytes=len(raw) if type(raw) is bytes else 0)
            return result

        page=controller.execute(scope,read,cost_upper_micro_usd=self._cost,
            credentials=self._credentials,credential_name='MASSIVE_API_KEY')
        assert rows is not None
        coverage=p.coverage if p.coverage is not None else Coverage(None,len(rows),False)
        if coverage.observed!=len(rows): fail()
        chunks=max(1,(len(rows)+request.max_batch_rows-1)//request.max_batch_rows)
        if len(rows)>request.max_rows or chunks>request.max_batches: fail(SourceErrorCode.LIMIT)
        digest=hashlib.sha256(page.data).hexdigest()
        for ordinal in range(chunks):
            check();indices=tuple(range(ordinal*request.max_batch_rows,min((ordinal+1)*request.max_batch_rows,len(rows))))
            source=self._source(digest,indices)
            batch=CanonicalBatch(DataKind.BAR,tuple(Column(name,tuple(rows[n][i] for n in indices))
                for i,name in enumerate(FIELDS)),BatchMetadata(p.namespace,source,coverage,p.price_unit,scope=p.scope))
            check()
            yield AdapterBatch(request.request_id,ordinal,ordinal==chunks-1,source,coverage,
                               Coverage(len(indices),len(indices),True),batch)

    def _source(self,digest: str,indices: tuple[int,...]) -> SourceBinding:
        p=self._profile;selected=hashlib.sha256(json.dumps(indices,separators=(',',':')).encode()).hexdigest()
        return replace(p.source,mapping_version=p.source.mapping_version+':profile:'+p.fingerprint,
            input_id=p.source.input_id+':json:'+digest+':profile:'+p.fingerprint+':rows:'+selected)


class MassiveFactory:
    protocol_version='1'
    def __init__(self,profile: MassiveProfile,*,approve: Approval,policy: DownloadPolicy=DownloadPolicy(),
                 cost_upper_micro_usd: int | None=None,clock_ns: Callable[[],int]=time.monotonic_ns,
                 transport: MassiveTransport | None=None) -> None:
        self._profile,self._approve,self._policy=profile,approve,policy
        self._cost,self._clock,self._transport=cost_upper_micro_usd,clock_ns,transport

    def __repr__(self) -> str: return 'MassiveFactory(<opaque>)'

    def validate_config(self,config: PublicConfig) -> PublicConfig:
        valid=False
        try: valid=set(config)=={'profile_id'} and config['profile_id']==self._profile.fingerprint
        except Exception: pass
        if not valid: raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        return MappingProxyType({'profile_id':self._profile.fingerprint})

    def create(self,config: PublicConfig,credentials: CredentialProvider) -> HistoricalAdapter:
        self.validate_config(config)
        return MassiveHistoricalAdapter(self._profile,approve=self._approve,credentials=credentials,
            policy=self._policy,cost_upper_micro_usd=self._cost,clock_ns=self._clock,transport=self._transport)
