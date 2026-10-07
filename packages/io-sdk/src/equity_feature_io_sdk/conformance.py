"""Reusable logical sink checks on caller-provided isolated destinations."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import functools
from typing import Literal

from equity_feature_contracts.results import FeatureResult
from equity_feature_io_contracts import FactoryError, SinkRequirements
from equity_feature_io_contracts.publication import (
    CompletionReceipt, PublicationState, ResultSink, SinkError, SinkErrorCode, WriteSession,
)
from .codec import encode_result, idempotency_key
from .factories import admit_sink
from .publication import prepare_publication, publish, verify_receipt


@dataclass(frozen=True)
class ConformanceCase:
    name: str
    expected: str
    observed: str

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


@dataclass(frozen=True)
class SinkConformanceReport:
    cases: tuple[ConformanceCase, ...]
    backend_durability_certification: bool = False

    @property
    def passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)


def qualify_sink(factory: Callable[[], ResultSink], results: tuple[FeatureResult, ...],
                 limits: SinkRequirements, *, staging_recovery: Literal["busy", "restart"] = "busy") -> SinkConformanceReport:
    """Factory must create a NEW isolated destination each call. Uses synthetic supplied facts.

    This suite makes real begin/write/commit/read calls. The caller owns cleanup and
    backend/process/retention qualification; no hidden scheduling or universal guarantees.
    At least one complete result is required, including an observed-empty result if needed.
    """
    if not results:
        raise SinkError(SinkErrorCode.INVALID_CONFIG)
    if staging_recovery not in ("busy", "restart"):
        raise SinkError(SinkErrorCode.INVALID_CONFIG)
    envelope = prepare_publication(results, destination_scope="synthetic-conformance", generation_id="generation1",
                                   job_id="job1", partition_id="partition1", limits=limits)
    key = idempotency_key(envelope.identity)
    cases: list[ConformanceCase] = []

    def check(name: str, expected: str, operation: Callable[[], str]) -> None:
        try:
            observed = operation()
        except SinkError as error:
            observed = error.code.value
        except FactoryError:
            observed = SinkErrorCode.UNSUPPORTED_CAPABILITY.value
        except Exception:
            observed = "unexpected_error"
        cases.append(ConformanceCase(name, expected, observed))

    def begin(sink: ResultSink) -> WriteSession:
        session = sink.begin(envelope)
        if isinstance(session, CompletionReceipt):
            raise SinkError(SinkErrorCode.CORRUPTION)
        return session

    def roundtrip() -> str:
        sink = factory()
        receipt = publish(sink, envelope, results)
        observed = sink.read(receipt)
        verify_receipt(receipt, envelope, observed)
        return "exact" if tuple(map(encode_result, observed)) == tuple(map(encode_result, results)) else "content_mismatch"

    def replay() -> str:
        sink = factory()
        receipt = publish(sink, envelope, results)
        return "original" if sink.begin(replace(envelope, caller_created_at_ns=99)) == receipt else "changed"

    def committed_lookup() -> str:
        sink = factory()
        receipt = publish(sink, envelope, results)
        status = sink.lookup(key)
        return "original" if status.state is PublicationState.COMMITTED and status.receipt == receipt else "wrong_state"

    def conflict(state: str) -> str:
        sink = factory()
        if state == "committed":
            publish(sink, envelope, results)
        else:
            session = begin(sink)
            if state == "aborted":
                sink.abort(session)
        sink.begin(replace(envelope, expected_content_sha256="0" * 64 if envelope.expected_content_sha256 != "0" * 64 else "1" * 64))
        return "accepted_conflict"

    def staging() -> str:
        sink = factory()
        begin(sink)
        state = sink.lookup(key)
        return state.state.value if state.receipt is None else "premature_receipt"

    def busy() -> str:
        sink = factory()
        original = begin(sink)
        restarted = sink.begin(envelope)
        if staging_recovery == "restart" and not isinstance(restarted, CompletionReceipt) and restarted is not original:
            try:
                sink.write(original, 0, results[0])
            except SinkError as error:
                status = sink.lookup(key)
                return "exclusive_restart" if error.code is SinkErrorCode.INVALID_SESSION and status.state is PublicationState.STAGING and status.receipt is None else "incorrect_restart"
        return "multiple_owners"

    def aborted_retry() -> str:
        sink = factory()
        session = begin(sink)
        a = sink.abort(session)
        b = sink.abort(session)
        new = sink.begin(envelope)
        return "new_attempt" if a == b and a.state is PublicationState.ABORTED and not isinstance(new, CompletionReceipt) and new is not session and sink.lookup(key).state is PublicationState.STAGING else "incorrect_retry"

    def abort_commit() -> str:
        sink = factory()
        session = begin(sink)
        for ordinal, result in enumerate(results):
            sink.write(session, ordinal, result)
        receipt = sink.commit(session)
        outcome = sink.abort(session)
        return "preserved" if outcome.state is PublicationState.COMMITTED and outcome.receipt == receipt and sink.lookup(key).receipt == receipt else "retracted"

    def zero() -> str:
        sink = factory()
        empty = prepare_publication((), destination_scope="synthetic-conformance", generation_id="empty", job_id="job", partition_id="partition", limits=limits)
        receipt = publish(sink, empty, ())
        verify_receipt(receipt, empty, sink.read(receipt))
        return "zero" if receipt.result_count == receipt.cell_count == receipt.evidence_count == receipt.content_bytes == 0 else "fabricated"

    def version() -> str:
        sink = factory()
        sink.begin(replace(envelope, codec_version="codec2"))
        return "unsupported_version_accepted"

    def multiwriter() -> str:
        sink = factory()
        mode = "single_writer" if sink.capabilities().writer_mode == "conflict_safe_multi_writer" else "conflict_safe_multi_writer"
        admit_sink(sink, replace(limits, writer_mode=mode))
        return "unsupported_mode_accepted"

    def ordinal(duplicate: bool) -> str:
        sink = factory()
        session = begin(sink)
        if duplicate:
            sink.write(session, 0, results[0])
        sink.write(session, 0 if duplicate else 1, results[0])
        return "ordinal_accepted"

    def foreign() -> str:
        first, second = factory(), factory()
        session = begin(first)
        begin(second)
        second.write(session, 0, results[0])
        return "foreign_accepted"

    def partial() -> str:
        sink = factory()
        sink.commit(begin(sink))
        return "partial_accepted"

    def limit() -> str:
        sink = factory()
        session = sink.begin(replace(envelope, max_chunk_bytes=1))
        if isinstance(session, CompletionReceipt):
            return "premature_receipt"
        sink.write(session, 0, results[0])
        return "oversized_accepted"

    def descriptor_mismatch() -> str:
        sink = factory()
        session = begin(sink)
        wrong = replace(results[0], metadata=replace(results[0].metadata, backend_version="other"))
        sink.write(session, 0, wrong)
        return "descriptor_accepted"

    def receipt_tamper() -> str:
        sink = factory()
        receipt = publish(sink, envelope, results)
        sink.read(replace(receipt, content_sha256="0" * 64))
        return "tamper_accepted"

    def supersedes() -> str:
        sink = factory()
        original = publish(sink, envelope, results)
        new = replace(envelope, generation_id="generation2", supersedes_key=key)
        corrected = publish(sink, new, results)
        return "preserved" if corrected.idempotency_key != key and sink.lookup(key).receipt == original and tuple(map(encode_result, sink.read(original))) == tuple(map(encode_result, results)) else "supersession_retracted"

    check("complete_readback", "exact", roundtrip)
    check("original_replay_operational_timestamp", "original", replay)
    check("committed_lookup", "original", committed_lookup)
    for state in ("committed", "staging", "aborted"):
        check(state + "_different_content_conflict", "CONFLICT", functools.partial(conflict, state))
    check("staging_nonvisible", "STAGING", staging)
    check("exclusive_staging_policy", "BUSY" if staging_recovery == "busy" else "exclusive_restart", busy)
    check("abort_idempotence_same_content_retry", "new_attempt", aborted_retry)
    check("abort_after_commit", "preserved", abort_commit)
    check("zero_results", "zero", zero)
    check("unknown_codec", "INCOMPATIBLE_VERSION", version)
    check("unsupported_writer_requirement", "UNSUPPORTED_CAPABILITY", multiwriter)
    check("out_of_order", "INVALID_CONTENT", lambda: ordinal(False))
    check("duplicate_ordinal", "INVALID_CONTENT", lambda: ordinal(True))
    check("foreign_session", "INVALID_SESSION", foreign)
    # The design admits INVALID_CONTENT or CONFLICT for incomplete commits.
    try:
        observed = partial()
    except SinkError as error:
        observed = "no_completion" if error.code in (SinkErrorCode.INVALID_CONTENT, SinkErrorCode.CONFLICT) else error.code.value
    except Exception:
        observed = "unexpected_error"
    cases.append(ConformanceCase("partial_commit", "no_completion", observed))
    check("chunk_resource_limit", "RESOURCE_LIMIT", limit)
    check("descriptor_mismatch", "INVALID_CONTENT", descriptor_mismatch)
    check("receipt_tamper", "CORRUPTION", receipt_tamper)
    check("supersedes_preserves_original", "preserved", supersedes)
    return SinkConformanceReport(tuple(cases))
