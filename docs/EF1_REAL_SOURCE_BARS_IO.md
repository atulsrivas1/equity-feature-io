# EF1 bounded real-source bars (demonstration adapter)

`equity_feature_duckdb.real_bars_reader.read_real_regular_bars(database, table, symbol, date, row_cap, *, session_open_utc, session_close_utc, price_scale, currency)` reads a small slice of stored 1-minute bars and returns `RealRegularBarSource` for the existing regular completed-BAR price producer (see [supplied regular BAR inputs](api/EF1_REGULAR_BAR_PRICES_INPUTS.md)).

## Access rules

- One existing DuckDB file, opened `read_only=True` with `threads=1`; one parameterized SELECT for one symbol and one date inside an explicit UTC window; the connection is closed immediately. No write, copy, attach, export or network call.
- `row_cap` is a hard limit (maximum 5000). More matching rows refuse; nothing is truncated. No match refuses; nothing is invented.
- The table argument is a `schema.table` identifier. Database path, symbol and date are runtime parameters and are never stored in the repository.

## Lossless mapping

| Stored column | Canonical BAR field | Rule |
| --- | --- | --- |
| start timestamp text (UTC, second precision) | `start_ns` | exact integer nanoseconds; other formats refuse |
| (schema is one minute) | `end_ns` | start plus 60 s, a stated schema assumption |
| open, high, low, close (DOUBLE) | integer coefficients at `price_scale` | `Decimal(repr(value))` scaled; refuses if not exactly representable at the scale, so no rounding ever occurs |
| volume (integer) | `volume` | exact integer |
| symbol / instrument | `instrument_id` | one instrument and unique starts required |

The reader declares the scale it was given; a source with sub-cent prices needs a larger scale (the demonstration slice needed scale 3, scale 2 correctly refused).

## Provenance

Returned `provenance` is `calendar_provenance: synthetic`, `bars: duckdb_backed_observed`, `population_proof: synthetic`. These are caller declarations, not rights or capability evidence.

Absent from the stored source and therefore explicit SYNTHETIC stipulations: the trading calendar and session window, the population-completeness proof (membership is declared complete over the rows returned, which is not evidence that minutes without a stored bar had no trades), every original known-at clock (stipulated equal to bar end), the knowledge and market cutoffs (session close), the currency and the raw-adjustment declaration. The proof digest reimplements the reviewed membership projection and is verified by the pure producer.

No dataset-rights claim and no original-source parity claim is made; both stay unqualified owner items. Calculated close is the last positive-volume completed bar close of the supplied window, not an official close.
