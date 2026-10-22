# EF1 supplied multi-venue status conversion - EQ212 / EQ165

This source candidate maps SUPPLIED multi-venue facts (the expected-publisher
population, per-publisher status states, seeds, prefix and validity certificates)
into the five fixed roles of the frozen `ef1-multivenue-status1` contract (core
`docs/ef1/MULTI_VENUE_STATUS_CONTRACT_PROPOSAL.md`). It contains no population,
precedence, age, count or clock mathematics, no venue arbitration and no
acquisition. The single-publisher `status` adapter is unchanged and is never
aliased. Adapter and package versions are unchanged; source authoring is distinct
from reviewed, tested, qualified, released or completed delivery.

```python
from equity_feature_duckdb.venue_status import (
    VenueStatusInputs, make_venue_batch, make_multivenue_status_config,
    make_venue_population_reference_id, make_venue_seed_reference_id,
    make_venue_state_reference_id, make_venue_certificate_reference_id,
    synthetic_venue_status_config, synthetic_venue_status_fixture,
    SYNTHETIC_VENUE_STATUS_CASES,
)

inputs = synthetic_venue_status_fixture("MV05")
config = synthetic_venue_status_config("MV05")
assert inputs.roles == ("venue_population", "venue_seed", "venue_states",
                        "venue_prefix", "venue_validity")
# compute_ef1(inputs.slots, config, entity=EntityKey("X", "S")) takes five positions, incl. None.
```

- `make_venue_batch(rows, *, metadata, instrument_id, session_id)` converts exact
  supplied rows, each the six original cells reference_id, fact_kind,
  effective_start_ns, effective_end_ns, text, known_at_ns, into a REFERENCE batch with
  the two leading target-binding columns. Order, cells and metadata (including the
  caller's Coverage and SourceBinding) are retained. Nothing is sorted, filtered,
  filled or checked against the vocabularies; admission, duplicates, epoch, revision,
  snapshot and publisher checks belong to the pure producer. A zero-row batch is
  present-empty with its own coverage; `None` is missing delivery.
- The four reference-id encoders only format identities the caller supplied:
  `vp1:B(population_id):B(revision):B(publisher)`, `vs1:D:B(epoch):B(publisher):seq19`,
  `v1:D:B(epoch):B(publisher):seq19:B(event_id)` and
  `vc1:D:B(epoch):B(publisher):B(P):B(certificate_id)` (prefix and validity share the
  grammar; P is the actual states input_id). B is unpadded base64url of UTF8, D is
  t/q/s for trading/quoting/ssr, seq19 is the 19-digit zero-padded nonnegative int64
  semantic sequence (bool and overflow refuse). The 128 codepoint / 512 byte limit is
  enforced. Binding P to the actual input, text, order and vocabulary stay with the producer.
- `make_multivenue_status_config(*, population_id, population_revision, epoch,
  precedence, clock_dimensions, max_age_ns, session, window, availability,
  policy_id="venue_precedence_v1", policy_version="1")` builds the
  `ef1.multivenue_status` ConfigSpec (v1/schema 1, one `ef1_context_json`, calendar
  null, price unit null, raw adjustment, canonical ASCII JSON). The precedence order has
  no default; the permutation, dimension and range rules (`invalid_config`) belong to the
  pure decoder, so malformed values pass through.
- `VenueStatusInputs(venue_population=None, venue_seed=None, venue_states=None,
  venue_prefix=None, venue_validity=None, provenance=("unavailable",)*5)` exposes five
  fixed nullable `.slots` in `.roles` order; `.batches` is the present-only
  subsequence. Duplicate input IDs, differing namespaces, non-REFERENCE batches and
  origins that disagree with delivery refuse. It does not compare epoch, source or
  snapshot across slots (the producer refuses conflicts, e.g. RF04).
- `SYNTHETIC_VENUE_STATUS_CASES` lists the contract's own 42 result fixture ids
  (MV01..MV37, MV40..MV44; there is no MV38/MV39).
  `synthetic_venue_status_fixture(case_id)` and `synthetic_venue_status_config(case_id)`
  return the fixture's exact slots (expected population and fact rows, missing and
  covered-empty slots, declared coverage) and its context selection, availability
  (C, K, mode) and precedence. Entity is SYN/X/S, session [0, 100), evaluation time 100,
  reconstruction label `synthetic replay`. They embed no expected values and calculate
  nothing; the worker layer compares with the contract. The 13 refusal fixtures
  RF01..RF13 are not provided here.

Policy id: the contract JSON writes `FP` in all 55 fixtures, while the contract text
(D03) fixes `venue_precedence_v1`. The config builder and synthetic configs use the
normative `venue_precedence_v1`/`1`; see the I/O checkpoint.

Origins are `synthetic`, `duckdb_backed_observed` or `unavailable`; unavailable
corresponds exactly to absence. Observed is a caller declaration, not proof of rights.

The adapter never sorts, filters, repairs, derives a count or aggregate, shrinks the
expected population, infers a publisher, seed or certificate, or reads the
single-publisher status path. The existing DuckDB sink, SDK, codec and versions are
reused; whether the new units `publishers` and `boolean`, bool and int64 clock
values round-trip there is verified only when executed.

[Executable synthetic example](../../examples/ef1_venue_status.py) uses `.slots` with
`compute_ef1`. See [validation and remaining gates](../EF1_VENUE_STATUS_IO.md).
