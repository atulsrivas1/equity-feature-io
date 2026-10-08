# Explicit acquisition controls (experimental 0.1.0a0)

This optional companion reuses `AcquisitionRequest`, canonical `SourceErrorCode`
and the accepted I/O `CredentialProvider`. It performs no operation on import and
registers no source. Calculations, I/O contracts/SDK0.1.0a2 and workers0.1.0a12 are
unchanged. CPython3.12 Windows/Linux qualification is required before delivery.

`AcquisitionScope(request, provider, dataset, endpoint, mode, source_revision,
mapping_revision)` binds every canonical request field. `DownloadApproval(scope,
authorization_scope, expires_ns, limits)` is an explicit trusted user authorization;
credentials, feature selection, account credit and cached files never create it.
`AcquisitionController` accepts that approval or None, caller `clock_ns`, `sleep_ns`,
`cancelled` and a `RetryPolicy`. `execute(scope, transport,
cost_upper_micro_usd=..., idempotent=False, credentials=None,
credential_name=None)` admits the exact scope before credential lookup/transport.
Unknown cost rejects; zero cost ceiling admits only an explicit zero conservative
upper bound. No provider billing quote, subscription, batch submission or connection
is performed automatically. Future adapters must require user approval even for
free provider downloads. The current owner's approval covers free qualification
dependencies/artifacts only, not market data or charges.

Limits are finite integer calls, rows, received payload bytes, elapsed nanoseconds
and reserved USD millionths. The injected monotonic clock domain measures runtime,
not market or knowledge time. Approval expires exactly at its absolute deadline;
elapsed deadline starts at controller creation. Ledger persists across explicit
pages and retries. Reserve the per-attempt conservative cost before transport,
including failed attempts; no automatic refund. A zero-remaining call/row/byte budget
rejects before credentials. Rows/data above bounds or a late result are counted and
rejected. Returned `Page(bytes, row_count)` contains immutable owned bytes and a
trusted declared row count, not a canonical coverage/completeness witness.

Transport receives a secret only for the attempt and `AttemptBudget` with ordinal,
absolute deadline and remaining rows/bytes. It must stream-account actual received
bytes and respect deadlines/limits, disable hidden SDK retries, and report failed
bytes through `AttemptFailure(code, received_bytes=0, retry_after_ns=0)`. Only typed
TRANSPORT/RATE_LIMIT failures retry for explicit idempotent reads. Authentication,
entitlement, schema, cancellation and untyped exceptions terminate. Retry delay is
max(capped exponential backoff, Retry-After); a wait reaching deadline rejects
without sleep/retry. Sleeps are sliced for cancellation and must advance the
monotonic clock. Attempt/call budgets remain finite. No reconnect/pagination loop
is supplied. A controller rejects concurrent/reentrant execute calls; independent
controllers require separately allocated caller budgets. It is not a global rate
governor or a provider billing meter.

Credential lookup failures and transport exceptions become fixed canonical errors
outside their exception handler; raw exception strings/cause/context are not
retained. No logs, serialized credentials, config values, URLs or headers are
emitted. Controller/approval/scope/page/cache repr is opaque, ledger numeric. Caller
and transport code are trusted: they may log or retain their own credentials.
Python introspection/debugger capture of frame locals is not a security boundary.
Arbitrary callbacks cannot be preempted, and logical payload bounds are not hard
network-transfer/RSS/disk limits. Cancellation cannot reverse an already executed
request or accrued charge. Never infer charge consent from this mechanism.

`ImmutableCache(clock_ns=..., policy=None)` defaults to disabled: get misses and put
does nothing. Enabling requires finite `CachePolicy(max_entries,max_bytes,ttl_ns)`
and a `RetentionApproval(scope, authorization_scope, expires_ns,
immutable_revision=True)` on every read/write. This is explicit permitted local
retention/use, independent of new download consent. Keys bind full scope, opaque
authorization partition and page_key. Live/mutable/expired approvals reject.
Insertion TTL never slides on a hit and cannot outlast permission. Expired entries
are purged on enabled operations; expiry does not schedule background erasure.
Call `clear()` or dispose the cache at use-session end. Stored payload bytes/counts
are bounded; FIFO eviction and atomic replacement are deterministic. An oversized
item rejects without evicting unexpired unrelated items. No disk/network cache,
error/credential cache, rights discovery or historical-known-at certification.
Cache methods require serial caller ownership; metadata/Python memory overhead is
outside the payload cap. Opaque authorization IDs and scope metadata must contain
no credentials or private account information.

Run the owned synthetic third-party client fixture `examples/acquisition_consumer.py`
after explicit installation. It uses no network or real credential. Independent
test schedules are frozen in `tests/acquisition_goldens.json`; fresh installed
wheel/sdist forms execute the same public cases outside repository import paths.
All examples are owned synthetic. Actual SDK/provider access, entitlements and
data/cache/derived-output rights require later separately authorized qualification.
