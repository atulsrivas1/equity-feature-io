"""One explicitly approved historical acquisition; no registration side effects."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
import hashlib
import json
from threading import Lock
import time
from types import MappingProxyType

from equity_feature_acquisition import (AcquisitionController, AcquisitionScope, AttemptBudget,
    DownloadApproval, Page)
from equity_feature_contracts import BatchMetadata, CanonicalBatch, Column, Coverage, DataKind
from equity_feature_contracts.adapters import (AcquisitionRequest, AdapterBatch, AdapterCapabilities,
    Cancellation, HistoricalAdapter, SourceError, SourceErrorCode, require_adapter_capability)
from equity_feature_contracts.inputs import I64_MAX, SourceBinding
from equity_feature_contracts.validation import validate_batch
from equity_feature_io_contracts import CredentialProvider, FactoryError, FactoryErrorCode, PublicConfig
from .codec import BAR_FIELDS, TRADE_FIELDS, layout, safe_decode
from .model import DatabentoProfile, DownloadPolicy, fail, text
from .transport import DatabentoTransport, HTTPSDatabentoTransport

Approval = Callable[[AcquisitionScope], DownloadApproval | None]


class DatabentoHistoricalAdapter:
    def __init__(self, profile: DatabentoProfile, *, approve: Approval,
                 credentials: CredentialProvider, policy: DownloadPolicy = DownloadPolicy(),
                 credential_name: str = 'DATABENTO_API_KEY', cost_upper_micro_usd: int | None = None,
                 clock_ns: Callable[[], int] = time.monotonic_ns,
                 transport: DatabentoTransport | None = None) -> None:
        if type(profile) is not DatabentoProfile or type(policy) is not DownloadPolicy:
            fail()
        text(credential_name)
        if cost_upper_micro_usd is not None and (type(cost_upper_micro_usd) is not int
                or not 0 <= cost_upper_micro_usd <= I64_MAX):
            fail()
        self._profile, self._policy = profile, policy
        self._approve, self._credentials, self._credential_name = approve, credentials, credential_name
        self._cost, self._clock = cost_upper_micro_usd, clock_ns
        self._transport = transport if transport is not None else HTTPSDatabentoTransport(policy, clock_ns)
        self._lock, self._used = Lock(), False

    def __repr__(self) -> str:
        return 'DatabentoHistoricalAdapter(<opaque>)'

    def capabilities(self) -> AdapterCapabilities:
        p = self._profile
        return AdapterCapabilities((DataKind.TRADE if p.schema == 'trades' else DataKind.BAR,),
            (p.namespace,), (p.price_unit,), max_batch_rows=self._policy.max_batch_rows)

    def acquisition_scope(self, request: AcquisitionRequest) -> AcquisitionScope:
        p = self._profile
        require_adapter_capability(self.capabilities(), request)
        # The network request never broadens the approved canonical population.
        if (request.snapshot_id != p.source.snapshot_id or request.start_ns != p.event_scope.start_ns
                or request.end_ns != p.event_scope.end_ns
                or set(request.instruments) != {b.canonical_id for b in p.bindings}
                or set(request.sessions) != {b.session_id for b in p.bindings}
                or request.adjustment.policy_version != 'raw-v1'
                or request.adjustment.action_snapshot != 'none' or request.adjustment.anchor != 'none'):
            fail(SourceErrorCode.UNSUPPORTED)
        return AcquisitionScope(request, 'databento', p.dataset, 'timeseries.get_range:' + p.schema,
                                'historical', p.source.input_id, p.fingerprint)

    def iter_batches(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        error: SourceErrorCode | None = None
        if not self._lock.acquire(blocking=False):
            fail(SourceErrorCode.LIMIT)
        try:
            if self._used:
                fail(SourceErrorCode.LIMIT)
            self._used = True
            try:
                yield from self._iterate(request, cancellation)
            except SourceError as caught:
                error = caught.code
            except Exception:
                error = SourceErrorCode.SCHEMA
        finally:
            self._lock.release()
        if error is not None:
            fail(error)

    def _iterate(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        scope = self.acquisition_scope(request)
        p, policy = self._profile, self._policy
        started = self._clock()
        if type(started) is not int or not 0 <= started <= I64_MAX:
            fail()
        last, deadline = started, started + policy.max_elapsed_ns

        def check() -> None:
            nonlocal last
            cancelled, now = cancellation.is_cancelled(), self._clock()
            if type(cancelled) is not bool or type(now) is not int or not last <= now <= I64_MAX:
                fail()
            last = now
            if cancelled:
                fail(SourceErrorCode.CANCELLED)
            if now >= deadline:
                fail(SourceErrorCode.LIMIT)

        check()
        approval = self._approve(scope)
        if approval is not None:
            if type(approval) is not DownloadApproval or approval.scope != scope:
                fail(SourceErrorCode.ENTITLEMENT)
            deadline = min(deadline, approval.expires_ns, started + approval.limits.max_elapsed_ns)
        controller = AcquisitionController(approval, clock_ns=self._clock,
            sleep_ns=lambda _: None, cancelled=cancellation.is_cancelled)
        record_limit = min(policy.max_rows, request.max_rows,
                           approval.limits.max_rows if approval is not None else request.max_rows)
        parameters = MappingProxyType({'dataset':p.dataset, 'schema':p.schema,
            'symbols':','.join(str(n) for n in sorted({b.instrument_id for b in p.bindings})),
            'stype_in':'instrument_id', 'stype_out':'instrument_id', 'encoding':'dbn',
            'compression':'none', 'start':str(p.capture_start_ns), 'end':str(p.capture_end_ns),
            'limit':str(record_limit)})

        def read(credential: str | None, budget: AttemptBudget) -> Page:
            check()
            return self._transport(parameters, credential,
                replace(budget, deadline_ns=min(deadline, budget.deadline_ns)), check)

        page = controller.execute(scope, read, cost_upper_micro_usd=self._cost,
            credentials=self._credentials, credential_name=self._credential_name)
        check()
        _, _, wire_count = layout(page.data, p.schema)
        if page.row_count != wire_count:
            fail()
        # A full capped response cannot prove EOF or completeness. Fail closed.
        if wire_count >= record_limit:
            fail(SourceErrorCode.LIMIT)
        rows = safe_decode(page.data, p, policy, check)
        coverage = p.coverage if p.coverage is not None else Coverage(None, len(rows), False)
        if coverage.observed != len(rows):
            fail()
        digest = hashlib.sha256(page.data).hexdigest()
        kind = DataKind.TRADE if p.schema == 'trades' else DataKind.BAR
        fields = TRADE_FIELDS if kind == DataKind.TRADE else BAR_FIELDS
        source = self._source(digest, ())
        full = CanonicalBatch(kind, tuple(Column(name, tuple(row[i] for row in rows))
            for i,name in enumerate(fields)), BatchMetadata(p.namespace, source, coverage,
                                                          p.price_unit, scope=p.event_scope))
        # Validate the whole population before publishing any prefix.
        validate_batch(full, required_fields=())
        chunks = max(1, (len(rows)+request.max_batch_rows-1)//request.max_batch_rows)
        if len(rows) > request.max_rows or chunks > request.max_batches:
            fail(SourceErrorCode.LIMIT)
        for ordinal in range(chunks):
            check()
            indices = tuple(range(ordinal*request.max_batch_rows,
                                  min((ordinal+1)*request.max_batch_rows,len(rows))))
            source = self._source(digest, indices)
            batch = CanonicalBatch(kind, tuple(Column(c.name, tuple(c.values[i] for i in indices))
                for c in full.columns), replace(full.metadata, source=source))
            check()
            yield AdapterBatch(request.request_id, ordinal, ordinal == chunks-1, source, coverage,
                               Coverage(len(indices),len(indices),True), batch)

    def _source(self, digest: str, indices: tuple[int,...]) -> SourceBinding:
        p = self._profile
        selected = hashlib.sha256(json.dumps(indices,separators=(',',':')).encode()).hexdigest()
        return replace(p.source, mapping_version=p.source.mapping_version + ':profile:' + p.fingerprint,
            input_id=p.source.input_id + ':dbn:' + digest + ':profile:' + p.fingerprint + ':rows:' + selected)


class DatabentoFactory:
    protocol_version = '1'

    def __init__(self, profile: DatabentoProfile, *, approve: Approval,
                 policy: DownloadPolicy = DownloadPolicy(), cost_upper_micro_usd: int | None = None,
                 clock_ns: Callable[[], int] = time.monotonic_ns,
                 transport: DatabentoTransport | None = None) -> None:
        self._profile, self._approve, self._policy = profile, approve, policy
        self._cost, self._clock, self._transport = cost_upper_micro_usd, clock_ns, transport

    def __repr__(self) -> str:
        return 'DatabentoFactory(<opaque>)'

    def validate_config(self, config: PublicConfig) -> PublicConfig:
        valid = False
        try:
            valid = set(config) == {'profile_id'} and config['profile_id'] == self._profile.fingerprint
        except Exception:
            pass
        if not valid:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        return MappingProxyType({'profile_id':self._profile.fingerprint})

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> HistoricalAdapter:
        self.validate_config(config)
        return DatabentoHistoricalAdapter(self._profile, approve=self._approve, credentials=credentials,
            policy=self._policy, cost_upper_micro_usd=self._cost, clock_ns=self._clock,
            transport=self._transport)
