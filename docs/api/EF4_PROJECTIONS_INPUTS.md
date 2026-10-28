# EF4 projections supplied inputs

`equity_feature_duckdb.ef4_projections` (EF4-I2 I/O, EQ-172) maps supplied daily closes, epoch bars, leg witnesses, sector membership facts and tape-window aggregates into canonical batches and builds the request envelopes of the four I2 producers: `ef4.session_projection` (`ef4-proj1`), `ef4.bar_projection` (`ef4-proj1`), `ef4.relative_excess` (`ef4-rel1`) and `ef4.rate_projection` (`ef4-rate1`). The library (`equity_features.ef4`) computes every value, readiness decision and refusal; this module does no mathematics. The source checkpoint is [EF4_PROJECTIONS_IO.md](../EF4_PROJECTIONS_IO.md). Runnable example: `examples/ef4_projections.py`.

## Entry points

- `build_request(producer, fx, ctx, ids, *, default_known_at=None)` returns a `ProjectionRequest(producer, grid, batches, config, features, capability, entity)`. `producer` is `session_projection`, `bar_projection`, `relative_excess` or `rate_projection`.
- `fx` is the supplied input mapping of the producer (below). `ctx` carries `config_unit`, `batch` (`unit`, `adjustment`), `config_adjustment`, `capability` and `features`. `params` inside `fx` are the producer parameters, passed to the envelope as supplied and unvalidated, so the library refuses a bad or unknown parameter.
- `ProjectionIds(namespace, instrument_id, calendar_id, grid_id, revision, day_session_prefix, bar_session_id, target_session_id, names)`: every identity is a caller value. `names` binds supplied short names to ids; an unmapped name passes through so the library decides on it.
- `session_projection_inputs`, `bar_projection_inputs`, `relative_excess_inputs`, `rate_projection_inputs` build the batches of one producer; `BarGridCodec` and the EF3 daily grid codec carry the grid and its digest. The caller builds the library grid object from the codec (`ef4.BarGrid`, `ef3.DailyGrid`) and checks that the digests are equal.
- `ProjectionStageError(stage, error)` tags a refusal `io` (supplied-input mapping and the shared batch rules) or `library` (envelope, decided by the core).

## Roles and supplied inputs

| Producer | Roles (library order) | Supplied `fx` keys |
| --- | --- | --- |
| `session_projection` | `daily` BAR close-only | `closes` (one entry per governed daily slot), `target`, `K`, `params` |
| `bar_projection` | `bars` BAR | `bars` (one flat list, one entry per epoch bar), `notional_column`, `target`, `K`, `params` |
| `relative_excess` | `legs`, `membership` REFERENCE | `instrument`, `facts` (leg start and end), `membership`, `C`, `K`, `params` |
| `rate_projection` | `tape`, `legs` REFERENCE | `instrument`, `tape` (count, volume, notional aggregates), `legs`, `C`, `K`, `params` |

A slot is a value, or `{"row": ..., "ka": token}`, or one of `absent`, `gap`, `null`, `empty` (bars only: a proven-empty zero-volume bar). A bar row is `[open, high, low, close, volume, actual_notional]`; `actual_notional` is delivered only when `notional_column` is true, otherwise the column is omitted and the dollar outputs are absent input. Epoch bars are one batch with per-slot coverage `bar:<i>` (session projection: `slot:<i>`) and declared aggregate coverage on every batch; the chunked delivery is not modelled.

## Known-at

Availability is never defaulted. A slot or fact without `ka` has unknown availability exactly as a null `known_at` does. In session and bar notation a token `t` maps to `knowledge_ns - (K - t)` seconds; in relative and rate notation `ka` is the instant itself. `default_known_at` is an explicit opt-in for a caller that decodes a notation documenting a default token (the contract fixtures document 50); it is `None` unless given.

## Capability matrix

| Data needed | Supplied by | Client or server | Source |
| --- | --- | --- | --- |
| Daily closes, epoch bars (with actual notional for dollar outputs) | caller | client | any supplier of governed closes and bars |
| Leg start and end witnesses, sector membership | caller | client | any supplier of prices at witness times |
| Tape window count, volume, notional | caller | client | the `ef4-tape1` producer results |
| Values, readiness, refusals | library | client | `equity_features.ef4` |

## Limits

No derivation, filling, bridging, rescaling, value sorting or sector-name inference. REFERENCE facts are sorted by `(effective_start_ns, reference_id)` only. Reference ids use the closed `x1:` grammar. Optional DuckDB publication is `ef4_projections_sink.publish_results` (lazy optional imports). Adjustment is carried as the supplied basis label. Projections results are scalar and decimal columns (no top-K cells); the Parquet round trip of a bar projection with dollar outputs is recorded in the PR that added this document.

```python
from equity_feature_duckdb.ef4_projections import ProjectionIds, build_request
from equity_features import ef4

request = build_request("bar_projection", fx, {**ctx, "features": features}, ids)
g = request.grid
grid = ef4.BarGrid(g.instrument_id, g.calendar_id, g.grid_id, g.revision, g.session, g.bar_ns, g.bar_count, g.target_index)
result = ef4.compute_ef4_path_projections(request.batches, request.config, features=features, grid=grid)
```
