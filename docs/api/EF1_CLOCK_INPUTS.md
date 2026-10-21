# EF1 supplied calendar proof source — EQ212 / EQ165 clock subset

This additive source-authoring slice follows frozen `ef1-contract1`. It supports
the reviewed clock subset of EQ165#505 through I/O EQ212#570; status feeds and
other source families are outside this slice. Existing anchor APIs and fixtures
are retained. Adapter remains the same unreleased0.1.0a9 candidate, canonical
contracts0.0.4a4 and existing SDK/sink versions remain unchanged.

Explicit public imports:

```python
from equity_feature_duckdb.ef1 import (
    ClockInputs, calendar_definition_bytes, make_calendar_provenance,
    synthetic_clock_calendar, synthetic_clock_fixture,
)

calendar = synthetic_clock_calendar()
packet = synthetic_clock_fixture(known_at_ns=5)
# Actual REFERENCE input in fixed transport role order:
assert packet.roles == ("calendar_provenance",)
assert packet.batches == (packet.calendar_provenance,)
missing = ClockInputs(None, "unavailable")
```

The original literal C01 calendar is explicitly supplied: calendar_id C01,
revision R1, timezone UTC, target_date2026-01-02, session S[10,30), premarket[0,10),
regular[10,30), postmarket[30,40), scheduled_close_ns40 and early_close true.
These are toy integer UTC nanoseconds and fictional schedule facts; they do not
certify exchange truth. Each call returns fresh owned schedule containers.

`calendar_definition_bytes(calendar)` validates and detaches the exact eight
fields calendar_id/revision/timezone/target_date/sessions/segments/
scheduled_close_ns/early_close, then returns sorted compact ASCII JSON with
ensure_ascii true, no extra whitespace and no nonfinite values. Arrays preserve
supplied order. Sessions and segments must be concrete bounded ordered disjoint
rows, with unique IDs/phases; regular bounds match the supplied target session
and scheduled/early-close operands agree. ISO dates are parsed as supplied;
there is no date generation, timezone-offset inference or wall-time read.
The standalone byte bound is4096; this does not prove the enclosing mathematical
context or complete worker task fits its separate unchanged wire bounds.

`make_calendar_provenance(calendar, *, namespace, instrument_id, session_id,
source_id, input_id, known_at_ns, start_ns, end_ns)` converts an **actual supplied
declaration** into one canonical REFERENCE row. Its fields are:

| Field | Exact mapping |
| --- | --- |
| reference_id | c1: followed by lowercase SHA256 of the exact canonical calendar bytes |
| fact_kind / text | ef1.calendar.provenance / supplied_schedule |
| effective_start_ns / effective_end_ns | Original supplied positive finite interval covering every supplied session and segment bound |
| known_at_ns | Original exact int64 availability or null; future/unknown stays unchanged |
| source.snapshot_id | Exact calendar revision |
| source.mapping_version | ef1-reference-map1 |
| source_id / input_id / target | Actual caller identities, never inferred from a path or current clock |

The hash includes scheduled_close_ns and early_close. Changing either schedule
operand changes the bound identity; contradictory operands reject. No price or
factor payload fields are introduced. Proof interval scope covers supplied
schedule intervals, so coverage equality at either end is admitted; the library
may evaluate C=40 from C01's proof[0,40), whose calendar covers that schedule.
This scope does not invent ongoing feed validity or authenticate the source.

`ClockInputs(actual_proof, mode)` preserves the complete actual batch metadata.
Mode is explicitly synthetic or duckdb_backed_observed; missing proof must use
unavailable and produces no batch. Packet admission checks canonical transport
shape; the pure clock library validates exact hash, revision, target, coverage
and cutoff-relative availability. No fallback labels a stored observation
synthetic or manufactures an availability time. The original synthetic fixture
supplies source F/snapshot R1/namespace SYN/instrument X/session S/input_id
synthetic-clock-C01, complete1/1 proof population, scope[0,40) and known-at5.
No N: dataset, source calendar authority or publication rights has been qualified.

Workers select one homogeneous clock/config task, one calendar_provenance slot
and the original five scalar outputs from the library. Mathematical context has
the supplied schedule/selection only; acquired proof stays in the real input
binding. The numerical package owns clock mathematics and missingness. There is
no feature math, fetching, provider access or output publication in this source
module. Existing sink readback retains full canonical bytes, quality, input
identities and evidence. No new result codec or schema is needed.

Authored checks: `tests/ef1/test_clock_inputs.py` covers independent literal JSON,
hash identity, original known-at, whole-schedule proof scope, shape/target and
explicit provenance. `tests/ef1/test_clock_composition.py` supplies independent
C01 results at C10/20/30/40, missing/unknown/future proofs and candidate library
result-to-existing-sink full-byte readback/replay/sequential reopen. Its explicit
limits are one result,1MiB chunk and total bytes,5 cells and128 evidence rows.
Existing anchor checks remain present. No test, import, typecheck, build,
benchmark or database operation has executed in this source-authoring slice;
the official R18 study retains its resource reservation. Source changes require
coordinator review, independent recheck and actual compatible CI/artifact/runtime
qualification before acceptance. Original19 extraction hashes/guards are retained;
only the additive EF1 module's declared evolution hash changes.
