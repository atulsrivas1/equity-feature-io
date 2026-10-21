# Supplied gap endpoint inputs

Source candidate for [EQ212 #570](https://github.com/atulsrivas1/equity-features/issues/570). [Validation and limits](../EF1_GAP_ENDPOINT_IO.md). Requires the compatible reviewed EF1 endpoint library source, not merely an equal version string.

```python
from equity_feature_contracts import EntityKey
from equity_feature_duckdb.ef1 import (
    synthetic_gap_endpoint_config, synthetic_gap_endpoint_fixture,
)
from equity_features.ef1 import compute_ef1

inputs = synthetic_gap_endpoint_fixture("E01_up_reversal")
config = synthetic_gap_endpoint_config("E01_up_reversal")
result = compute_ef1(inputs.slots, config, entity=EntityKey("X", "S"))
```

Use `E26_bar_close_at_cutoff` for the literal bar example. These helpers return independent original synthetic source assertions, not inferred observed-data provenance. No observed-source capability is admitted.

`GapEndpointInputs(calendar_provenance=None, path=None, prior_close=None, population_proof=None, provenance=("unavailable",)*4)` retains four exact roles and nullable slots. Actual input kinds are REFERENCE, TRADE-or-BAR, DAILY, REFERENCE. Set each present slot's provenance explicitly to `synthetic` or `duckdb_backed_observed`; the latter labels supplied origin and does not qualify rights or historical capability. Use `.slots` for the endpoint calculation; `.batches` contains only present originals for generic worker transport. Two REFERENCE roles are never inferred from kind.

`make_gap_endpoint_batch(kind, column_order, rows, metadata=metadata)` accepts concrete tuple column order and rectangular tuple rows. It preserves every supplied cell and metadata, running ordinary canonical validation. No sorting, defaulting, numerical calculations or proof creation occurs. It may refuse structural invalidity before the pure producer. Semantic proof defects remain available to actual pure admission.

`make_gap_population_proof(row, metadata=metadata)` requires exactly the original eight cells in `instrument_id, session_id, reference_id, fact_kind, effective_start_ns, effective_end_ns, text, known_at_ns`. It preserves the supplied original JSON text and known-at. It never generates a digest from observed rows, backdates a new declaration or authenticates a snapshot. The pure library performs bounded canonical proof/profile/config/source closure and mathematical admission.

The existing SDK serializes full canonical results; the existing sink writes to a new separate output DuckDB. Source databases are never destinations. Adapter source does not change generic SDK/sink schemas, retry identity, old producer behavior or package versions. Full release, installed-artifact and observed-data qualification remain separate.
