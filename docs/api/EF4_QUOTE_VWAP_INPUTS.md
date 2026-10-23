# EF4 quote dynamics and VWAP path supplied inputs

`equity_feature_duckdb.quote_vwap` maps supplied quote, trade, bar, declared-gap, grid-edge, prepared-proof and bounds
values into canonical batches and assembles the two producer requests of the core library (`ef4-quote1` for
`ef4.quote_dynamics`, `ef4-vwap1` for `ef4.vwap_path`; contract `docs/ef4/QUOTE_VWAP_CONTRACT_PROPOSAL.json`). Every value
the caller supplies is carried through unchanged. The module computes nothing; `equity_features.ef4` performs every
admission, decision and refusal.

## Batches

| Function | Role | Kind | Notes |
| --- | --- | --- | --- |
| `reference_batch(facts, scope=, declared=, input_id=)` | bounds, grid, proof | REFERENCE | `Fact` carries instrument, session, reference id, fact kind, times, text and known-at as supplied. |
| `quote_batch(rows, scope=, sampling=, unit=, declared=, basis=)` | quotes | QUOTE | Full state rows in supplied order; `sampling` is the supplied sampling. |
| `trade_batch(rows, scope=, unit=, declared=, basis=)` | trades | TRADE | Supplied `eligible`, `price` and `size`. |
| `bar_batch(rows, gaps, scope=, unit=, basis=)` | bars | BAR | `BarRow` per delivered slot, with optional `ohlc`; `Gap` per declared incomplete slot with no row. A slot with neither is absent. |

`bar_batch` declares each delivered slot complete unless its `BarRow` sets `incomplete=True`, which declares the slot incomplete; a `Gap` is incomplete with no row. `declared` is required and is one of `complete`, `incomplete` or `absent`. `complete` declares the row count, `incomplete`
declares an unknown expected count, and `absent` admits no row. There is no undeclared path: a role with rows is always sent
with an explicit declaration. `Scope(start_ns, end_ns, name)` is the declared delivery window of a batch. `adjustment(basis)`
builds the shared adjustment basis of a batch.

## Requests

- `quote_request(entity=, session=, timing=, config_unit=, params=, bounds=, quotes=)`: slots `(bounds, quotes)`.
- `vwap_request(entity=, session=, timing=, config_unit=, params=, bounds=, grid=, trades=, bars=, proof=)`: slots
  `(bounds, grid, trades, bars, proof)`.
- `quote_parameters(policy_version=, sampling=, evidence_limit=)` and
  `vwap_parameters(policy_version=, series_source=, evidence_limit=, grid_version=, series_policy_id=)` return the closed
  parameter tuples. Grid and series policy are present exactly when supplied; the library refuses any other presence.
- `availability(market_cutoff_ns, knowledge_cutoff_ns)` builds the causal timing.
- `reference(text)` encodes a reference identity as `x1:` followed by the unpadded URL-safe base64 of the text.

Bounds-fact text must equal the snapshot label `snap` (`SNAPSHOT_ID`); any other text is refused by the library as `INCONSISTENT_IDENTITY`.

The entity (instrument and session), session, interval, grid version, series policy and series identifiers are caller values.
The module fixes only the namespace, source, snapshot (`snap`) and mapping labels.

## Sink

Results are published with `equity_feature_io_sdk.publication` (`prepare_publication`, `publish`) to
`equity_feature_duckdb_sink.DuckDBSink`, one generation per result, and read back with `sink.read(receipt)`.
