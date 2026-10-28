"""Explicit synthetic EF4 tape trades, tick seed and notional top-K partitions as supplied inputs; no acquisition."""
from equity_feature_contracts import Coverage
from equity_feature_duckdb.tape import SeedSupply, TradeSupply, top_k_case, window_case


def main() -> None:
    # Window: three prints in the window [C - W, C) after a seeded tick chain; the seed is the last print before the open.
    trades = TradeSupply(rows=(
        {"instrument_id": "X", "session_id": "S", "event_ns": 10, "order_key": 0, "event_id": "t1", "eligible": True,
         "price": 100, "size": 5, "known_at_ns": 500},
        {"instrument_id": "X", "session_id": "S", "event_ns": 20, "order_key": 0, "event_id": "t2", "eligible": True,
         "price": 101, "size": 3, "known_at_ns": 500},
        {"instrument_id": "X", "session_id": "S", "event_ns": 30, "order_key": 0, "event_id": "t3", "eligible": True,
         "price": 100, "size": 4, "known_at_ns": 500},
    ), delivered=("price", "size", "known_at_ns"), coverage=Coverage(3, 3, True))
    seed = SeedSupply(facts=({"fact_kind": "ef4.tick.seed", "instrument_id": "X", "session_id": "S",
                              "effective_start_ns": -1, "effective_end_ns": 0, "text": "+", "price": 99,
                              "factor_num": None, "factor_den": None, "known_at_ns": 0},), seed_set_id="example-seed-set")
    window = window_case(instrument_id="X", session_id="S", open_ns=0, cutoff_ns=100, knowledge_ns=1000,
                         session_close_ns=10**12, price_scale=2, eligibility_policy="eligible_trade", window_ns=100,
                         seed_policy="supplied", evidence_limit=10, policy_version="ef4-tape1", trades=trades, seed=seed)
    print("window", window.config().identity, [s.row_count if s else None for s in window.slots])

    # Notional top-K: one partition of the same entity and session with its own supplied rows.
    partition = TradeSupply(rows=trades.rows[:2], delivered=("price", "size", "known_at_ns"), coverage=Coverage(2, 2, True),
                            input_id="P1")
    top_k = top_k_case(instrument_id="X", session_id="S", open_ns=0, cutoff_ns=100, knowledge_ns=1000,
                       session_close_ns=10**12, price_scale=2, eligibility_policy="eligible_trade", top_k=2,
                       evidence_limit=2, policy_version="ef4-notional1", trades=partition)
    print("top-k", top_k.config().identity, [s.row_count if s else None for s in top_k.slots])
    # The library (equity_features.ef4) computes every value and refusal; this module only maps and builds the request.


if __name__ == "__main__":
    main()
