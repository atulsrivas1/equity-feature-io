# EF1 supplied current-state status conversion — EQ212 / EQ165 subset

This source candidate implements the frozen `ef1-contract1` supplied current-state
status mapping plus reviewed `STATUS_INPUT_SLOTS.md` clarification. It adds no
status history, venue arbitration, open-delay inference or provider acquisition.
EQ164 full audit, EQ165 residual scope and actual EF1 release gates remain open.
Adapter version stays unreleased0.1.0a9; canonical contracts0.0.4a4, feature candidate
0.0.4a5 and existing result/sink codecs are unchanged. Source authoring is distinct
from reviewed, tested, qualified, released or completed delivery.

```python
from equity_feature_duckdb.ef1 import (
    StatusState, StatusCertificate, StatusInputs,
    make_status_states, make_status_proof,
    synthetic_status_context, synthetic_status_fixture,
)

packet = synthetic_status_fixture(case="S01")
context = synthetic_status_context(case="S01")
assert packet.roles == (
    "calendar_provenance", "status_states", "status_prefix", "status_validity")
# Direct pure calls receive exactly four positions, including None:
# compute_ef1(packet.slots, configured, entity=entity)
# Worker transport carries packet.batches and its complete/missing manifests.
missing = StatusInputs(None, None, None, None, ("unavailable",) * 4)
```

`StatusInputs` is frozen. Each named role contains its original CanonicalBatch or
None. `.slots` retains all four positions; `.batches` retains only present original
objects in role order. Zero rows is a present population with actual metadata,
not missing delivery. A partial packet never shifts later roles or fabricates
replacement inputs. Result bindings retain the library's canonical lexical role
order, independently of the local/worker declaration order. Unknown expected
population counts stay unknown, and incomplete coverage is not promoted.

`provenance` is an exact four-string tuple in the same order. Each value is
`synthetic`, `duckdb_backed_observed` or `unavailable`; unavailable iff its slot is
None. Present states/prefix/validity use one common provenance mode. Synthetic
proof cannot attest observed state; actual stored observations retain their
observed label. Calendar provenance/source may differ from the status publisher.
These labels record caller-supplied origin, not authentication or dataset rights.
No existing N: database has been inspected or admitted by this change.

`make_status_states(rows, *, dimension, epoch, metadata, instrument_id, session_id)`
accepts an exact tuple of `StatusState(sequence, event_id, effective_start_ns,
effective_end_ns, text, known_at_ns)`. The caller supplies actual publisher
sequence, event ID, epoch, original event/validity times, knowledge and complete
BatchMetadata, including explicit Coverage and source identity. No default row
count proves message completeness. Observed count must match actual rows.

| Dimension / D | Allowed original text | fact_kind |
| --- | --- | --- |
| trading / t | active, halted, closed | ef1.status.trading |
| quoting / q | enabled, disabled | ef1.status.quoting |
| ssr / s | on, off | ef1.status.ssr |

The identity is exactly `s1:D:B(epoch):seq19:B(event_id)`. Sequence is a nonnegative
int64, exactly19 decimal digits padded with zeroes; bool and overflow reject.
Sequence strictly increases, effective times do not decrease, and equal-time
publisher ties preserve their supplied sequence. No sorting, renumbering or
event generation occurs. Sequence gaps alone have no missing-message meaning.

`make_status_proof(rows, *, role, dimension, epoch, target_input_id, metadata,
instrument_id, session_id)` accepts original `StatusCertificate(certificate_id,
effective_start_ns, effective_end_ns, known_at_ns)` tuples for a dedicated
status_prefix or status_validity role. Its identity is
`p1:D:B(epoch):B(target_input_id):B(certificate_id)`, text D and fact_kind
`ef1.status.prefix_complete` or `ef1.status.validity`. The interval is positive
finite; knowledge stays its original exact int64 value or null. Prefix and
validity are distinct real inputs and may use the same original certificate ID.

B is reversible strict UTF8 base64url, unpadded. Decoding checks alphabet, strict
UTF8, safe decoded label and exact re-encoding, including pad-bit canonicality.
Safe status labels are nonblank strings bounded at128 codepoints/512 UTF8 bytes;
C0 characters, DEL and surrogates reject. This matches canonical status admission;
it does not claim all Unicode control categories are excluded. Combined IDs obey
the same bound; overflow rejects without truncation or hashing away original IDs.
Actual worker string/task bounds still apply independently, so maximal labels
are not promised to fit every manifest. Every status role uses mapping version
`ef1-reference-map1` with no numerical payload columns. The full actual metadata
is retained. Wrong populated role vocabulary rejects rather than inferring roles.

