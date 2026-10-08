"""Serial cooperative acquisition with exact integer budgets and safe failures."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import NoReturn, Protocol

from equity_feature_contracts.adapters import AcquisitionRequest, SourceError, SourceErrorCode
from equity_feature_contracts.inputs import I64_MAX
from equity_feature_io_contracts.factories import CredentialProvider


def fail(code: SourceErrorCode = SourceErrorCode.SCHEMA) -> NoReturn:
    # Called outside handlers: sensitive exceptions cannot enter __context__.
    raise SourceError(code, "Acquisition stopped: " + code.value)


def integer(value: int, *, zero: bool = False) -> None:
    if type(value) is not int or not (0 if zero else 1) <= value <= I64_MAX:
        fail()


def identity(value: str) -> None:
    if type(value) is not str or not value.strip():
        fail()


@dataclass(frozen=True, repr=False)
class AcquisitionScope:
    request: AcquisitionRequest
    provider: str
    dataset: str
    endpoint: str
    mode: str
    source_revision: str
    mapping_revision: str

    def __post_init__(self) -> None:
        if type(self.request) is not AcquisitionRequest:
            fail()
        for value in (self.provider, self.dataset, self.endpoint, self.source_revision, self.mapping_revision):
            identity(value)
        if self.mode not in ("historical", "live", "file"):
            fail()


@dataclass(frozen=True)
class AcquisitionLimits:
    max_calls: int
    max_rows: int
    max_bytes: int
    max_elapsed_ns: int
    max_cost_micro_usd: int = 0

    def __post_init__(self) -> None:
        for value in (self.max_calls, self.max_rows, self.max_bytes, self.max_elapsed_ns):
            integer(value)
        integer(self.max_cost_micro_usd, zero=True)


@dataclass(frozen=True, repr=False)
class DownloadApproval:
    scope: AcquisitionScope
    authorization_scope: str
    expires_ns: int
    limits: AcquisitionLimits

    def __post_init__(self) -> None:
        if type(self.scope) is not AcquisitionScope or type(self.limits) is not AcquisitionLimits:
            fail()
        identity(self.authorization_scope)
        integer(self.expires_ns)
        if self.limits.max_rows > self.scope.request.max_rows:
            fail()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    initial_backoff_ns: int = 100_000_000
    maximum_backoff_ns: int = 1_000_000_000
    cancellation_poll_ns: int = 100_000_000

    def __post_init__(self) -> None:
        for value in (self.max_attempts, self.initial_backoff_ns, self.maximum_backoff_ns, self.cancellation_poll_ns):
            integer(value)
        if self.initial_backoff_ns > self.maximum_backoff_ns:
            fail()


@dataclass(frozen=True, repr=False)
class Page:
    data: bytes
    row_count: int

    def __post_init__(self) -> None:
        if type(self.data) is not bytes:
            fail()
        integer(self.row_count, zero=True)


@dataclass(frozen=True)
class AttemptBudget:
    ordinal: int
    deadline_ns: int
    remaining_rows: int
    remaining_bytes: int


class AttemptFailure(Exception):
    """Trusted transport report; accepts no raw provider exception message."""
    def __init__(self, code: SourceErrorCode, *, received_bytes: int = 0, retry_after_ns: int = 0) -> None:
        if type(code) is not SourceErrorCode:
            fail()
        integer(received_bytes, zero=True)
        integer(retry_after_ns, zero=True)
        self.code = code
        self.received_bytes = received_bytes
        self.retry_after_ns = retry_after_ns
        super().__init__("Acquisition attempt failed")


class Transport(Protocol):
    def __call__(self, credential: str | None, budget: AttemptBudget) -> Page: ...


@dataclass(frozen=True)
class Ledger:
    calls: int = 0
    received_bytes: int = 0
    rows: int = 0
    reserved_cost_micro_usd: int = 0


class AcquisitionController:
    """One caller-authorized scope and cumulative ledger; no implicit operations."""
    def __init__(self, approval: DownloadApproval | None, *, clock_ns: Callable[[], int],
                 sleep_ns: Callable[[int], None], cancelled: Callable[[], bool],
                 retry: RetryPolicy = RetryPolicy()) -> None:
        if approval is not None and type(approval) is not DownloadApproval:
            fail()
        if type(retry) is not RetryPolicy:
            fail()
        self._approval = approval
        self._clock = clock_ns
        self._sleep = sleep_ns
        self._cancelled = cancelled
        self._retry = retry
        self._ledger = Ledger()
        self._last = 0
        self._started = self._now()
        self._lock = Lock()

    def __repr__(self) -> str:
        return "AcquisitionController(<opaque>)"

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    def _now(self) -> int:
        value = -1
        try:
            value = self._clock()
        except Exception:
            pass
        integer(value, zero=True)
        if value < self._last:
            fail()
        self._last = value
        return value

    def _admit(self, scope: AcquisitionScope) -> tuple[DownloadApproval, int]:
        approval = self._approval
        if approval is None or type(scope) is not AcquisitionScope or scope != approval.scope:
            fail(SourceErrorCode.ENTITLEMENT)
        cancellation: bool | None = None
        try:
            cancellation = self._cancelled()
        except Exception:
            pass
        if type(cancellation) is not bool:
            fail()
        if cancellation:
            fail(SourceErrorCode.CANCELLED)
        now = self._now()
        deadline = min(approval.expires_ns, self._started + approval.limits.max_elapsed_ns)
        if now >= deadline:
            fail(SourceErrorCode.LIMIT)
        return approval, deadline

    def execute(self, scope: AcquisitionScope, transport: Transport, *,
                cost_upper_micro_usd: int | None, idempotent: bool = False,
                credentials: CredentialProvider | None = None, credential_name: str | None = None) -> Page:
        if not self._lock.acquire(blocking=False):
            fail(SourceErrorCode.LIMIT)
        try:
            return self._execute(scope, transport, cost_upper_micro_usd, idempotent, credentials, credential_name)
        finally:
            self._lock.release()

    def _execute(self, scope: AcquisitionScope, transport: Transport, cost: int | None,
                 idempotent: bool, credentials: CredentialProvider | None, credential_name: str | None) -> Page:
        approval, _ = self._admit(scope)
        if cost is None:
            fail(SourceErrorCode.ENTITLEMENT)
        integer(cost, zero=True)
        if type(idempotent) is not bool or (credentials is None) != (credential_name is None):
            fail()
        if credential_name is not None:
            identity(credential_name)
        backoff = self._retry.initial_backoff_ns
        for attempt in range(1, self._retry.max_attempts + 1):
            approval, deadline = self._admit(scope)
            limits, ledger = approval.limits, self._ledger
            if (ledger.calls >= limits.max_calls or ledger.rows >= limits.max_rows or
                    ledger.received_bytes >= limits.max_bytes or ledger.reserved_cost_micro_usd + cost > limits.max_cost_micro_usd):
                fail(SourceErrorCode.LIMIT)
            secret: str | None = None
            credential_failed = False
            if credentials is not None and credential_name is not None:
                try:
                    secret = credentials.get(credential_name)
                except Exception:
                    credential_failed = True
                if credential_failed or type(secret) is not str or not secret:
                    fail(SourceErrorCode.AUTHENTICATION)
            _, deadline = self._admit(scope)
            self._ledger = Ledger(ledger.calls + 1, ledger.received_bytes, ledger.rows, ledger.reserved_cost_micro_usd + cost)
            budget = AttemptBudget(self._ledger.calls, deadline, limits.max_rows - ledger.rows, limits.max_bytes - ledger.received_bytes)
            page: Page | None = None
            error: SourceErrorCode | None = None
            received, retry_after, retryable = 0, 0, False
            try:
                page = transport(secret, budget)
            except AttemptFailure as exc:
                error, received, retry_after = exc.code, exc.received_bytes, exc.retry_after_ns
                retryable = True
            except SourceError as exc:
                error = exc.code
            except Exception:
                error = SourceErrorCode.TRANSPORT
            # No caught exception object survives into a public failure.
            secret = None
            if error is not None and (type(error) is not SourceErrorCode or type(received) is not int or type(retry_after) is not int or received < 0 or retry_after < 0):
                fail()
            if error is None:
                if type(page) is not Page:
                    fail()
                received = len(page.data)
            ledger = self._ledger
            rows = ledger.rows + (page.row_count if page is not None and error is None else 0)
            self._ledger = Ledger(ledger.calls, ledger.received_bytes + received, rows, ledger.reserved_cost_micro_usd)
            if self._ledger.received_bytes > limits.max_bytes or rows > limits.max_rows:
                fail(SourceErrorCode.LIMIT)
            self._admit(scope)
            if error is None and page is not None:
                return page
            if error is None:
                fail()
            if not (retryable and idempotent and error in (SourceErrorCode.RATE_LIMIT, SourceErrorCode.TRANSPORT) and attempt < self._retry.max_attempts):
                fail(error)
            delay = max(backoff, retry_after)
            _, deadline = self._admit(scope)
            target = self._now() + delay
            if target >= deadline:
                fail(SourceErrorCode.LIMIT)
            while self._now() < target:
                self._admit(scope)
                before = self._now()
                duration = min(self._retry.cancellation_poll_ns, target - before)
                sleep_failed = False
                try:
                    self._sleep(duration)
                except Exception:
                    sleep_failed = True
                if sleep_failed or self._now() <= before:
                    fail()
                self._admit(scope)
            backoff = min(backoff * 2, self._retry.maximum_backoff_ns)
        fail(SourceErrorCode.LIMIT)
