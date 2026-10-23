"""Explicit synthetic EF4-H quote dynamics and VWAP path requests as supplied inputs; no acquisition, no computation."""
from equity_feature_contracts import EntityKey, SessionSpec
from equity_feature_duckdb.quote_vwap import (
    BarRow, COMPLETE, Fact, Gap, QuoteRow, Scope, adjustment, availability, bar_batch, price_unit, quote_batch,
    quote_parameters, quote_request, reference, reference_batch, vwap_parameters, vwap_request,
)

NAMESPACE = "SYN"
ENTITY = EntityKey("ENTITY-1", "SESSION-1")
SESSION = SessionSpec(NAMESPACE, "SESSION-1", 0, 10**12, "UTC")
INTERVAL = (0, 100)
SCOPE = Scope(INTERVAL[0], INTERVAL[1], "interval:interval-1")
UNIT = price_unit(0, "USD")


def bounds(known_at: int):
    fact = Fact(ENTITY.instrument_id, ENTITY.session_id, reference("interval-1"), "ef4.interval.bounds", INTERVAL[0],
                INTERVAL[1], "snap", known_at)
    return reference_batch([fact], scope=SCOPE, declared=COMPLETE, input_id="bounds")


def main() -> None:
    # Quote dynamics: three supplied quote states, complete coverage declared, continuous sampling.
    quotes = [
        QuoteRow(ENTITY.instrument_id, ENTITY.session_id, "q1", 0, 1, 100, 102, 300, 100, 50),
        QuoteRow(ENTITY.instrument_id, ENTITY.session_id, "q2", 3, 1, 102, 102, 200, 200, 50),
        QuoteRow(ENTITY.instrument_id, ENTITY.session_id, "q3", 7, 1, 105, 104, 100, 100, 50),
    ]
    quote_slot = quote_batch(quotes, scope=SCOPE, sampling="continuous", unit=UNIT, declared=COMPLETE,
                             basis=adjustment("raw"))
    quote_req = quote_request(entity=ENTITY, session=SESSION, timing=availability(100, 100), config_unit=UNIT,
                              params=quote_parameters(policy_version="ef4-quote1", sampling="continuous",
                                                      evidence_limit=10),
                              bounds=bounds(50), quotes=quote_slot)
    print("quote", quote_req.config.identity, [s.row_count if s else None for s in quote_req.slots])

    # VWAP path from bars: four grid edges, two delivered bars, one declared gap slot, one absent slot.
    edges = [0, 25, 50, 75, 100]
    grid = reference_batch(
        [Fact(ENTITY.instrument_id, ENTITY.session_id, reference(f"grid-1#{i}"), "ef4.window.edge", t, None, "grid-1", 50)
         for i, t in enumerate(edges)], scope=SCOPE, declared=COMPLETE, input_id="grid")
    bars = bar_batch(
        [BarRow(ENTITY.instrument_id, ENTITY.session_id, 0, 25, 100, 10100, 50),
         BarRow(ENTITY.instrument_id, ENTITY.session_id, 25, 50, 200, 20400, 50)],
        [Gap(50, 75)], scope=SCOPE, unit=UNIT, basis=adjustment("raw"))
    vwap_req = vwap_request(entity=ENTITY, session=SESSION, timing=availability(100, 100), config_unit=UNIT,
                            params=vwap_parameters(policy_version="ef4-vwap1", series_source="bar", evidence_limit=10,
                                                   grid_version="grid-1"),
                            bounds=bounds(50), grid=grid, trades=None, bars=bars, proof=None)
    print("vwap", vwap_req.config.identity, [s.row_count if s else None for s in vwap_req.slots])


if __name__ == "__main__":
    main()