States and certificates bind one dimension/epoch. All present proofs refer to
actual states input_id, namespace, instrument/session, source_id and snapshot_id;
proof input_ids are distinct from each other and the states input_id. If states
are missing, present proofs must still declare a coherent target/source/revision,
without inventing the missing state's actual binding. Calendar revision/source
is separate and uses the existing actual c1 supplied-schedule proof. An empty
batch retains its caller-assigned role because no row vocabulary exists to infer
an alternative role. Sum of all present reference rows, including calendar and
certificates, is at most4096. Context4096, actual task1MiB and evidence128 limits
remain separate unchanged gates.

The adapter performs representation and identity validation. The pure library
owns cutoff/knowledge eligibility, proof applicability, quality, diagnostic
precedence, selected witnesses and all status mathematics. In particular:

- Current event is the last original selected transition with event time<C, only
  after the explicit original seed, complete prefix and required transition
  knowledge are proved. Every required original known_at must be nonnull and<=K
  in both known_at and reconstruction modes; late transitions never fall back.
- A prefix certificate individually covers seed effective time through C:
  start<=seed_time and C<=end. A validity certificate individually contains C:
  start<=C<end. Fragments cannot be stitched, and multiple applicable proofs
  reject DUPLICATE without knowledge-based arbitration.
- Age is C minus the proved original current event time, in exact UTC nanoseconds.
  No implicit age expiry exists. Explicit max_age rejects state only when age
  exceeds the maximum; proved descriptive age remains available. Missing prefix
  or transitions prevents dependent expiry/age claims.
- Diagnostic admission_state/reason readiness is distinct from factual readiness.
  State/age witnesses retain exact original input_id, reference_id, event time,
  known_at and effective bounds; no unproved last-observed witness is emitted.

`synthetic_status_fixture/context(case='S01'|'S02'|'S03')` supplies original
public toy UTCns examples, with source F/snapshot R1/namespace SYN/X/S and actual
states input_id st. Every context explicitly selects its original seed ID; no
first-row inference. Context has selection and supplied C01 calendar only.
Calendar is C01/R1 UTC, target2026-01-02, pre[0,10), regular[10,30), post[30,40),
scheduled_close40/early_close true, bound by the actual c1 proof[0,40), known_at5.

| Case | Original events | Prefix / validity | Independent expected query |
| --- | --- | --- | --- |
| S01 trading | seed active@8/seq0, halt halted@12/seq1, resume active@16/seq2, known_at equals each time | [8,20) / [8,21), known_at8 | C16/K16 halted/age4; C17/K17 active/age1; C17/K15 both unavailable/future_knowledge |
| S02 ssr | seed on@5/seq0, known_at5 | [5,16) / [5,17), known_at5 | C16 age11 stays on; max10 rejects only state; C17 incomplete_status_prefix without dependent expiry |
| S03 ssr | a on@5/seq0, b off@5/seq1, known_at5 | [5,20) / [5,21), known_at5 | C6/K6 off/age1 using original b witness |

Authored tests `tests/ef1/test_status_inputs.py` assert literal reference identities,
original facts, malformed encoding/order/identity, missing/empty/partial populations
and explicit provenance. `tests/ef1/test_status_composition.py` hand-authors its own
canonical inputs/context/goldens, invokes the library with `.slots`, checks quality,
original witnesses, missing roles, expiry, knowledge, proof ambiguity/fragments and
actual helper composition. It also authors full canonical byte comparison through
existing DuckDBSink publication, replay, lookup and closed sequential reopen for
available, unavailable, partially missing and stale-state results. No output is
relabelled, concatenated or given a replacement config/input digest.

No local import, syntax check, test, build, benchmark or DB/N: operation executed
under the separate EQ142 reservation. Coordinator review, fresh independent review,
current-head remote CI, actual artifacts/integration and browser demo remain
mandatory. Existing anchor/clock source prefix and original19 extraction guard
records remain unchanged; only the additive EF1 source evolution hash is refreshed.
