# EF4 tape trades and notional top-K supplied inputs

`equity_feature_duckdb.tape` (EF4-G I/O, EQ-158 and EQ-162) maps supplied TRADE rows, the optional `ef4.tick.seed` REFERENCE fact and notional top-K partitions into canonical batches, and builds the request envelopes of `ef4.tape_window_sign` (`ef4-tape1`) and `ef4.trade_top_k_notional` (`ef4-notional1`). The library (`equity_features.ef4`) computes every value, readiness decision and refusal; this module does no mathematics. The source checkpoint is [EF4_TAPE_IO.md](../EF4_TAPE_IO.md).

- `window_case(...)`: the window request. Two nullable slots in library order: `trades` (a `TradeSupply`) and `seed` (a `SeedSupply`, present exactly when the seed is supplied). Parameters `window_ns`, `seed_policy`, `evidence_limit` and `policy_version` are passed as supplied; `extra_parameters` passes any further supplied parameter through so the library refuses it.
- `top_k_case(...)`: the notional top-K request, one nullable `trades` slot. Each partition of a merge is its own request with its own `input_id` (the label of the partition).
- `TradeSupply(rows, delivered, coverage, scale, adjustment, kind, scope_policy, scope_start_ns, scope_end_ns, scope_include_*_auction, input_id)`: the supplied TRADE batch in the supplied order. Nothing is sorted, deduplicated or filled. `delivered` names the payload columns (`price`, `size`, `condition`, `known_at_ns`) the supplier delivers; an undelivered column is omitted. `scale`, `adjustment`, `kind`, `coverage` and the scope are carried as supplied, so the shared validators and the library refuse a mismatch.
- `SeedSupply(facts, seed_set_id, scale, adjustment)`: the seed facts. The reference id is `seed_reference(seed_set_id)`, the closed grammar `x1:` followed by the unpadded URL-safe base64 of the caller's seed-set id.
- `TapeCase.config()`: the envelope of the request. The library builders (`build_tape_window_config`, `build_notional_top_k_config`) give the same `ConfigSpec` for the same explicit parameters; the runner checked this for every fixture.
- `session_spec(...)`, `availability(...)`: the governed session (the caller names the session id and both bounds) and the causal `known_at` timing, or `reconstruction` timing with the identity label `RECONSTRUCTION_REASON`.

Each builder takes the instrument, session and eligibility policy explicitly. There are no default instrument, entity, session or grid ids. The only constants are the namespace, source, snapshot and mapping labels, the identities and algorithm labels of the two producers, and the trade column names.

Top-K cells are notional-ordered. The shared size-ranked `TopKTrades` constructor refuses them (`INVALID_ORDER`), so this module never rebuilds a cell. The DuckDB sink reads a stored top-K cell through the io-sdk codec, which keeps the constructor check and falls back to the stored fields only for `INVALID_ORDER` (see the checkpoint).

```python
from equity_feature_duckdb.tape import SeedSupply, TradeSupply, top_k_case, window_case
from equity_features.ef4 import compute_tape_window, compute_trade_top_k_notional

case = window_case(instrument_id="X", session_id="S", open_ns=0, cutoff_ns=100, knowledge_ns=1000,
                   session_close_ns=10**12, price_scale=2, eligibility_policy="eligible_trade", window_ns=100,
                   seed_policy="supplied", evidence_limit=10, policy_version="ef4-tape1",
                   trades=TradeSupply(rows=trade_rows, delivered=("price", "size", "known_at_ns")), seed=seed_supply)
result = compute_tape_window(case.slots, case.config(), entity=case.entity, features=("tape.window.count",))
```

Limits: no sorting, rounding, filling, rescaling or inference of supplied values. Reference identities use the shared `x1:` grammar only. Windows publish the result-wide evidence bound of the library (`evidence_limit * 9`).

## Adjustment, known refusals and known limits

- Adjustment: `AdjustmentSpec(label)` carries only the basis label; it cannot carry a snapshot or anchor. A non-raw supplied basis therefore raises `UNSUPPORTED_ADJUSTMENT` at I/O (or in the library, for the partition and merge cases) and the config adjustment is fixed to `raw`. This is the reason for RF14, RF62 and RF71.
- RF18 (`batch_kind = quote`): the shared batch validator refuses first with `UNSUPPORTED_SAMPLING` (the quote kind carries the trade sampling label). The contract expects `INVALID_SCHEMA`; the refusal is at I/O and the input is still refused.
- RF35 (`seed.count = 2`, two identical `ef4.tick.seed` facts): the shared REFERENCE validator refuses first with `DUPLICATE`. The contract expects `INVALID_SCHEMA` ("exactly one seed fact"); the refusal is at I/O.
- RF69 (a supplied partial whose rows arrive in the delivered order): the adapter has no supplied-partial input. The runner reorders a computed partial's cell rows to the delivered order and the library's merge refuses with `INVALID_ORDER`. This is exercised by the runner, not through the adapter.
- Known limit: the `bundles` package decoder (`equity_feature_bundles/_typed.py`) rebuilds `TopKTrades` through the constructor and will refuse EF4 notional-ordered cells. The Parquet and bundles round trip is not covered by this change.
- Codec: the io-sdk decoder reads a notional-ordered cell only for a `tape.top_k_notional` column (checked by feature id); all other top-K cells keep the shared size-order constructor.
