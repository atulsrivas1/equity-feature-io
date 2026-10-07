# BUG-005 — coherent Parquet publication observation

Canonical [issue301](https://github.com/atulsrivas1/equity-features/issues/301), E08/R5 prerequisite, provisional3points. Owner requested repair after post-delivery R4.1 review. Historical accepted versions/receipts stay preserved. No worker implementation or mathematical change.

## Design before implementation

Read immutable completion before its reservation binding. A cooperating writer creates/replaces reservation before publishing completion and never replaces either after commitment. Therefore observing completion first establishes a stable attempt whose reservation can then be validated without a mixed precommit snapshot. When completion is absent, lookup may return the factual reservation state observed during the operation; a later lookup discovers a concurrently committed receipt. No lock or unbounded retry is added to readers.

Remove the reservation helper's cross-file absence/completion test: absence can legitimately precede first publication. Stable completion with missing reservation remains corruption when validated by the completion reader. Do not remove envelope/attempt/key/digest/component validation or admit staged files as committed. Existing writer lock, commit uncertainty, immutable components, replay/conflicts and storage format stay unchanged.

Package the corrected backend as equity-feature-parquet0.1.0a1; canonical/I/O SDK/source/DuckDBsink/extensions/workers versions and algorithms remain unchanged. Update current composition version expectations; preserve historical accepted .a0 archive bindings. Existing matrix archive equality applies only to unchanged packages, and the changed package requires fresh repeat-build/native/install evidence.

## Independent tests

Deterministically schedule real publication across lookup control reads with ABSENT, ABORTED and abandoned STAGING predecessors. Also schedule publication between reservation-path existence and subsequent observation. Accept only a factual precommit state or fully verified COMMITTED, never false CORRUPTION; subsequent lookup/full result/receipt replay must match independent synthetic facts. Stable missing reservation and mismatched attempt/envelope/completion/components remain CORRUPTION. Prove the regressions fail against the accepted old source before validating the fix.

Run physical and eight process cases, strict public typing, independent composed source-result-sink checks and clean wheel/sdist qualification in supported native CI. Inspect actual artifacts/source/test/probe hashes and producer identities, finite expiry and actual-main readback before Done. No private rerun is needed for this output-only fix; no performance/power-loss/network-filesystem certification claim.

## Documentation and accepted end state

Update backend API/recovery/README/changelog/compatibility and both repositories' knowledge/handoff with failure, fix, reviewer identity and exact delivery evidence. Resolve BUG005 only after applicable separate final-head review, all required CI, actual published artifacts/install/readback and lifecycle gates. Then restore EQ057 Ready with corrected versions and R5 handoff dependency record; stop before worker implementation to discuss next work with the owner. The pre-code pending local-review question is superseded by the owner's explicit bounded BUG005 review request, recorded in AGENTS/CODE_REVIEW; general R5 remains outside that authorization.
