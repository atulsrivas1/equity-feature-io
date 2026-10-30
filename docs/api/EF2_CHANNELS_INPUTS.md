# EF2 supplied Ichimoku and price-channel conversion - EF2-IO #609

This source candidate maps SUPPLIED OHLCV bars into the one `bars` role of the frozen Ichimoku and
price-channel contract (core `docs/ef2/ICHIMOKU_CHANNELS_CONTRACT_PROPOSAL.md`; contract `ef2-v1`,
algorithm `ef2-channels-v1`; producers `ichimoku`, `keltner`, `donchian`, `pivot_levels`,
`band_width_percentile`, `bollinger_keltner_squeeze`). It contains no Ichimoku, EMA, ATR, Keltner,
Donchian, pivot, percentile, Bollinger or squeeze mathematics, no default period, no acquisition and no
scale, currency, basis or unit normalization. Adapter and package versions are unchanged.

```python
from equity_feature_duckdb.channels import (
    ChannelsInputs, make_channels_batch, make_slot_coverage, make_channels_config,
    synthetic_channels_fixture, synthetic_channels_config, synthetic_channels_features,
    SYNTHETIC_CHANNELS_CASES, PRODUCER_PARAMETERS, PRODUCER_FEATURES, FEATURE_UNITS, FEATURE_DTYPES,
)
```

- `make_channels_batch(column_order, rows, *, metadata)` converts exact supplied BAR cells
  (`high`, `low`, `close`, `volume`, `known_at_ns`, grid `start_ns`/`end_ns`, no invented `open`)
  into a BAR batch, retaining order and metadata. Columns the delivery lacks are simply not listed.
  `make_slot_coverage(index, start_ns, end_ns, expected=, observed=, complete=)` builds the
  per-slot `slot:<index>` coverage entry of the R17 grid.
- `ChannelsInputs(bars=None, provenance=("unavailable",))`: one nullable role `bars` holding a tuple
  of BAR chunks, ONE PER GOVERNED SESSION (`.slots == (bars,)`, `.batches`); the pivots need the
  chunk of the preceding session. `None` is absent delivery; origins must match delivery; distinct chunk
  `input_id`s and one namespace are required.
- `make_channels_config(producer=..., ...)` builds `ef2.<producer>` (`ef2-channels-v1`) with the library
  keywords (that producer's own operation parameters, `availability`, `adjustment`, `price_unit`,
  `evidence_limit=0`, `convention_version=None`) plus the explicit R17 context (`instrument_id`,
  `calendar_id`, `grid_id`, `revision`, `sessions`, `runs`, `anchor_index`, `target_index`, `mode`).
  Byte-identical to the library `build_channels_config`. Ranges, bounds, reduced multipliers, mode and
  convention values (invalid_config, incompatible_version) belong to the pure decoder.
- `PRODUCER_PARAMETERS`, `PRODUCER_FEATURES` (lexical, the 25 ids), `CONVENTION_LABELS`,
  `CONFIG_IDENTITIES`, `FEATURE_UNITS` (`currency/share`, `fraction`, `boolean`) and `FEATURE_DTYPES`
  (`float64`; `bool` for `channel.squeeze.bollinger_inside_keltner`) give the sink headers of the worker layer.
- `SYNTHETIC_CHANNELS_CASES` lists the contract's own 74 result fixture ids (ICH-01..17 without ICH-10,
  KEL-01..10, DON-01..11, PIV-01..11 without PIV-07, PCT-01..15, SQ-01..12) including ICH-17 and the
  prefix fixtures ICH-15, KEL-09, DON-09, PIV-10, PCT-14 and SQ-11 (plain stand-alone fixtures).
  `synthetic_channels_fixture(case_id, *, empty_form="row")`, `synthetic_channels_config(case_id)` and
  `synthetic_channels_features(case_id)` (the producer's complete header set) return original inputs and
  carry no expected value.

Synthetic choices the contract does not fix (listed for the worker): entity X in namespace SYN, ten-ns
grid, one slot per fixture position, sessions `S0`, `S1`, ... then `S` (a single session is `S`), anchor
the first slot of the last session, K = evaluation = end of the last slot (also the last session close),
raw basis, USD at the fixture scale (0 or 2), `evidence_limit` the fixture's (the contract default 1000
is not applied by the builder; its library default is 0), volume 100 on every ordinary bar, known_at 5
(future: K+50, unknown: null). `gap` is a declared incomplete slot without a row (the compact values are
not supplied); `empty` a zero-volume all-null-OHLC row with complete coverage (or expected 0 without a
row, `empty_form="coverage"`); `null` a row with null volume and the listed OHLC field null (a
positive-volume bar with a null OHLC cell is invalid); absent columns are omitted from the delivery;
delivery none is `bars=None`. The library takes an `IntradayContext`; decode it from the config's context
chunks with `IntradayContext.from_json`.

[Executable synthetic example](../../examples/ef2_channels.py). See
[validation and remaining gates](../EF2_CHANNELS_IO.md).

## Contract catalogue

Internal, synthetic, pre-release. Generated input and output contract pages for the producers this page covers (core wins on conflict; the catalogue computes nothing and names no data supplier). Overview: [catalogue INDEX](../contracts/catalogue/INDEX.md); use: [CATALOGUE.md](../contracts/CATALOGUE.md).

- `ef2.band_width_percentile`: [input](../contracts/catalogue/ef2.band_width_percentile/input.md), [output](../contracts/catalogue/ef2.band_width_percentile/output.md)
- `ef2.bollinger_keltner_squeeze`: [input](../contracts/catalogue/ef2.bollinger_keltner_squeeze/input.md), [output](../contracts/catalogue/ef2.bollinger_keltner_squeeze/output.md)
- `ef2.donchian`: [input](../contracts/catalogue/ef2.donchian/input.md), [output](../contracts/catalogue/ef2.donchian/output.md)
- `ef2.ichimoku`: [input](../contracts/catalogue/ef2.ichimoku/input.md), [output](../contracts/catalogue/ef2.ichimoku/output.md)
- `ef2.keltner`: [input](../contracts/catalogue/ef2.keltner/input.md), [output](../contracts/catalogue/ef2.keltner/output.md)
- `ef2.pivot_levels`: [input](../contracts/catalogue/ef2.pivot_levels/input.md), [output](../contracts/catalogue/ef2.pivot_levels/output.md)
