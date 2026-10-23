# EF3 breadth and adaptive volume supplied inputs

`equity_feature_duckdb.breadth_adaptive` (EF3-IO [#611](https://github.com/atulsrivas1/equity-features/issues/611)) maps supplied member, roster and observation facts into canonical REFERENCE batches and builds the request envelopes of `ef3.session_breadth` (`ef3-breadth1`), `ef3.observed_breadth` (`ef3-obsbreadth1`) and `ef3.adaptive_volume` (`ef3-adaptive1`). The library (`equity_features.ef3`) computes every value and refusal; this module does no mathematics. The source checkpoint is [EF3_BREADTH_ADAPTIVE_IO.md](../EF3_BREADTH_ADAPTIVE_IO.md).

- `declared_case(inp, entity_instrument=...)`: nine nullable slots in library order (`population`, `prior_reference_availability`, `current_return`, `cumulative_volume`, `endpoint_price`, `vwap`, `momentum`, `selected_high`, `selected_low`). Static or ordered membership, one `ef3.population.member` or `ef3.breadth.membership_interval` row per member stint.
- `observed_case(inp, entity_instrument=...)`: four nullable slots (`members`, `change`, `qualifier_price`, `qualifier_volume`) for the roster and the observed facts; the group label is a config parameter.
- `adaptive_case(inp, entity_instrument=...)`: one nullable `observations` slot; each row names its instrument, epoch, sequence and event time, with a rational supplied rate.
- `Case.config(features)`: the configuration envelope for one selection. A tolerance parameter is present exactly when its fraction output is selected, as in the library.
- `reference_batch(facts, input_id=..., complete=..., unit=...)`: builds and validates one role. A complete role declares its row count; an incomplete role declares no expected count, so missing members are governed gaps.

Each `*_case` takes the entity instrument explicitly; there are no default instrument ids. `NAMESPACE`, `SESSION_ID`, `POPULATION_ID`, `POPULATION_REVISION`, `RECORD_SET_ID`, `SNAPSHOT_ID` and the session window are module constants, not parameters. `reference_batch` sorts facts by `(start_ns, reference_id)`, so out-of-order input is reordered silently. Member names come from the supplied rows. Reference identities: `x1:` (population), `bh1:` (membership stint, six digit), `bf1:` (declared facts), `ob1:` (roster and observed facts), `ao1:` (adaptive sequence, 19 digit) with the base64url text components. These identifiers are implementation choices pending the EF3 amendment and must be pinned there.

```python
from equity_feature_duckdb.breadth_adaptive import adaptive_case, declared_case

case = declared_case(declared_input, entity_instrument="BREADTH-AGG")
features = ("breadth.session.advancing_count", "breadth.session.near_high_fraction")
result = compute_ef3_breadth(case.slots, case.config(features), entity=case.entity, features=features)
```

Limits: no rounding, sorting by value, filling, rescaling or inference of supplied values. Rows are ordered by `(effective_start_ns, reference_id)` only as the shared validator requires.
