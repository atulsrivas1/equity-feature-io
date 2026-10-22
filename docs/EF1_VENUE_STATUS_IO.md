# Multi-venue status I/O source checkpoint - October 22, 2026

Status: source authored against the frozen `ef1-multivenue-status1` contract by the
EQ212 [#570](https://github.com/atulsrivas1/equity-features/issues/570) I/O layer for
EQ165 [#505](https://github.com/atulsrivas1/equity-features/issues/505). The pure
library producer (`multivenue_status`) is authored in parallel.

Added the [supplied-input API](api/EF1_VENUE_STATUS_INPUTS.md): the exact five-role
nullable container, lossless conversion, the four reference-id encoders, the config
builder, and synthetic fixture/config builders for the contract's 42 result fixtures
(MV01..MV44). No fetching, venue arbitration, state inference, population, precedence,
age, count or clock mathematics, and no sink/SDK/version change.

Actually executed (Python 3.12, no library producer on the path): all 42 synthetic
fixtures and configs build, and every batch passes generic canonical validation;
tools/check_extraction.py with the core root exited 0.

NOT executed: compute_ef1 on the fixtures, the DuckDB sink round-trip of the new
units and types, the worker, mypy.

Contract defect for the coordinator: the 55 fixtures in
`MULTI_VENUE_STATUS_CONTRACT_PROPOSAL.json` carry `state_policy.policy_id` of `FP`,
but the contract text fixes `venue_precedence_v1` (D03, and the fixture paragraph says
fixtures use it). The synthetic configs use the normative value; the contract JSON or
text needs reconciling before the worker compares config digests.

Unspecified by the contract, chosen here only for the synthetic config and listed for
the worker: evaluation time E = 100, session [0, 100), window one `S` session
(`completed_eod`), reconstruction reason `synthetic replay`.

Remaining gates: library availability and manual run, worker and sink readback,
source-evolution declaration review, independent review, observed-source rights and release.
