"""Explicit synthetic EF3 declared breadth, observed breadth and adaptive-volume requests as supplied inputs; no acquisition."""
from equity_feature_duckdb.breadth_adaptive import (
    Fact, adaptive_case, declared_case, observed_case, reference, reference_batch,
)


def main() -> None:
    # Declared universe: four members on one governed session; every role is delivered complete.
    members = ("alpha", "beta", "gamma", "delta")
    population = {"cov": "complete", "rows": [
        {"m": m, "e": "E", "s": 0, "end": None, "ka": 60, "stint": 0} for m in members]}
    returns = {m: v for m, v in zip(members, (3, -1, 0, 2))}
    endpoints = {m: v for m, v in zip(members, (1100, 900, 1000, 1250))}
    declared = {
        "C": 100, "K": 100, "scale": 2, "profile": "static",
        "params": {"near_high_tol": [1, 4], "near_low_tol": [1, 5], "evidence_limit": 3},
        "roles": {
            "population": population,
            "pra": {"cov": "complete", "rows": {m: {"k": "available"} for m in members}},
            "ret": {"cov": "complete", "rows": {m: {"v": returns[m]} for m in members}},
            "vol": {"cov": "complete", "rows": {m: {"v": 100 * (i + 1)} for i, m in enumerate(members)}},
            "ep": {"cov": "complete", "rows": {m: {"v": endpoints[m], "t": 40} for m in members}},
            "vwap": {"cov": "complete", "rows": {m: {"k": "rat", "num": 1000, "den": 1} for m in members}},
            "mom": {"cov": "complete", "rows": {m: {"v": 1} for m in members}},
            "hi": {"cov": "complete", "rows": {m: {"v": 1120} for m in members}},
            "lo": {"cov": "complete", "rows": {m: {"v": 1000} for m in members}},
        },
    }
    case = declared_case(declared, entity_instrument="BREADTH-AGG")
    features = ("breadth.session.advancing_count", "breadth.session.near_high_fraction")
    print("declared", case.config(features).identity, [s.row_count if s else None for s in case.slots])

    # Observed roster: two groups of records with qualifiers; the group label is an explicit scope parameter.
    roster = {"C": 100, "K": 100, "scale": 2,
              "params": {"scope": "group", "group_label": "desk-1", "floor_price": [10, 1], "floor_volume": 100,
                         "evidence_limit": 3},
              "roles": {
                  "members": {"cov": "complete", "rows": {"p": {"g": "desk-1"}, "q": {"g": "desk-2"}}},
                  "chg": {"cov": "complete", "rows": {"p": {"v": 1}, "q": {"v": -1}}},
                  "qp": {"cov": "complete", "rows": {"p": {"v": 1500}, "q": {"v": 900}}},
                  "qv": {"cov": "complete", "rows": {"p": {"v": 200}, "q": {"v": 50}}}}}
    observed = observed_case(roster, entity_instrument="ROSTER-AGG")
    print("observed", observed.config(()).identity, [s.row_count if s else None for s in observed.slots])

    # Adaptive volume: a regular stream of supplied rates for one entity (sequence 1 to 6, one second apart).
    rates = (8, 8, 16, 32, 8, 8)
    stream = {"C": 100000000000, "K": 100000000000, "tau_ns": 1000000000, "W": 2, "evidence_limit": 2,
              "obs": {"cov": "complete", "rows": [
                  {"q": i + 1, "t": (i + 1) * 1000000000, "rate": [r, 1, 1]} for i, r in enumerate(rates)]}}
    adaptive = adaptive_case(stream, entity_instrument="Q9")
    print("adaptive", adaptive.config(()).identity, [s.row_count if s else None for s in adaptive.slots])

    # The helpers are explicit: a caller-built fact batch names its instrument, kind and reference on every row.
    manual = reference_batch([Fact("alpha", reference("bf1", ("t",), ("SYN-POP",)), "ef3.member.momentum", 50, None, 60,
                                                      None, 1)], input_id="mom", complete=False,
                             unit=declared_case(declared, entity_instrument="BREADTH-AGG").unit)
    print("manual role", manual.row_count, manual.metadata.coverage.complete)
    # The library (equity_features.ef3) computes every value; this module only maps and builds the request.


if __name__ == "__main__":
    main()
