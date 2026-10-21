# EF1 supplied sampled paths — EQ212 / EQ167 subset

Source-authored against the frozen `PATH_SOURCE_AUTHORING_FREEZE.json` amendment
(e55be33767184cafb971827f041c55933a41e7010e23a8b581f0aaa41d6667fe Markdown;
04c2743559de751d22225a2d521bd4f69eb75318f2f7e276ecde8c1bdf80a616 JSON).
This covers the original four gap and three opening-drive outputs. It is not
legacy GapFillPercent equivalence or completion of the full EF1 inventory audit.

```python
from equity_feature_duckdb.ef1 import (
    PathGapInputs, PathDriveInputs, make_path_prior_close,
    synthetic_path_gap_fixture, synthetic_path_gap_context,
    synthetic_path_drive_fixture, synthetic_path_drive_context,
)
packet = synthetic_path_gap_fixture(case="G01")
context = synthetic_path_gap_context(case="G01")
# context is the full raw EF1 context dict, not build_ef1_config keyword arguments.
assert packet.roles == ("calendar_provenance", "path", "prior_close")
# compute_ef1(packet.batches, configured, entity=entity)
missing = PathGapInputs()
assert missing.batches == ()
```

Both immutable packets expose `.roles` in declared order and `.batches` as the
present-only subsequence of the exact original CanonicalBatch objects. Empty
batches remain present; omitted batches never become fake covered-empty inputs.
`PathDriveInputs` has calendar/path slots. Path accepts TRADE or BAR; prior accepts
DAILY; calendar accepts REFERENCE. Canonical structural validation occurs before
readiness. Distinct actual input IDs and a common namespace are required.
The selected sampling, session/window/scope and all causal admission are checked
by the pure library. The adapter does not compute gap/drive mathematics.

`provenance` is an exact three- or two-string tuple, with one mode per declared
slot: `synthetic`, `duckdb_backed_observed`, or `unavailable`. Unavailable is true
iff that slot is absent. Present path/prior roles may have distinct truthful
origins and sources. These labels do not authenticate source rights or coverage.

`make_path_prior_close(row, *, metadata, instrument_id, session_id)` converts one
explicitly selected canonical DAILY row. `row` is a mapping with supplied
`start_ns` and `end_ns`; optional supplied open/high/low/close/volume/
actual_notional/known_at_ns cells are retained in canonical source-column order.
Unknown fields reject; missing fields stay absent. Caller metadata is preserved,
including coverage, unit, adjustment, auction scope and source identity. No
previous-day discovery, UTC-day interval creation, price conversion, knowledge
filling or completeness inference occurs. In particular, originally supplied
invalid volume/OHLC cells reject rather than being removed to admit a row.
Existing supplied canonical market converters can be used without weakening
their source policies; this additive helper is not source database acquisition.

Fixtures `G01`, `G02`, `G03` and `D01` are literal public synthetic populations:
G01 upward gap hits prior10; G02 bar low9 does not establish a sampled-close hit;
G03 downward gap hits prior12; D01 has trade prices10/12/11. Every call returns a
fresh context and packet. Unknown cases reject. PriceUnit(0, USD), raw adjustment,
SYN/X/S, regular[10,30), explicit prior P[-10,0) and supplied_path scopes follow
the frozen amendment. Gap window is exactly (P,S), drive exactly (S,). Default
market/knowledge/evaluation cutoffs are G01/G03=13, G02=12, D01=15 when callers
construct AvailabilitySpec. The context helper does not create these specs.

The existing output sink accepts the complete canonical FeatureResult unchanged
in a separate new output database. No schema/version/codec rewrite, source DB
inspection, N: access, private defaults, provenance authentication or numerical
parity claim is introduced. Original nineteen baseline source receipts remain
unchanged; only the additive helper's current-byte receipt is refreshed.

Authored tests: 15 input/conversion methods and 11 composition methods, including
four literal numerical goldens, an independently constructed G01 source packet,
original-knowledge controls in both modes, missing roles, coverage, endpoint
rejection and full result bytes/idempotence/reopen through the existing sink.
They have not been executed. The protected EQ142 reservation prohibits local
runtime/import/syntax/tests/build/benchmark/database operations. Review, actual
local exact-commit checks and integration/release gates remain pending. Owner
local validation policy applies; hosted CI completion is not a merge prerequisite.
