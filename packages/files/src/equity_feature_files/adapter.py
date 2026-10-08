"""Explicit local-use admission, immutable bytes and canonical delivery."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from types import MappingProxyType
from typing import cast

from equity_feature_acquisition import (AcquisitionController, AcquisitionScope, AttemptBudget,
    AttemptFailure, DownloadApproval, ImmutableCache, Page, RetentionApproval)
from equity_feature_contracts import BatchMetadata, CanonicalBatch, Column, Coverage, DataKind
from equity_feature_contracts.adapters import (AcquisitionRequest, AdapterBatch, AdapterCapabilities,
    Cancellation, HistoricalAdapter, SourceError, SourceErrorCode, require_adapter_capability)
from equity_feature_contracts.inputs import I64_MAX, SourceBinding
from equity_feature_contracts.validation import validate_batch
from equity_feature_io_contracts import CredentialProvider, FactoryError, FactoryErrorCode, PublicConfig
from .codecs import Row, decode, dependency
from .model import FIELDS, FileProfile, ReadPolicy, fail

Approval = Callable[[AcquisitionScope], DownloadApproval | None]
Retention = Callable[[AcquisitionScope], RetentionApproval | None]


def local_path(value: object) -> str:
    if (type(value) is not str or not value.strip() or len(value) > 4096
            or "\x00" in value or value.startswith(("\\", "//"))
            or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) and not re.match(r"^[A-Za-z]:[\\/]", value)):
        fail(SourceErrorCode.UNSUPPORTED)
    return value


class LocalFileTradeAdapter:
    def __init__(self, path: str, profile: FileProfile, *, approve: Approval,
                 policy: ReadPolicy = ReadPolicy(), clock_ns: Callable[[], int] = time.monotonic_ns,
                 cache: ImmutableCache | None = None, retain: Retention | None = None) -> None:
        self._path = local_path(path)
        if type(profile) is not FileProfile or type(policy) is not ReadPolicy:
            fail()
        if profile.coverage.observed > policy.max_input_rows:
            fail(SourceErrorCode.LIMIT)
        if cache is not None and type(cache) is not ImmutableCache:
            fail()
        self._profile, self._policy = profile, policy
        self._approve, self._clock = approve, clock_ns
        self._cache, self._retain = cache, retain

    def __repr__(self) -> str:
        return "LocalFileTradeAdapter(<opaque>)"

    def capabilities(self) -> AdapterCapabilities:
        p = self._profile
        return AdapterCapabilities((DataKind.TRADE,), (p.namespace,), (p.price_unit,),
                                   max_batch_rows=self._policy.max_batch_rows)

    def acquisition_scope(self, request: AcquisitionRequest) -> AcquisitionScope:
        p = self._profile
        require_adapter_capability(self.capabilities(), request)
        if (request.snapshot_id != p.source.snapshot_id or request.start_ns < p.scope.start_ns
                or request.end_ns > p.scope.end_ns or request.adjustment.policy_version != "raw-v1"
                or request.adjustment.action_snapshot != "none" or request.adjustment.anchor != "none"):
            fail(SourceErrorCode.UNSUPPORTED)
        return AcquisitionScope(request, "local-file", p.source.source_id,
                                p.schema + ":" + p.format, "file", p.sha256, p.fingerprint)

    def iter_batches(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        error: SourceErrorCode | None = None
        try:
            yield from self._iterate(request, cancellation)
        except SourceError as caught:
            error = caught.code
        except Exception:
            error = SourceErrorCode.SCHEMA
        if error is not None:
            fail(error)

    def _iterate(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        scope = self.acquisition_scope(request)
        p, policy = self._profile, self._policy
        last = self._clock()
        if type(last) is not int or not 0 <= last <= I64_MAX:
            fail()
        started = last
        deadline = started + policy.max_elapsed_ns
        retention_expiry: int | None = None

        def check() -> None:
            nonlocal last
            cancelled = cancellation.is_cancelled()
            if type(cancelled) is not bool:
                fail()
            if cancelled:
                fail(SourceErrorCode.CANCELLED)
            now = self._clock()
            if type(now) is not int or not last <= now <= I64_MAX:
                fail()
            last = now
            if now >= deadline:
                fail(SourceErrorCode.LIMIT)
            if retention_expiry is not None and now >= retention_expiry:
                fail(SourceErrorCode.ENTITLEMENT)

        check()
        # Dependencies are never installed implicitly, and absent codecs fail before open.
        if p.format == "parquet":
            dependency("pyarrow.parquet", "pyarrow", "20.0.0")
        elif p.format == "dbn":
            dependency("databento_dbn", "databento-dbn", "0.70.0")
        permission = self._retain(scope) if self._retain is not None else None
        if permission is not None:
            if type(permission) is not RetentionApproval or permission.scope != scope:
                fail(SourceErrorCode.ENTITLEMENT)
            retention_expiry = permission.expires_ns
        cached = (self._cache.get(permission, page_key="file")
                  if self._cache is not None and permission is not None else None)
        full: CanonicalBatch | None = None
        indices: tuple[int, ...] = ()

        def normalize(raw: bytes) -> None:
            nonlocal full, indices
            check()
            if hashlib.sha256(raw).hexdigest() != p.sha256:
                fail()
            rows = decode(raw, p, policy, check)
            if len(rows) != p.coverage.observed:
                fail()
            source = self._source(())
            full = self._batch(rows, source)
            validate_batch(full, required_fields=())
            if any(not p.scope.start_ns <= r[2] < p.scope.end_ns for r in rows):
                fail()
            indices = tuple(i for i, row in enumerate(rows) if row[0] in request.instruments
                            and row[1] in request.sessions and request.start_ns <= row[2] < request.end_ns)
            count = len(indices)
            chunks = max(1, (count + request.max_batch_rows - 1) // request.max_batch_rows)
            if count > request.max_rows or chunks > request.max_batches:
                fail(SourceErrorCode.LIMIT)
            check()

        page: Page
        if cached is not None:
            normalize(cached.data)
            if cached.row_count != len(indices):
                fail()
            page = cached
        else:
            approval = self._approve(scope)
            if approval is not None:
                if type(approval) is not DownloadApproval or approval.scope != scope:
                    fail(SourceErrorCode.ENTITLEMENT)
                deadline = min(deadline, approval.expires_ns, started + approval.limits.max_elapsed_ns)
            controller = AcquisitionController(approval, clock_ns=self._clock,
                                               sleep_ns=lambda _: None, cancelled=cancellation.is_cancelled)

            def read(credential: str | None, budget: AttemptBudget) -> Page:
                raw = bytearray()
                code: SourceErrorCode | None = None
                try:
                    check()
                    with Path(self._path).open("rb") as file:
                        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                            fail(SourceErrorCode.UNSUPPORTED)
                        limit = min(policy.max_bytes, budget.remaining_bytes)
                        while True:
                            check()
                            chunk = file.read(min(policy.read_chunk_bytes, limit - len(raw) + 1))
                            if not chunk:
                                break
                            raw.extend(chunk)
                            if len(raw) > limit:
                                fail(SourceErrorCode.LIMIT)
                    normalize(bytes(raw))
                    return Page(bytes(raw), len(indices))
                except FileNotFoundError:
                    code = SourceErrorCode.UNAVAILABLE
                except OSError:
                    code = SourceErrorCode.UNAVAILABLE
                except SourceError as caught:
                    code = caught.code
                except Exception:
                    code = SourceErrorCode.SCHEMA
                assert code is not None
                raise AttemptFailure(code, received_bytes=len(raw))

            page = controller.execute(scope, read, cost_upper_micro_usd=0)
            if self._cache is not None and permission is not None:
                check()
                self._cache.put(permission, page, page_key="file")
        assert full is not None
        chunks = max(1, (len(indices) + request.max_batch_rows - 1) // request.max_batch_rows)
        for ordinal in range(chunks):
            check()
            selected = indices[ordinal*request.max_batch_rows:(ordinal+1)*request.max_batch_rows]
            source = self._source(selected)
            batch = CanonicalBatch(DataKind.TRADE,
                tuple(Column(c.name, tuple(c.values[i] for i in selected)) for c in full.columns),
                replace(full.metadata, source=source))
            check()
            yield AdapterBatch(request.request_id, ordinal, ordinal == chunks-1, source,
                               p.coverage, Coverage(len(selected), len(selected), True), batch)

    def _source(self, indices: tuple[int, ...]) -> SourceBinding:
        p = self._profile
        selected = hashlib.sha256(json.dumps(indices, separators=(",", ":")).encode()).hexdigest()
        return replace(p.source, mapping_version=p.source.mapping_version + ":profile:" + p.fingerprint,
                       input_id=p.source.input_id + ":file:" + p.sha256 + ":profile:" + p.fingerprint + ":rows:" + selected)

    def _batch(self, rows: tuple[Row, ...], source: SourceBinding) -> CanonicalBatch:
        p = self._profile
        return CanonicalBatch(DataKind.TRADE,
            tuple(Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(FIELDS)),
            BatchMetadata(p.namespace, source, p.coverage, p.price_unit, scope=p.scope))


class LocalFileFactory:
    """Existing ComponentFactory extension; credentials are never consulted."""
    protocol_version = "1"

    def __init__(self, profile: FileProfile, *, approve: Approval,
                 policy: ReadPolicy = ReadPolicy(), clock_ns: Callable[[], int] = time.monotonic_ns,
                 cache: ImmutableCache | None = None, retain: Retention | None = None) -> None:
        self._profile, self._approve, self._policy = profile, approve, policy
        self._clock, self._cache, self._retain = clock_ns, cache, retain

    def __repr__(self) -> str:
        return "LocalFileFactory(<opaque>)"

    def validate_config(self, config: PublicConfig) -> PublicConfig:
        valid: str | None = None
        try:
            if set(config) == {"path"}:
                valid = local_path(config["path"])
        except Exception:
            pass
        if valid is None:
            raise FactoryError(FactoryErrorCode.INVALID_CONFIG)
        return MappingProxyType({"path": valid})

    def create(self, config: PublicConfig, credentials: CredentialProvider) -> HistoricalAdapter:
        validated = self.validate_config(config)
        return LocalFileTradeAdapter(cast(str, validated["path"]), self._profile,
             approve=self._approve, policy=self._policy, clock_ns=self._clock,
             cache=self._cache, retain=self._retain)
