"""Disabled-by-default, serial, authorized immutable byte cache."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from equity_feature_contracts.adapters import SourceErrorCode
from .controls import AcquisitionScope, Page, fail, identity, integer


@dataclass(frozen=True)
class CachePolicy:
    max_entries: int
    max_bytes: int
    ttl_ns: int

    def __post_init__(self) -> None:
        for value in (self.max_entries, self.max_bytes, self.ttl_ns):
            integer(value)


@dataclass(frozen=True, repr=False)
class RetentionApproval:
    scope: AcquisitionScope
    authorization_scope: str
    expires_ns: int
    immutable_revision: bool

    def __post_init__(self) -> None:
        if type(self.scope) is not AcquisitionScope or type(self.immutable_revision) is not bool:
            fail()
        identity(self.authorization_scope)
        integer(self.expires_ns)


class ImmutableCache:
    def __init__(self, *, clock_ns: Callable[[], int], policy: CachePolicy | None = None) -> None:
        if policy is not None and type(policy) is not CachePolicy:
            fail()
        self._clock = clock_ns
        self._policy = policy
        self._entries: OrderedDict[tuple[AcquisitionScope, str, str], tuple[int, Page]] = OrderedDict()
        self._bytes = 0
        self._last = 0

    def __repr__(self) -> str:
        return "ImmutableCache(<opaque>)"

    @property
    def stored_bytes(self) -> int:
        return self._bytes

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def _admit(self, approval: RetentionApproval, page_key: str) -> tuple[int, tuple[AcquisitionScope, str, str]]:
        if type(approval) is not RetentionApproval:
            fail(SourceErrorCode.ENTITLEMENT)
        identity(page_key)
        now = -1
        try:
            now = self._clock()
        except Exception:
            pass
        integer(now, zero=True)
        if now < self._last:
            fail()
        self._last = now
        # Purge expired data on every enabled operation; TTL never slides on access.
        for key, (expiry, page) in tuple(self._entries.items()):
            if now >= expiry:
                del self._entries[key]
                self._bytes -= len(page.data)
        if not approval.immutable_revision or approval.scope.mode == "live" or now >= approval.expires_ns:
            fail(SourceErrorCode.ENTITLEMENT)
        return now, (approval.scope, approval.authorization_scope, page_key)

    def get(self, approval: RetentionApproval, *, page_key: str) -> Page | None:
        if self._policy is None:
            return None
        _, key = self._admit(approval, page_key)
        entry = self._entries.get(key)
        return entry[1] if entry else None

    def put(self, approval: RetentionApproval, page: Page, *, page_key: str) -> None:
        policy = self._policy
        if policy is None:
            return
        now, key = self._admit(approval, page_key)
        if type(page) is not Page:
            fail()
        if len(page.data) > policy.max_bytes or page.row_count > approval.scope.request.max_rows:
            fail(SourceErrorCode.LIMIT)
        old = self._entries.pop(key, None)
        if old:
            self._bytes -= len(old[1].data)
        while len(self._entries) >= policy.max_entries or self._bytes + len(page.data) > policy.max_bytes:
            _, (_, evicted) = self._entries.popitem(last=False)
            self._bytes -= len(evicted.data)
        self._entries[key] = (min(now + policy.ttl_ns, approval.expires_ns), page)
        self._bytes += len(page.data)

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0
